from common import *
import subprocess,traceback
from processor_cpu import load_processor
from driver_cpu import Driver
from stripe_runtime import schedule,render,recent,format_reason,validate_steps

def rollout(d,cfg):
 steps=read(OUT/'steps32.json');memory=read(OUT/'legacy_memory.json');nodes=read(OUT/'memory_h06.json')['nodes'];validate_steps(steps,nodes);results=[]
 for spec in schedule(steps):
  history=read(OUT/'initial_history.json');records=[];presented=[];stop=None
  for turn,group in enumerate(spec['groups'],1):
   prompt,payload=render(group,history,memory,steps);before=dict(history=recent(history),presented_step_ids=list(presented),semantic_status='unverified')
   context=dict(experiment=cfg['experiment'],arm=spec['arm'],turn=turn,group=group,payload=payload,before=before,source_inputs_sha256=sha(OUT/'steps32.json'),fixed_sequence=True,adaptive_reselection=False)
   cid,out=d.call('surface',prompt,cfg['surface_seed'],context);reason=format_reason(out['body'],out['official_stop_reached'])
   ids=[s['index'] for s in group.get('steps',[])];presented.extend(ids)
   if reason is None:history.append(dict(text=out['body'],memory_id='H06',origin='offline text delivered, semantically unverified'))
   row=dict(call_id=cid,arm=spec['arm'],turn=turn,group=group,payload=payload,before=before,after=dict(history=recent(history),presented_step_ids=list(presented),semantic_status='unverified'),body=out['body'],raw_output=out['raw_output'],delivered=reason is None,format_reason=reason,presented_not_semantically_executed=ids,semantic_status='unverified')
   records.append(row);write(OUT/'turns'/(cid+'.json'),row);write(OUT/'arm_states'/(spec['arm']+'.json'),dict(records=records,history=history,stop_reason=reason))
   if reason:stop='format_held_no_retry';break
   if len(out['body'])>800 and turn<len(spec['groups']):stop='last_text_exceeds_history_window';break
  results.append(dict(arm=spec['arm'],records=records,stop_reason=stop or 'fixed_schedule_exhausted',unattempted_groups=len(spec['groups'])-len(records),semantic_status='unverified'))
  write(OUT/'abc_result.json',dict(arms=results,completed_arms=len(results),actual_surface_calls=d.n,planner_calls=0,guard_calls=0,training=0,quality_retries=0,memory_writes=0))
 return read(OUT/'abc_result.json')

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
   d=Driver(state,cfg,proc,torch,native);result=rollout(d,cfg);assert 3<=d.n<=11 and result['completed_arms']==3
   prepared=read(OUT/'prepared_inputs.json')['initial_by_arm']
   for item in result['arms']:
    req=read(OUT/'requests'/(item['records'][0]['call_id']+'.json'));assert all(req[k]==v for k,v in prepared[item['arm']].items())
   write(OUT/'requests/DONE.json',dict(calls=d.n,finished_jst=now()))
   while native.poll() is None:time.sleep(.5)
   launch_exit=child.wait(timeout=60);outcome=read(receipt);assert native.returncode==launch_exit==outcome['exit_code']==0
   state.update(native_exit=native.returncode,launcher_exit=launch_exit,python_outcome=outcome,actual_surface_calls=d.n)
  verify();state.update(status='complete',phase='generated_pending_root_review',finished_jst=now());write(OUT/'controller.json',state)
 except BaseException as e:
  write(OUT/'stop_requested.json',dict(reason=str(e),requested_jst=now(),own_run_only=True));state.update(status='failed',error=str(e),traceback=traceback.format_exc(),finished_jst=now());write(OUT/'controller.json',state);raise
if __name__=='__main__':main()
