from common import *
import copy,subprocess,traceback
from runtime import *
class Driver:
 def __init__(self,state,cfg,proc,torch,native):self.state=state;self.cfg=cfg;self.proc=proc;self.torch=torch;self.native=native;self.n=0
 def call(self,role,prompt,seed,context):
  if role not in ('surface','planner'):raise ValueError('Semantic Guard forbidden in this experiment')
  self.n+=1
  if self.n>self.cfg['max_calls']:raise ValueError('Bounded call budget exhausted')
  cid=f'R{self.n:04}';req=dict(call_id=cid,role=role,seed=seed,context=context)
  if role=='planner':req.update(prompt=prompt['prompt'],recent=prompt['recent'],candidate_ids=prompt['candidate_ids'])
  else:
   messages=[dict(role='user',content=[dict(type='text',text=prompt)])];kw=dict(tokenize=True,return_dict=True,return_tensors='pt',add_generation_prompt=True,enable_thinking=False)
   f=self.proc.apply_chat_template(messages,**kw);ids=f['input_ids'][0].tolist();dec=self.proc.decode(ids,skip_special_tokens=False)
   assert self.proc.tokenizer.encode(dec,add_special_tokens=False)==ids and len(ids)+384<8192
   req.update(user_prompt=prompt,messages=messages,template_kwargs=kw,processor_fields={k:v.tolist() for k,v in f.items()},decoded_input=dec)
  path=OUT/'requests'/(cid+'.json');write(path,req);self.state.update(phase='waiting_output',call_id=cid,role=role,calls_submitted=self.n);write(OUT/'controller.json',self.state);dest=OUT/'inference'/(cid+'.output.json');deadline=time.monotonic()+2400
  if self.n<=len(self.cfg['prefix_reuse']):
   cache=self.cfg['prefix_reuse'][self.n-1];old_req=read(cache['request']);old_out=read(cache['output'])
   assert sha(cache['request'])==cache['request_sha256'] and sha(cache['output'])==cache['output_sha256']
   assert {k:v for k,v in req.items() if k!='call_id'}=={k:v for k,v in old_req.items() if k!='call_id'},'Prefix full input/context mismatch; do not regenerate silently'
   assert old_out['request_sha256']==sha(cache['request']) and old_out['role']==role
   rec=copy.deepcopy(old_out);rec.update(call_id=cid,request_sha256=sha(path),seconds=0.0,source_generation_seconds=old_out['seconds'],new_model_generation=False,reuse=dict(source_request=cache['request'],source_output=cache['output'],source_output_sha256=cache['output_sha256'],full_input_context_identical=True,previous_process_exit=1,new_model_generation=False))
   if role=='surface':
    import shutil
    jp=Path(cache['output']).with_name(old_req['call_id']+'_token_journal.jsonl');assert sha(jp)==old_out['journal_sha256'];shutil.copyfile(jp,OUT/'inference'/(cid+'_token_journal.jsonl'))
   write(dest,rec)
  while not dest.exists():
   if self.native.poll() is not None:raise RuntimeError('GPU native exited before output')
   if time.monotonic()>deadline:raise TimeoutError('Inference deadline exceeded')
   time.sleep(.5)
  rec=read(dest);assert rec['request_sha256']==sha(path)
  if role=='surface':
   ids=req['processor_fields']['input_ids'][0];assert rec['input_ids']==ids and self.proc.decode(rec['output_ids'],skip_special_tokens=False)==rec['raw_output']
   parsed=self.proc.parse_response(rec['raw_output'],prefix=self.torch.tensor([ids]));assert parsed.get('role')=='assistant' and isinstance(parsed.get('content'),str)
   rec.update(body=parsed['content'],parsed=parsed);write(OUT/'deliveries'/(cid+'.json'),dict(call_id=cid,body=rec['body'],raw_output=rec['raw_output'],parsed=parsed,request_sha256=sha(path),output_sha256=sha(dest)))
  self.state['calls_completed']=self.n;write(OUT/'controller.json',self.state);return cid,rec
 def replan(self,memory,recent,seed,previous,progress):
  from planner_policy import planner_prompt,parse_plan
  from context_runtime import planner_input
  src=dict(id=memory['id'],body=memory['body']);inp=planner_input(recent,[src],previous,src,'post_actual_offline_text_delivery')
  inp['current_state'].update(progress=progress,unused_fact_ids=progress['pending_target_ids'],external_event=None,progress_warning='提示済み/模擬再生済みは意味確認済みではない。再提示せず未提示のFactから次の焦点を選ぶ。')
  request=dict(prompt=planner_prompt(inp),recent=inp['recent'],candidate_ids=[memory['id']]);cid,rec=self.call('planner',request,seed,dict(memory_id=memory['id'],reason='actual_text_feedback',planner_input=inp))
  plan=parse_plan(rec['text'],[memory['id']]);return dict(call_id=cid,plan=plan,planner_input=inp,semantic_validation=False,syntax_valid=True)
