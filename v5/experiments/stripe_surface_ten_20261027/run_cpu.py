from common import *
import subprocess,traceback
from processor_cpu import load_processor
from driver_cpu import Driver
from stripe_runtime import render_sample,format_reason

def rollout(d,cfg):
 results=[]
 for s in read(OUT/'samples.json'):
  prompt,payload=render_sample(s)
  context=dict(experiment=cfg['experiment'],sample_id=s['id'],category=s['category'],payload=payload,before=dict(history=[],semantic_status='unverified'),source_inputs_sha256=sha(OUT/'samples.json'),fixed_sequence=True,adaptive_reselection=False)
  cid,out=d.call('surface',prompt,cfg['surface_seed'],context);reason=format_reason(out['body'],out['official_stop_reached'])
  row=dict(call_id=cid,sample_id=s['id'],body=out['body'],raw_output=out['raw_output'],delivered=reason is None,format_reason=reason,semantic_status='unverified',presented_not_semantically_executed=list(range(1,33)),after_history=[dict(text=out['body'],origin='offline unverified text; not Memory')] if reason is None else [])
  results.append(row);write(OUT/'turns'/(cid+'.json'),row)
  write(OUT/'ten_result.json',dict(records=results,completed_samples=len(results),actual_surface_calls=d.n,planner_calls=0,guard_calls=0,training=0,quality_retries=0,memory_writes=0))
 return read(OUT/'ten_result.json')

def main():
 state=dict(status='running',phase='cpu_initialize',calls_completed=0,**obs(os.getpid()),started_jst=now());write(OUT/'controller.json',state)
 try:
  cfg=verify();assert read(OUT/'cpu_preflight.json')['status']=='pass'
  assert sha(OUT/'prepared_inputs.json')==read(OUT/'cpu_preflight.json')['prepared_inputs_sha256']
  proc,torch=load_processor()
  for p in [BETA/'dependencies',GEMMA/'dependencies',GEMMA,MULTI]:sys.path.insert(0,str(p))
  from supervise_real_evaluation import observer_type
  env=dict(os.environ,PYTHONPATH=os.pathsep.join(map(str,[HERE,BETA,MULTI,GEMMA])),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1')
  receipt=OUT/'gpu.python_outcome.json'
  with (OUT/'gpu.stdout.log').open('x',encoding='utf-8') as so,(OUT/'gpu.stderr.log').open('x',encoding='utf-8') as se:
   child=subprocess.Popen([cfg['gpu_python'],'-X','utf8','-B','-u',str(MULTI/'child_guard.py'),'--receipt',str(receipt),str(HERE/'gpu_worker.py')],cwd=BETA,env=env,stdout=so,stderr=se,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
   state.update(launcher=obs(child.pid),phase='waiting_native_handshake');write(OUT/'controller.json',state);deadline=time.monotonic()+120
   while not (OUT/'inference/state.json').exists():
    if child.poll() is not None:raise RuntimeError('GPU initialization exited')
    if time.monotonic()>deadline:raise TimeoutError('GPU handshake absent')
    time.sleep(.2)
   w=read(OUT/'inference/state.json');actual=obs(w['pid']);assert abs(actual['created_unix']-w['created_unix'])<.01
   native=observer_type()(actual['pid'],actual);write(OUT/'inference/observer_ready.json',dict(worker_pid=actual['pid'],worker_created_unix=actual['created_unix'],observer_pid=os.getpid()));state.update(actual_gpu=actual);write(OUT/'controller.json',state)
   d=Driver(state,cfg,proc,torch,native);result=rollout(d,cfg);assert d.n==10 and result['completed_samples']==10
   prepared=read(OUT/'prepared_inputs.json')['by_sample']
   for item in result['records']:
    req=read(OUT/'requests'/(item['call_id']+'.json'));assert all(req[k]==v for k,v in prepared[item['sample_id']].items())
   write(OUT/'requests/DONE.json',dict(calls=d.n,finished_jst=now()))
   while native.poll() is None:time.sleep(.5)
   launch_exit=child.wait(timeout=60);outcome=read(receipt);assert native.returncode==launch_exit==outcome['exit_code']==0
   state.update(native_exit=native.returncode,launcher_exit=launch_exit,python_outcome=outcome,actual_surface_calls=d.n)
  verify();state.update(status='complete',phase='generated_pending_root_review',finished_jst=now());write(OUT/'controller.json',state)
 except BaseException as e:
  write(OUT/'stop_requested.json',dict(reason=str(e),requested_jst=now(),own_run_only=True));state.update(status='failed',error=str(e),traceback=traceback.format_exc(),finished_jst=now());write(OUT/'controller.json',state);raise
if __name__=='__main__':main()
