from common import *
import copy,subprocess,traceback
from runtime import *
from driver_cpu import Driver
from continuous_policy import *

def rollout(a,d,cfg,es,state):
 from planner_delivery import resolve
 from contract_runtime import render
 eligible=set(cfg['eligible_memory_ids']);records=[];plans=[];selections=[];completed=[]
 m=None;p=None;previous_memory=None;previous_plan=None;shared=[];summary='';chars=0;stop=None
 while chars<cfg['target_chars']:
  if m is None:
   m,traces=choose(a,'\n'.join(x['text'] for x in es.recent()),eligible,len(selections)+1)
   selection=dict(index=len(selections)+1,selected_memory=m,traces=traces,source_fact_promotion=False)
   selections.append(selection);write(OUT/'selections'/f'S{len(selections):02}.json',selection)
   if m is None:stop='alpha_no_supported_unmentioned_candidate';break
   assert m['id'] not in [q['memory_id'] for q in completed]
   p=Progress(m,None);previous_plan=None;shared,summary=relation(previous_memory,m)
  if len(records)>=cfg['max_surface_calls']:stop='surface_budget';break
  recent='\n'.join(x['text'] for x in es.recent());request,context=make_planner_request(m,recent,previous_plan,p.snapshot())
  before_plan=p.snapshot();pcid,raw=d.call('planner',request,cfg['seeds'][0],context)
  entry=dict(call_id=pcid,turn=len(records)+1,memory_id=m['id'],planner_input=context['planner_input'],request=request,raw=raw,before=before_plan)
  resolution=resolve(raw['text'],[m['id']]);plan=resolution['plan'];entry.update(resolution)
  if resolution['format_fallback']:
   es.append('planner_format_fallback',dict(call_id=pcid,error=resolution['error'],policy=resolution['fallback_policy'],source_fact_promotion=False,quality_retry=False))
  p.reorder(plan);entry['after_mapping']=p.snapshot();write(OUT/'plans'/(pcid+'.json'),entry);plans.append(entry)
  ids=p.focus('C');h=history(es);case=surface_case(m,ids,h,shared,summary,f'L-T{len(records)+1:03}')
  before=p.snapshot();p.presented(ids)
  cid,out=d.call('surface',render(case),cfg['seeds'][0],dict(rollout_id='L',turn=len(records)+1,memory_id=m['id'],target_ids=ids,case=case,planner_call_id=pcid))
  body=out['body'];reason=format_failure(body,out['official_stop_reached']);ev=None
  if reason:es.append('format_held',dict(call_id=cid,body=body,reason=reason,no_semantic_judge=True))
  else:ev=es.append('text_delivery_confirmed',dict(call_id=cid,text=body,memory_id=m['id'],actual_audio=False,semantic_status='unverified',source_fact_promotion=False))
  p.finish(ids,body,ev);observe_alpha(a,m,p,ev is not None)
  row=dict(turn=len(records)+1,call_id=cid,planner_call_id=pcid,memory_id=m['id'],source_memory=m,source_facts=facts_for(m),case=case,body=body,raw_output=out['raw_output'],delivered=ev is not None,format_reason=reason,repetition_log=repetition_observation(body,h),event_seq=ev,before=before,after=p.snapshot(),plan=plan,planner_syntax_valid=resolution['syntax_valid'],planner_format_fallback=resolution['format_fallback'],planner_error=resolution['error'],semantic_status='unverified',semantic_guard_used=False)
  records.append(row);write(OUT/'turns'/f'T{len(records):03}.json',row)
  chars=sum(count_chars(r['body']) for r in records if r['delivered'])
  (OUT/'speech.txt').write_text('\n\n'.join(r['body'] for r in records if r['delivered'])+'\n',encoding='utf-8')
  write(OUT/'continuous_partial.json',dict(records=records,plans=plans,selections=selections,completed_memories=completed,delivered_chars=chars))
  state.update(surface_candidates=len(records),text_delivered=sum(r['delivered'] for r in records),delivered_chars=chars,planner_calls=len(plans),planner_format_fallbacks=sum(x['format_fallback'] for x in plans));write(OUT/'controller.json',state)
  previous_plan=plan
  if not p.pending():completed.append(p.snapshot());previous_memory=m;m=None;p=None
  if chars>=cfg['target_chars']:stop='target_chars_reached';break
  if m is None and len(completed)==len(eligible):stop='all_eligible_source_presented';break
 if stop is None:stop='target_chars_reached'
 result=dict(records=records,plans=plans,selections=selections,completed_memories=completed,unfinished_progress=p.snapshot() if p else None,delivered_chars=chars,estimated_minutes=chars/cfg['chars_per_minute_assumption'],target_chars=cfg['target_chars'],target_met=chars>=cfg['target_chars'],stop_reason=stop,planner_format_fallbacks=sum(x['format_fallback'] for x in plans),prefix_reused_calls=len(cfg['prefix_reuse']),new_model_calls=d.n-len(cfg['prefix_reuse']),semantic_guard_calls=0,actual_tts=False,human_quality_labels=0,quality_retries=0)
 write(OUT/'continuous_result.json',result);return result

def main():
 state=dict(status='running',phase='cpu_initialize',calls_completed=0,**obs(os.getpid()),started_jst=now());write(OUT/'controller.json',state)
 try:
  cfg=verify()
  for path in [BETA/'dependencies',GEMMA/'dependencies',GEMMA,MULTI,HERE/'vendor']:sys.path.insert(0,str(path))
  from alpha import Alpha
  a=Alpha(OUT/'live_alpha.sqlite');a.populate(HERE/'sources/v1_2.zip',HERE/'sources/fixtures_20.json');initial=signature(a);write(OUT/'memory_invariants.json',initial)
  sys.path.insert(0,str(CPU_DEPS));import torch
  from transformers import AutoProcessor
  assert torch.__version__.endswith('+cpu') and not torch.cuda.is_available()
  proc=AutoProcessor.from_pretrained(str(MULTI/'models'/cfg['surface']['model_key']),local_files_only=True,trust_remote_code=False)
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
   es=EventStore(OUT/'events.sqlite');d=Driver(state,cfg,proc,torch,native)
   result=rollout(a,d,cfg,es,state);es.close();assert signature(a)==initial;a.close()
   write(OUT/'requests/DONE.json',dict(calls=d.n,finished_jst=now()))
   while native.poll() is None:time.sleep(.5)
   launch_exit=child.wait(timeout=60);outcome=read(receipt);assert native.returncode==launch_exit==outcome['exit_code']==0
   state.update(native_exit=native.returncode,launcher_exit=launch_exit,python_outcome=outcome)
  verify();state.update(status='complete',phase='generated_pending_root_review',stop_reason=result['stop_reason'],target_met=result['target_met'],finished_jst=now());write(OUT/'controller.json',state)
 except BaseException as e:
  write(OUT/'stop_requested.json',dict(reason=str(e),requested_jst=now(),own_run_only=True));state.update(status='failed',error=str(e),traceback=traceback.format_exc(),finished_jst=now());write(OUT/'controller.json',state);raise
if __name__=='__main__':main()
