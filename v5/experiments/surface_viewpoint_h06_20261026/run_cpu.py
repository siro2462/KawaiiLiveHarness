from common import *
import subprocess,traceback
from processor_cpu import load_processor
from driver_cpu import Driver
from viewpoint_runtime import render, apply_angle, AngleAttempts
from runtime import format_failure

def main():
 state=dict(status='running',phase='cpu_initialize',calls_completed=0,**obs(os.getpid()),started_jst=now());write(OUT/'controller.json',state)
 try:
  cfg=verify();assert read(OUT/'cpu_preflight.json')['status']=='pass'
  assert sha(OUT/'prepared_inputs.json')==read(OUT/'cpu_preflight.json')['prepared_inputs_sha256']
  for p in [BETA/'dependencies',GEMMA/'dependencies',GEMMA,MULTI]:sys.path.insert(0,str(p))
  proc,torch=load_processor()
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
   d=Driver(state,cfg,proc,torch,native);results=[];attempts=AngleAttempts(cfg['max_calls'])
   for pair in read(OUT/'cases.json'):
    case=pair['case'];angle=pair['viewpoint'];applied=apply_angle(case,angle);attempt_key=attempts.begin(case,angle);write(OUT/'angle_attempts.json',attempts.records);context=dict(viewpoint=angle,applied_viewpoint=applied,pair_id=pair['pair_id'],arm='assigned_angle',memory_id=pair['memory_id'],case=case,target_ids=[f['id'] for f in case['facts']],baseline_call_id=pair['source_call_id'],fixed_history=True)
    cid,out=d.call('surface',render(case,angle),pair['seed'],context)
    prepared=next(x for x in read(OUT/'prepared_inputs.json') if x['pair_id']==pair['pair_id'])['B']
    req=read(OUT/'requests'/(cid+'.json'));assert all(req[k]==v for k,v in prepared.items())
    reason=format_failure(out['body'],out['official_stop_reached'])
    row=dict(pair_id=pair['pair_id'],memory_id=pair['memory_id'],call_id=cid,case=case,body=out['body'],raw_output=out['raw_output'],format_reason=reason,delivered=reason is None,semantic_status='unverified',semantic_guard_used=False,history_updated=False)
    row.update(viewpoint=angle,applied_viewpoint=applied);write(OUT/'turns'/(cid+'.json'),row);results.append(row);attempts.finish(attempt_key,cid,row['delivered']);write(OUT/'angle_attempts.json',attempts.records)
    state.update(completed_pairs=len(results),text_delivered=sum(x['delivered'] for x in results));write(OUT/'controller.json',state)
   write(OUT/'requests/DONE.json',dict(calls=d.n,finished_jst=now()))
   while native.poll() is None:time.sleep(.5)
   launch_exit=child.wait(timeout=60);outcome=read(receipt);assert native.returncode==launch_exit==outcome['exit_code']==0
   state.update(native_exit=native.returncode,launcher_exit=launch_exit,python_outcome=outcome)
  verify();write(OUT/'probe_result.json',dict(rows=results,new_model_calls=d.n,baseline_reference_calls=1,common_first_reference_calls=1,new_planner_calls=0,new_guard_calls=0,training=0,real_tts=False,history_mode='each probe uses original A history; no B feedback'))
  state.update(status='complete',phase='generated_pending_root_review',finished_jst=now());write(OUT/'controller.json',state)
 except BaseException as e:
  write(OUT/'stop_requested.json',dict(reason=str(e),requested_jst=now(),own_run_only=True));state.update(status='failed',error=str(e),traceback=traceback.format_exc(),finished_jst=now());write(OUT/'controller.json',state);raise
if __name__=='__main__':main()
