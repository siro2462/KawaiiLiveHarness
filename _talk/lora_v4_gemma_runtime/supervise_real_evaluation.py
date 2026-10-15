"""One child, native Windows exit observation, no retries or restarts."""
import argparse
import ast
import ctypes
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
import psutil

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'lora_v4_multibase'
sys.path.insert(0,str(OLD))
from atomic_state import write
sys.path.insert(0,str(ROOT))
from evaluation_support import read,sha


def observation(pid):
    p=psutil.Process(pid)
    return {'pid':pid,'created_unix':p.create_time(),'parent_pid':p.ppid(),'command_line':p.cmdline(),'executable':p.exe()}


def observer_type():
    path=OLD/'supervise_windows_after_mac_handoff.py'
    tree=ast.parse(path.read_text(encoding='utf8'))
    nodes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ObservedProcess']
    assert len(nodes)==1
    ns={'psutil':psutil,'time':time,'subprocess':subprocess}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)
    return ns['ObservedProcess']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    out=parser.parse_args().out.resolve();assert out.is_relative_to(ROOT/'runs')
    assert (out/'cpu_preflight.json').exists() and not (out/'supervisor.json').exists()
    state={'status':'running','pid':os.getpid(),'create_time':psutil.Process().create_time(),
           'started_unix':time.time(),'exit_code':None,'automatic_restart':False}
    write(out/'supervisor.json',state);write(out/'launch_observation.json',{'supervisor':observation(os.getpid())})
    env=dict(os.environ);env['PYTHONPATH']=str(ROOT)+os.pathsep+str(OLD);env['PYTHONIOENCODING']='utf-8';env['PYTHONUNBUFFERED']='1'
    try:
        with (out/'inference.stdout.log').open('x',encoding='utf8') as stdout,(out/'inference.stderr.log').open('x',encoding='utf8') as stderr:
            child=subprocess.Popen([sys.executable,'-X','utf8','-u',str(OLD/'child_guard.py'),'--receipt',str(out/'python_outcome.json'),
                                    str(ROOT/'run_real_evaluation.py'),'--out',str(out)],cwd=ROOT,env=env,stdout=stdout,stderr=stderr,
                                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            state['child_launcher_pid']=child.pid;write(out/'supervisor.json',state)
            native=None;seen=None
            while True:
                manifest=out/'manifest.json'
                if native is None and manifest.exists():
                    value=read(manifest);seen=observation(value['pid'])
                    assert seen['created_unix']==value['create_time']
                    assert any('child_guard.py' in a for a in seen['command_line'])
                    assert any('run_real_evaluation.py' in a for a in seen['command_line'])
                    native=observer_type()(value['pid'],seen)
                    write(out/'launch_observation.json',{'supervisor':observation(os.getpid()),'child_launcher':observation(child.pid),'actual_worker':seen})
                tree=[]
                for p in psutil.Process().children(recursive=True):
                    try:tree.append(observation(p.pid))
                    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                write(out/'active_process_tree.json',{'observed_unix':time.time(),'processes':tree})
                if native is not None and native.poll() is not None:
                    state['native_worker_exit_code']=native.returncode;break
                if child.poll() is not None:
                    state['native_worker_exit_code']=native.poll() if native is not None else None;break
                time.sleep(10)
            state['launcher_exit_code']=child.wait(timeout=60)
        outcome=read(out/'python_outcome.json') if (out/'python_outcome.json').exists() else None
        final=read(out/'manifest.json') if (out/'manifest.json').exists() else {}
        success=(state.get('native_worker_exit_code')==0 and state['launcher_exit_code']==0 and
                 outcome is not None and outcome['exit_code']==0 and final.get('status')=='outputs_ready')
        state.update(status='complete' if success else 'failed',exit_code=0 if success else 1,
                     finished_unix=time.time(),python_outcome=outcome)
        write(out/'supervisor.json',state)
        from report_real_evaluation import build
        build(out)
        if not success:raise SystemExit(1)
    except BaseException as exc:
        if not isinstance(exc,SystemExit):
            state.update(status='failed',exit_code=1,error=str(exc),traceback=traceback.format_exc(),finished_unix=time.time())
            write(out/'supervisor.json',state)
        raise


if __name__=='__main__':main()
