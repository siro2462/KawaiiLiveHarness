from common import *
from processor_cpu import load_processor,prepare
from contract_runtime import render as render_a
from role_runtime import RoleControl,render
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
 result={k:state.get(k) for k in ['status','phase','calls_completed','actual_surface_calls','stop_reason','error']}
 for label,s in [('controller',state),('gpu',worker),('wrapper',launch)]:
  try:result[label+'_alive_same_identity']=abs(obs(s['pid'])['created_unix']-s['created_unix'])<.01
  except Exception:result[label+'_alive_same_identity']=False
  if (OUT/(label+'.python_outcome.json')).exists():result[label+'_python_exit']=read(OUT/(label+'.python_outcome.json'))['exit_code']
 if state['status']!='complete':print(json.dumps(result,ensure_ascii=False));return
 if not all((OUT/n).exists() for n in ['controller.python_outcome.json','gpu.python_outcome.json']):print(json.dumps(dict(status='receipts_pending')));return
 assert worker['status']=='complete' and state['native_exit']==state['launcher_exit']==0
 for label,s in [('controller',state),('gpu',worker)]:
  receipt=read(OUT/(label+'.python_outcome.json'));assert receipt['exit_code']==0 and receipt['pid']==s['pid']
  assert receipt['script']==str(HERE/('run_cpu.py' if label=='controller' else 'gpu_worker.py'))
 proc,torch=load_processor();base=read(OUT/'baseline_case.json');roles=read(OUT/'roles.json')
 saved=read(OUT/'controlled_result.json');control=RoleControl(base['case'],roles,cfg['max_calls']);packet=[];entries=[]
 for n,row in enumerate(saved['records'],1):
  cid=f'R{n:04}';role=control.next_role();assert role is not None and row['role_spec']==role
  before=control.snapshot();case=control.case();assert row['control_before']==before and row['case']==case
  control.begin(role['id'])
  reqp=OUT/'requests'/(cid+'.json');outp=OUT/'inference'/(cid+'.output.json');req=read(reqp);out=read(outp);d=read(OUT/'deliveries'/(cid+'.json'))
  expected_context=dict(experiment=cfg['experiment'],memory_id='H06',target_ids=[f['id'] for f in case['facts']],case=case,role_spec=role,control_before=before,initial_case_sha256=sha(OUT/'baseline_case.json'),turn=n)
  assert req['context']==expected_context and req['seed']==base['seed']==20260925 and req['role']=='surface'
  assert req['user_prompt']==render(case,role) and all(req[k]==v for k,v in prepare(proc,render(case,role)).items())
  assert out['request_sha256']==d['request_sha256']==sha(reqp) and d['output_sha256']==sha(outp)
  assert out['input_ids']==req['processor_fields']['input_ids'][0] and proc.decode(out['output_ids'],skip_special_tokens=False)==out['raw_output']
  assert proc.parse_response(out['raw_output'],prefix=torch.tensor([out['input_ids']]))==d['parsed']
  assert out['generation_config']==cfg['surface']['generation_config'] and out['adapter_disabled'] is False and out['new_model_generation'] is True
  journal=OUT/'inference'/(cid+'_token_journal.jsonl');assert sha(journal)==out['journal_sha256'] and sum([x['ids'] for x in rows(journal)],[])==out['output_ids']
  assert d['body']==row['body'] and d['raw_output']==row['raw_output']==out['raw_output']
  reason=control.finish(cid,row['body'],format_failure(row['body'],out['official_stop_reached']))
  assert row['format_reason']==reason and row['delivered']==(reason is None) and row['control_after']==control.snapshot()
  assert row['semantic_status']=='unverified' and not row['semantic_guard_used'] and not row['source_fact_progress_updated']
  if n==1:assert case==base['case']
  if n>1:assert case['history'][-1]['text']==saved['records'][n-2]['body']
  assert len(out['input_ids'])+384<8192
  packet.append(dict(request=req,output=out,delivery=d,row=row));entries.append(dict(call_id=cid,role_id=role['id'],input_tokens=len(out['input_ids']),output_tokens=len(out['output_ids']),official_stop_reached=out['official_stop_reached'],format_reason=reason,request_sha256=sha(reqp),output_sha256=sha(outp)))
 assert control.next_role() is None and saved['final_control']==control.snapshot()==read(OUT/'role_state.json')
 count=len(packet);assert 1<=count<=2 and count==saved['actual_surface_calls']==state['calls_completed']==worker['calls']==read(OUT/'requests/DONE.json')['calls']
 assert len(list((OUT/'requests').glob('R*.json')))==count
 identity=read(OUT/'inference/identity_001.json');assert identity['role']=='instruct' and identity['adapter_tensors_loaded_exact'] and identity['adapter_sha256']==cfg['surface']['adapter_sha256'] and not identity['training']
 assert len(list((OUT/'inference').glob('identity_*.json')))==1
 a=reference(base,proc,torch);first=reference(read(OUT/'reference/common_first.json'),proc,torch)
 assert first['delivery']['body']==base['case']['history'][-1]['text']
 write(OUT/'review_packet.json',dict(baseline=a,controlled_turns=packet,common_first=first,roles=roles,final_control=control.snapshot(),references=read(OUT/'reference/source_pairs.json'),scope='bounded designer roles, actual text feedback, literal cue tracking only; known-condition designer AI; human0'))
 audit=dict(status='pass',scope='technical integrity only, not semantic quality',new_surface_calls=count,baseline_saved_calls=1,common_first_saved_calls=1,planner_calls=0,guard_calls=0,training=0,quality_retries=0,actual_tts=False,memory_writes=0,current_exit0=True,initial_case_exact=True,source_facts_fixed=True,actual_text_feedback=True if count>1 else 'not_exercised_single_call',stop_reason=control.stop_reason,entries=entries,review_packet_sha256=sha(OUT/'review_packet.json'))
 verify();write(OUT/'technical_audit.json',audit);print(json.dumps({k:v for k,v in audit.items() if k!='entries'},ensure_ascii=False))
if __name__=='__main__':main()