def alpha_signature(a):return {t:digest(json.dumps([list(r) for r in a.con.execute('SELECT * FROM '+t+' ORDER BY 1,2,3')],ensure_ascii=False)) for t in ('memories','links')}
def main():
 state=dict(status='running',phase='cpu_preflight',calls_completed=0,rollouts_complete=0,**obs(os.getpid()),started_jst=now());write(OUT/'controller.json',state);child=None
 try:
  cfg=verify()
  for path in [BETA/'dependencies',GEMMA/'dependencies',GEMMA,MULTI,HERE/'vendor']:sys.path.insert(0,str(path))
  from alpha import Alpha
  from planner_policy import planner_prompt,parse_plan
  from context_runtime import planner_input
  a=Alpha(OUT/'live_alpha.sqlite');a.populate(HERE/'sources/v1_2.zip',HERE/'sources/fixtures_20.json');initial=alpha_signature(a);write(OUT/'memory_invariants.json',initial)
  # Exactly the first syntactically valid original shared-initial responses, never quality-selected.
  initial_plans={}
  for mid,cache in cfg['initial_plan_cache'].items():
   m=a.get(mid);src=dict(id=mid,body=m['body']);inp=planner_input('',[src],None,src,'shared_initial_plan');inp['current_state'].update(progress=None,unused_fact_ids=[f['id'] for f in facts_for(m)],external_event=None)
   req=read(cache['request']);out=read(cache['output']);assert sha(cache['request'])==cache['request_sha256'] and sha(cache['output'])==cache['output_sha256']
   assert req['prompt']==planner_prompt(inp) and req['recent']==inp['recent'] and req['candidate_ids']==[mid] and req['seed']==cfg['seeds'][0]
   assert out['request_sha256']==sha(cache['request']) and out['strict_schema_valid'] and out['official_stop_reached']
   initial_plans[mid]=parse_plan(out['text'],[mid]);write(OUT/'plans'/(mid+'.cached_initial.json'),dict(plan=initial_plans[mid],provenance=cache,input_fields_identical=True,new_model_call=False,semantic_gate_used=False))
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
   native=observer_type()(actual['pid'],actual);write(OUT/'inference/observer_ready.json',dict(worker_pid=actual['pid'],worker_created_unix=actual['created_unix'],observer_pid=os.getpid()));state.update(actual_gpu=actual);write(OUT/'controller.json',state);d=Driver(state,cfg,proc,torch,native)
   from contract_runtime import render
   results=[]
   for job in cfg['rollout_schedule']:
    arm=job['condition'];seed=job['seed'];rid=job['rollout_id'];folder=OUT/'rollouts'/rid;folder.mkdir();es=EventStore(folder/'events.sqlite');records=[];snapshots=[];turn=0;replans=0
    for mi,mid in enumerate(cfg['series'][job['series']]):
     m=a.get(mid);plan=copy.deepcopy(initial_plans[mid]);p=Progress(m,plan);cue=a.cue(rid,'\n'.join(x['text'] for x in es.recent()) or m['title'],event_id=rid+'-'+mid)
     es.append('memory_selection',dict(selected=mid,alpha_proposal=cue['proposal'],paired_fixture=True,source_fact_promotion=False))
     previous=cfg['series'][job['series']][mi-1] if mi else None;shared=sorted((set(a.get(previous)['tags'])&set(m['tags']))-{'昔','朝','夜','青','赤','白','黒'}) if previous else []
     summary='共通要素「'+'、'.join(shared)+'」を参考に別の経験へ移る。同日や因果にまとめない。' if shared else '別の話題へ移る。根拠のない共通経験や因果を作らない。' if previous else '同じ出来事の未提示の続き。'
     if mi==1:es.append('external_comment',dict(text='続きも聞かせて',synthetic=True,source_fact=False))
     replanned_here=False
     while p.pending():
      ids=p.focus(arm);history=[dict(text=x['text'],memory_id=x['memory_id'],origin='offline text delivered, semantically unverified') for x in es.recent()];case=surface_case(m,ids,history,shared,summary,rid+f'-T{turn+1:02}');before=p.snapshot();p.presented(ids)
      cid,rec=d.call('surface',render(case),seed,dict(rollout_id=rid,turn=turn+1,memory_id=mid,target_ids=ids,case=case));body=rec['body'];reason=format_failure(body,rec['official_stop_reached']);rep=repetition_observation(body,history);ev=None
      if reason:es.append('format_held',dict(call_id=cid,body=body,reason=reason,no_semantic_judge=True))
      else:ev=es.append('text_delivery_confirmed',dict(call_id=cid,text=body,memory_id=mid,actual_audio=False,semantic_status='unverified',source_fact_promotion=False))
      p.finish(ids,body,ev);turn+=1;row=dict(turn=turn,call_id=cid,memory_id=mid,source_facts=facts_for(m),case=case,body=body,raw_output=rec['raw_output'],delivered=ev is not None,format_reason=reason,repetition_log=rep,event_seq=ev,before=before,after=p.snapshot(),semantic_status='pending_offline_review',semantic_guard_used=False,plan=plan)
      records.append(row);write(folder/f'T{turn:02}.json',row)
      # Two bounded actual-text feedback opportunities, not a quality retry loop.
      if arm=='C' and mi<2 and ev is not None and p.pending() and not replanned_here:
       nb=d.replan(m,'\n'.join(x['text'] for x in es.recent()),seed,plan,p.snapshot());plan=nb['plan'];p.reorder(plan);replanned_here=True;replans+=1;write(folder/f'T{turn:02}.replan.json',dict(nb,after_mapping=p.snapshot()));es.append('post_delivery_replan',dict(call_id=nb['call_id'],pending_target_ids=p.pending(),mapping=p.mapping,source_fact_promotion=False))
      s=a.state(rid);s['thread'].update(current_memory_id=mid,current_topic=m['title'],beat_index=0,next_beat=None);s['event_seq']+=1;a._update_activation(s,{mid:.72} if ev is not None else {});a._save(rid,s,'offline_text_observation',dict(call_id=cid,actual_tts=False,semantic_coverage_unverified=True,source_fact_promotion=False))
      if turn>20:raise RuntimeError('Turn bound exceeded')
     snapshots.append(p.snapshot());s=a.state(rid);s['thread']['open_threads'].append(dict(memory_id=mid,runtime_status='presentation_exhausted_semantically_unverified'));s['thread'].update(current_memory_id=None,current_topic=None,beat_index=0,next_beat=None);s['event_seq']+=1;a._save(rid,s,'presentation_topic_released',dict(memory_id=mid,verified_coverage=False))
    assert replans<=2 and alpha_signature(a)==initial
    summary=dict(rollout_id=rid,condition=arm,series=job['series'],seed=seed,turns=turn,replans=replans,records=records,progress=snapshots,semantic_guard_calls=0,actual_tts=False);write(folder/'result.json',summary);es.close();results.append(summary);state['rollouts_complete']+=1;write(OUT/'controller.json',state)
   write(OUT/'all_rollouts.json',results);write(OUT/'requests/DONE.json',dict(calls=d.n,finished_jst=now()))
   while native.poll() is None:time.sleep(.5)
   launch_exit=child.wait(timeout=60);outcome=read(receipt);assert native.returncode==launch_exit==outcome['exit_code']==0
   state.update(native_exit=native.returncode,launcher_exit=launch_exit,python_outcome=outcome)
  assert alpha_signature(a)==initial;a.close();verify();state.update(status='complete',phase='generated_pending_root_review',finished_jst=now());write(OUT/'controller.json',state)
 except BaseException as exc:
  write(OUT/'stop_requested.json',dict(reason=str(exc),requested_jst=now(),own_run_only=True));state.update(status='failed',error=str(exc),traceback=traceback.format_exc(),finished_jst=now());write(OUT/'controller.json',state);raise
if __name__=='__main__':main()
