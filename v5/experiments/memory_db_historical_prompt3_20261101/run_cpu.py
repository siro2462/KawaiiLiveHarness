from common import *
import subprocess,traceback
from processor_cpu import load_processor
from driver_cpu import Driver
from stripe_runtime import render_step,make_context,recent,format_reason,groups as operation_groups
from cpu_selector import select

def rollout(d,cfg):
 records=[];groups=[];schedule=read(OUT/'unit_schedule.json')
 for sample in read(OUT/'samples.json'):
  chosen=select(sample,cfg['engine_seed']);assert chosen==sample['selection']==read(OUT/'cpu_selections.json')[sample['id']]
  prior=[]
  for index in range(len(operation_groups(sample))):
   assert d.n<len(schedule) and schedule[d.n]==dict(unit_key=sample['id']+f':G{index+1:02}',sample_id=sample['id'],unit_index=index+1)
   prompt,payload=render_step(sample,index,prior);context=make_context(sample,index,prior,payload)
   cid,out=d.call('surface',prompt,cfg['surface_seed'],context)
   reason=format_reason(out['body'],out['official_stop_reached'])
   row=dict(call_id=cid,sample_id=sample['id'],unit_index=index+1,operations=operation_groups(sample)[index],source_step_indices=payload['generation_scope']['source_step_indices'],body=out['body'],raw_output=out['raw_output'],eos=out['official_stop_reached'],delivered=reason is None,format_reason=reason,semantic_status='unverified',before_history=payload['history'],attempted_not_semantically_executed=True)
   prior.append(row);row['after_history']=recent(prior)
   records.append(row);write(OUT/'turns'/(cid+'.json'),row)
   state=dict(records=records,groups=groups,completed_operations=sum(len(r['operations']) for r in records),completed_samples=len(groups),actual_surface_calls=d.n,planner_calls=0,guard_calls=0,training=0,quality_retries=0,memory_writes=0)
   write(OUT/'surface_result.json',state)
  groups.append(dict(sample_id=sample['id'],records=prior,full_text='\n'.join(r['body'] for r in prior if r['delivered']),attempted_units=len(prior),semantic_status='unverified'))
  state.update(groups=groups,completed_samples=len(groups));write(OUT/'surface_result.json',state)
 assert len(records)==d.n==cfg['max_calls']==11 and len(groups)==3
 return state

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
   native=observer_type()(actual['pid'],actual);write(OUT/'inference/observer_ready.json',dict(worker_pid=actual['pid'],worker_created_unix=actual['created_unix'],observer_pid=os.getpid()))
   state.update(actual_gpu=actual);write(OUT/'controller.json',state)
   d=Driver(state,cfg,proc,torch,native);result=rollout(d,cfg);assert d.n==cfg['max_calls'] and result['completed_samples']==3
   write(OUT/'requests/DONE.json',dict(calls=d.n,finished_jst=now()))
   while native.poll() is None:time.sleep(.5)
   launch_exit=child.wait(timeout=60);outcome=read(receipt);assert native.returncode==launch_exit==outcome['exit_code']==0
   state.update(native_exit=native.returncode,launcher_exit=launch_exit,python_outcome=outcome,actual_surface_calls=d.n)
  verify();state.update(status='complete',phase='generated_pending_root_review',finished_jst=now());write(OUT/'controller.json',state)
 except BaseException as e:
  write(OUT/'stop_requested.json',dict(reason=str(e),requested_jst=now(),own_run_only=True));state.update(status='failed',error=str(e),traceback=traceback.format_exc(),finished_jst=now());write(OUT/'controller.json',state);raise
if __name__=='__main__':main()
