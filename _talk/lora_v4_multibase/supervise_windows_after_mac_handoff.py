"""Sequential isolated pipeline. Failed children are recorded, never restarted."""
import os
import argparse
import subprocess
import sys
import time
import traceback
import psutil
from multibase_common import *

def verify(progress):
    for name,digest in read(progress/'code_hashes.json').items():assert sha(ROOT/name)==digest,'Pipeline code changed: '+name
    for path,digest in read(RUN/'frozen_identities.json').items():assert sha(path)==digest,'Frozen comparison identity changed: '+path

def observation(pid):
    p=psutil.Process(pid)
    return {'pid':pid,'created_unix':p.create_time(),'command_line':p.cmdline(),
            'parent_pid':p.ppid(),'rss_bytes':p.memory_info().rss}


class ObservedProcess:
    """A non-child Windows process handle retains its actual exit code."""
    def __init__(self, pid, expected):
        import ctypes
        self.pid = pid
        p = psutil.Process(pid)
        assert p.create_time() == expected['created_unix']
        assert p.cmdline() == expected['command_line']
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.restype = ctypes.c_void_p
        self.kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        self.kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.handle = self.kernel.OpenProcess(0x100000 | 0x1000, False, pid)
        if not self.handle: raise ctypes.WinError(ctypes.get_last_error())
        self.returncode = None
    def poll(self):
        import ctypes
        if self.returncode is not None: return self.returncode
        code = ctypes.c_uint32()
        if not self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.returncode = None if code.value == 259 else code.value
        if self.returncode is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
        return self.returncode
    def wait(self, timeout=None):
        start = time.monotonic()
        while self.poll() is None:
            if timeout is not None and time.monotonic()-start >= timeout:
                raise subprocess.TimeoutExpired('adopted process', timeout)
            time.sleep(.1)
        return self.returncode

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--recovery');args=parser.parse_args()
    progress=Path(args.recovery) if args.recovery else RUN
    assert progress.resolve().is_relative_to(RUN.resolve())
    cfg=read(RUN/'protocol.json');state=read(progress/'manifest.json');assert state['status']=='prepared'
    cfg=dict(cfg);cfg['model_order']=[k for k in cfg['model_order'] if k!='xing40_29b_a4b']
    assert sha(Path(__file__))==state['scheduler_code_sha256']
    skipped={(r['model'],r['stage']) for r in state.get('stages',[])}
    state.update(status='running',supervisor_pid=os.getpid(),started=now(),training_started=bool(skipped))
    state.setdefault('stages',[])
    write(progress/'manifest.json',state)
    superstate={'status':'running','pid':os.getpid(),'started':now(),'exit_code':None,'automatic_restart':False}
    write(progress/'supervisor.json',superstate);write(progress/'launch_observation.json',observation(os.getpid()))
    logs=progress/'logs';logs.mkdir(exist_ok=False)
    def save():
        state['updated']=now();write(progress/'manifest.json',state)
        write(ROOT/'state.json',{'status':state['status'],'run':str(progress),'artifacts_run':str(RUN),'model':state.get('model'),'stage':state.get('stage'),
            'training_started':state['training_started'],'full_weight_download_started':True,
            'pending_user_input':None,'updated':state['updated'],'supervisor_pid':os.getpid(),
            'placement_authorization':'2026-10-12 user approved scheduler-only Mac Xing handoff','external_model_placement':state.get('external_model_placement'),'automatic_failed_stage_restart':False})
    try:
        with Lock(ROOT/'pipeline.lock'):
            for key in cfg['model_order']:
                state['model']=key
                for stage in cfg['stage_order']:
                    verify(progress)
                    if (key,stage) in skipped:continue
                    state['stage']=stage;save()
                    if stage=='download' and (ROOT/'audit'/('download_'+key+'.json')).exists():
                        path=ROOT/'audit'/('download_'+key+'.json');d=read(path)
                        external={'model':key,'stage':stage,'origin':'previously authorized running downloader','started':now(),'pid':d.get('pid')}
                        if d['status']=='running':
                            o=observation(d['pid']);command=' '.join(o['command_line'])
                            assert 'download_weights.py' in command and key in command
                            external['process_identity']=o
                            while d['status']=='running':
                                if not psutil.pid_exists(o['pid']) or psutil.Process(o['pid']).create_time()!=o['created_unix']:
                                    raise RuntimeError('Downloader disappeared without completed state; no restart')
                                state['external_download_observation']={**observation(o['pid']),
                                    'io_counters':dict(psutil.Process(o['pid']).io_counters()._asdict())};save()
                                time.sleep(30);d=read(path)
                        assert d['status']=='complete','Existing download failed; inspect preserved logs'
                        for name,info in d['files'].items():assert sha(ROOT/'models'/key/name)==info['sha256']
                        external.update(status='complete',finished=now(),exit_code=None,
                            exit_code_scope='not observed by this later supervisor; completed hashes/state independently verified')
                        state['stages'].append(external);save();continue
                    script,args={
                        'download':('download_weights.py',['--model',key]),
                        'quant_cache':('build_quant_cache.py',['--model',key]),
                        'admission':('admit_full_model.py',['--model',key]),
                        'planner':('train_multibase.py',['--model',key,'--kind','planner']),
                        'planner_evaluation':('evaluate_multibase.py',['--model',key,'--planner-only']),
                        'talk_v3':('train_multibase.py',['--model',key,'--kind','talk_v3']),
                        'talk_v4':('train_multibase.py',['--model',key,'--kind','talk_v4']),
                        'evaluation':('evaluate_multibase.py',['--model',key]),
                        'runtime_bc_10m':('runtime_multibase.py',['--model',key]),
                        'report':('report_multibase.py',['--model',key])}[stage]
                    recovery=state.get('recovery_stage')
                    if recovery and (key,stage)==(recovery['model'],recovery['stage']):
                        args += ['--resume',recovery['checkpoint'],'--output',recovery['output']]
                    record={'model':key,'stage':stage,'started':now(),'status':'running'}
                    stem=logs/(key+'_'+stage)
                    with stem.with_suffix('.stdout.log').open('w',encoding='utf8') as out,stem.with_suffix('.stderr.log').open('w',encoding='utf8') as err:
                        receipt=stem.with_suffix('.process_exit.json')
                        adopt=state.get('adopt_record')
                        adopting=bool(adopt and (adopt['model'],adopt['stage'])==(key,stage))
                        command=[sys.executable,'-X','utf8','-u',str(ROOT/'child_guard.py'),'--receipt',str(receipt),str(ROOT/script),*args]
                        if adopting:
                            record=state.pop('adopt_record')
                            command=record['command']
                            receipt=Path(command[command.index('--receipt')+1])
                            expected=next(p for p in record['process_tree'] if p['pid']==record['launcher_pid'])
                            child=ObservedProcess(record['launcher_pid'],expected)
                            record['scheduler_handoff']='existing child adopted; no stop/restart'
                        else:
                            child=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err)
                            record.update(launcher_pid=child.pid,command=command)
                        state['active_process']=record;save()
                        if stage in ['planner','talk_v3','talk_v4']:state['training_started']=True
                        while child.poll() is None:
                            try:
                                launcher=psutil.Process(child.pid)
                                record['process_tree']=[observation(launcher.pid)]+[observation(p.pid) for p in launcher.children(recursive=True)]
                                write(progress/'active_process_tree.json',record)
                            except psutil.Error:pass
                            if stage in ['planner','talk_v3','talk_v4']:
                                child_state=stage_dir(key,stage)/'state.json'
                                if child_state.exists() and read(child_state)['status']=='failed':
                                    record['reported_failure']=read(child_state)
                                    try:
                                        child.wait(timeout=15)
                                    except subprocess.TimeoutExpired:
                                        # Only a child with this launch identity and an explicit failed
                                        # state is eligible. No live healthy trainer is stopped.
                                        owner=psutil.Process(record['reported_failure']['pid'])
                                        identity=next(p for p in record['process_tree'] if p['pid']==owner.pid)
                                        assert owner.create_time()==identity['created_unix'] and owner.cmdline()==identity['command_line']
                                        assert owner.parent().pid==child.pid
                                        owner.terminate();owner.wait(timeout=10);child.wait(timeout=10)
                                        record['failed_child_shutdown_cleanup']=True
                            save();time.sleep(30)
                        record.update(exit_code=child.returncode,finished=now(),status='complete' if child.returncode==0 else 'failed')
                        if receipt.exists():record['python_outcome']=read(receipt)
                    state['stages'].append(record);state.pop('active_process',None);save()
                    if record['exit_code']!=0:raise RuntimeError(key+' '+stage+' exit '+str(record['exit_code'])+'; inspect '+str(stem)+'.stderr.log')
                
                if key not in state.setdefault('models_with_outputs',[]):state['models_with_outputs'].append(key)
                save()
            state.update(status='outputs_ready',stage='root_review_pending',finished=now(),root_review='pending',completion_scope='Windows Gemma and LLM-jp only; Xing executes on Mac')
            superstate.update(status='complete',exit_code=0,finished=now());save();write(progress/'supervisor.json',superstate)
    except Exception as exc:
        state.update(status='failed',finished=now(),error=str(exc),traceback=traceback.format_exc())
        superstate.update(status='failed',exit_code=1,finished=now(),error=str(exc));save();write(progress/'supervisor.json',superstate);raise

if __name__=='__main__':main()
