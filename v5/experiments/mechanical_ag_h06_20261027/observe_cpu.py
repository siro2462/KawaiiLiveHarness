from common import *
from processor_cpu import load_processor,prepare
from contract_runtime import render as render_a
from ag_runtime import Control,render
from runtime import format_failure

def reference(pair,proc,torch):
 req=read(pair['baseline_request_path']);out=read(pair['baseline_output_path']);d=read(pair['baseline_delivery_path'])
 assert req['context']['case']==pair['case'] and req['user_prompt']==render_a(pair['case'])
 assert all(req[k]==v for k,v in prepare(proc,req['user_prompt']).items())
 assert out['request_sha256']==d['request_sha256']==sha(pair['baseline_request_path']) and d['output_sha256']==sha(pair['baseline_output_path'])
 assert proc.decode(out['output_ids'],skip_special_tokens=False)==out['raw_output'] and out['input_ids']==req['processor_fields']['input_ids'][0]
 assert proc.parse_response(out['raw_output'],prefix=torch.tensor([out['input_ids']]))==d['parsed']
 assert d['body']==pair['baseline_body'] and out['generation_config']==read(OUT/'protocol.json')['surface']['generation_config']
 return dict(pair=pair,request=req,output=out,delivery=d)

def main():
 cfg=verify();state=read(OUT/'controller.json') if (OUT/'controller.json').exists() else dict(status='startup_pending')
 worker=read(OUT/'inference/state.json') if (OUT/'inference/state.json').exists() else {};launch=read(OUT/'launch.json') if (OUT/'launch.json').exists() else {}
 result={k:state.get(k) for k in ['status','phase','calls_completed','actual_surface_calls','error']}
 for label,s in [('controller',state),('gpu',worker),('wrapper',launch)]:
  try:result[label+'_alive_same_identity']=abs(obs(s['pid'])['created_unix']-s['created_unix'])<.01
  except Exception:result[label+'_alive_same_identity']=False
  if (OUT/(label+'.python_outcome.json')).exists():result[label+'_python_exit']=read(OUT/(label+'.python_outcome.json'))['exit_code']
 if state['status']!='complete':print(json.dumps(result,ensure_ascii=False));return
 if not all((OUT/n).exists() for n in ['controller.python_outcome.json','gpu.python_outcome.json']):print(json.dumps(dict(status='receipts_pending')));return
 assert worker['status']=='complete' and state['native_exit']==state['launcher_exit']==0
 for label,s in [('controller',state),('gpu',worker)]:
  receipt=read(OUT/(label+'.python_outcome.json'));assert receipt['exit_code']==0 and receipt['pid']==s['pid'] and receipt['script']==str(HERE/('run_cpu.py' if label=='controller' else 'gpu_worker.py'))
 proc,torch=load_processor();initial=read(OUT/'initial_case.json');catalog=read(OUT/'catalog.json');arms=read(OUT/'arms.json');saved=read(OUT/'ag_result.json');packets=[];entries=[];count=0
 assert saved['completed_arms']==7
 for spec,arm_result in zip(arms,saved['arms']):
  assert arm_result['arm']==spec;c=Control(initial,catalog,spec);turns=[]
  for n,row in enumerate(arm_result['records'],1):
   count+=1;cid=f'R{count:04}';choice=c.choose();before=c.snapshot()
   assert row['call_id']==cid and row['choice']==choice and row['control_before']==before and row['arm']==spec['id']
   prompt=render(c,choice);context=dict(experiment=cfg['experiment'],arm=spec['id'],turn=n,choice=choice,control_before=before,source_case=initial,candidates=c.candidates());c.begin(choice)
   reqp=OUT/'requests'/(cid+'.json');outp=OUT/'inference'/(cid+'.output.json');req=read(reqp);out=read(outp);d=read(OUT/'deliveries'/(cid+'.json'))
   assert req['context']==context and req['seed']==20260925 and req['role']=='surface' and req['user_prompt']==prompt
   assert all(req[k]==v for k,v in prepare(proc,prompt).items())
   assert out['request_sha256']==d['request_sha256']==sha(reqp) and d['output_sha256']==sha(outp)
   assert out['input_ids']==req['processor_fields']['input_ids'][0] and proc.decode(out['output_ids'],skip_special_tokens=False)==out['raw_output']
   assert proc.parse_response(out['raw_output'],prefix=torch.tensor([out['input_ids']]))==d['parsed']
   assert out['generation_config']==cfg['surface']['generation_config'] and out['adapter_disabled'] is False and out['new_model_generation'] is True
   journal=OUT/'inference'/(cid+'_token_journal.jsonl');assert sha(journal)==out['journal_sha256'] and sum([x['ids'] for x in rows(journal)],[])==out['output_ids']
   assert d['body']==row['body'] and d['raw_output']==row['raw_output']==out['raw_output']
   reason=c.finish(cid,row['body'],format_failure(row['body'],out['official_stop_reached']))
   assert row['format_reason']==reason and row['delivered']==(reason is None) and row['control_after']==c.snapshot() and row['semantic_status']=='unverified'
   if n>1 and arm_result['records'][n-2]['delivered']:assert before['recent'][-1]['text']==arm_result['records'][n-2]['body']
   assert len(out['input_ids'])+384<8192
   turns.append(dict(request=req,output=out,delivery=d,row=row));entries.append(dict(call_id=cid,arm=spec['id'],view_id=choice['view']['id'],input_tokens=len(out['input_ids']),output_tokens=len(out['output_ids']),eos=out['official_stop_reached'],request_sha256=sha(reqp),output_sha256=sha(outp)))
  assert c.choose() is None and c.snapshot()==arm_result['final_control']==read(OUT/'arm_states'/(spec['id']+'.json'))
  packets.append(dict(arm=spec,turns=turns,final_control=c.snapshot()))
 assert 7<=count<=28 and count==saved['actual_surface_calls']==state['calls_completed']==worker['calls']==read(OUT/'requests/DONE.json')['calls']
 assert len(list((OUT/'requests').glob('R*.json')))==count and len(list((OUT/'inference').glob('identity_*.json')))==1
 identity=read(OUT/'inference/identity_001.json');assert identity['role']=='instruct' and identity['adapter_tensors_loaded_exact'] and identity['adapter_sha256']==cfg['surface']['adapter_sha256'] and not identity['training']
 first=reference(read(OUT/'reference/common_first.json'),proc,torch);later=reference(read(OUT/'reference/baseline_later.json'),proc,torch)
 assert initial['history']==first['pair']['case']['history'] and later['pair']['case']['history'][-1]['text']==first['delivery']['body']
 write(OUT/'review_packet.json',dict(baseline=[first,later],arms=packets,initial_case=initial,catalog=catalog,references=read(OUT/'reference/source_pairs.json'),scope='cumulative designer-defined A-G, fixed same H06 information, literal cues not semantic certification, human0'))
 audit=dict(status='pass',scope='technical integrity only, not semantic quality',new_surface_calls=count,saved_baseline_calls=2,arms=7,planner_calls=0,guard_calls=0,training=0,quality_retries=0,memory_writes=0,current_exit0=True,actual_text_feedback_checked=True,all_inputs_exact=True,entries=entries,review_packet_sha256=sha(OUT/'review_packet.json'))
 verify();write(OUT/'technical_audit.json',audit);print(json.dumps({k:v for k,v in audit.items() if k!='entries'},ensure_ascii=False))
if __name__=='__main__':main()
