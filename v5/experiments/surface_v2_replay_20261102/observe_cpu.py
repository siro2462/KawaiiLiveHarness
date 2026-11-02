from common import *
from processor_cpu import load_processor,prepare
from prompt_v2 import render as render_b
from contract_runtime import render as render_a
from runtime import format_failure

def main():
 cfg=verify();state=read(OUT/'controller.json') if (OUT/'controller.json').exists() else dict(status='startup_pending');worker=read(OUT/'inference/state.json') if (OUT/'inference/state.json').exists() else {}
 result={k:state.get(k) for k in ['status','phase','calls_completed','completed_pairs','text_delivered','error']}
 launch=read(OUT/'launch.json') if (OUT/'launch.json').exists() else {}
 for label,s in [('controller',state),('gpu',worker),('wrapper',launch)]:
  try:result[label+'_alive_same_identity']=abs(obs(s['pid'])['created_unix']-s['created_unix'])<.01
  except Exception:result[label+'_alive_same_identity']=False
  receipt=OUT/(label+'.python_outcome.json')
  if receipt.exists():result[label+'_python_exit']=read(receipt)['exit_code']
 if state['status']!='complete':print(json.dumps(result,ensure_ascii=False));return
 if not all((OUT/f).exists() for f in ['controller.python_outcome.json','gpu.python_outcome.json']):print(json.dumps(dict(status='receipts_pending')));return
 assert worker['status']=='complete' and state['native_exit']==state['launcher_exit']==0
 for label,s in [('controller',state),('gpu',worker)]:
  rec=read(OUT/(label+'.python_outcome.json'));assert rec['exit_code']==0 and rec['pid']==s['pid']
  assert rec['script']==str(HERE/('run_cpu.py' if label=='controller' else 'gpu_worker.py'))
 proc,torch=load_processor();pairs=read(OUT/'cases.json');packet=[];entries=[]
 for n,pair in enumerate(pairs,1):
  cid=f'R{n:04}';req_path=OUT/'requests'/(cid+'.json');req=read(req_path);out_path=OUT/'inference'/(cid+'.output.json');out=read(out_path);dd=read(OUT/'deliveries'/(cid+'.json'));row=read(OUT/'turns'/(cid+'.json'))
  assert req['role']=='surface' and req['context']['case']==pair['case'] and req['context']['pair_id']==pair['pair_id'] and req['seed']==pair['seed']
  assert req['user_prompt']==render_b(pair['case']) and all(req[k]==v for k,v in prepare(proc,render_b(pair['case'])).items())
  assert out['request_sha256']==dd['request_sha256']==sha(req_path) and dd['output_sha256']==sha(out_path)
  assert out['input_ids']==req['processor_fields']['input_ids'][0] and proc.decode(out['output_ids'],skip_special_tokens=False)==out['raw_output']
  assert out['generation_config']==cfg['surface']['generation_config'] and out['seed']==pair['seed'] and out['adapter_disabled'] is False and out['new_model_generation'] is True
  assert proc.parse_response(out['raw_output'],prefix=torch.tensor([out['input_ids']]))==dd['parsed']
  jp=OUT/'inference'/(cid+'_token_journal.jsonl');assert sha(jp)==out['journal_sha256'] and sum([x['ids'] for x in rows(jp)],[])==out['output_ids']
  assert dd['body']==row['body'] and dd['raw_output']==row['raw_output']==out['raw_output']
  assert row['format_reason']==format_failure(row['body'],out['official_stop_reached']) and row['delivered']==(row['format_reason'] is None)
  ar=read(pair['baseline_request_path']);ao=read(pair['baseline_output_path']);ad=read(pair['baseline_delivery_path'])
  assert ar['context']['case']==pair['case'] and ar['user_prompt']==render_a(pair['case']) and all(ar[k]==v for k,v in prepare(proc,render_a(pair['case'])).items())
  assert ao['request_sha256']==ad['request_sha256']==sha(pair['baseline_request_path']) and ad['output_sha256']==sha(pair['baseline_output_path'])
  assert ao['input_ids']==ar['processor_fields']['input_ids'][0] and proc.decode(ao['output_ids'],skip_special_tokens=False)==ao['raw_output']
  assert proc.parse_response(ao['raw_output'],prefix=torch.tensor([ao['input_ids']]))==ad['parsed'] and ad['body']==pair['baseline_body']
  assert ao['generation_config']==out['generation_config'] and ao['seed']==out['seed']
  packet.append(dict(pair=pair,A=dict(request=ar,output=ao,delivery=ad),B=dict(request=req,output=out,delivery=dd,row=row)))
  entries.append(dict(pair_id=pair['pair_id'],new_call_id=cid,baseline_call_id=pair['source_call_id'],request_sha256=sha(req_path),output_sha256=sha(out_path),official_stop_reached=out['official_stop_reached'],hit_token_cap=not out['official_stop_reached'] and len(out['output_ids'])>=cfg['surface']['generation_config']['max_new_tokens']))
 assert len(packet)==state['calls_completed']==worker['calls']==read(OUT/'requests/DONE.json')['calls']==cfg['max_calls']==4
 identity=read(OUT/'inference/identity_001.json');assert identity['role']=='instruct' and identity['adapter_tensors_loaded_exact'] and identity['adapter_sha256']==cfg['surface']['adapter_sha256'] and not identity['training']
 assert len(list((OUT/'inference').glob('identity_*.json')))==1 and len(list((OUT/'requests').glob('R*.json')))==4
 write(OUT/'review_packet.json',dict(pairs=packet,references=read(OUT/'reference/source_pairs.json'),scope='known condition designer AI; 1seed fixed original A histories; human0'))
 verify();audit=dict(status='pass',scope='technical integrity only, not semantic quality',pairs=4,new_surface_calls=4,baseline_saved_calls=4,planner_calls=0,guard_calls=0,training=0,quality_retries=0,actual_tts=False,current_exit0=True,fixed_cases_exact=True,official_processor_decode_journals=True,entries=entries,review_packet_sha256=sha(OUT/'review_packet.json'))
 write(OUT/'technical_audit.json',audit);print(json.dumps({k:v for k,v in audit.items() if k!='entries'},ensure_ascii=False))
if __name__=='__main__':main()
