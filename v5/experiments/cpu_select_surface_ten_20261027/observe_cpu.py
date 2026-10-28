from common import *
from processor_cpu import load_processor,prepare
from stripe_runtime import render_sample,text_units,format_reason
from cpu_selector import select

def main():
 cfg=verify();state=read(OUT/'controller.json') if (OUT/'controller.json').exists() else dict(status='startup_pending');worker=read(OUT/'inference/state.json') if (OUT/'inference/state.json').exists() else {};launch=read(OUT/'launch.json') if (OUT/'launch.json').exists() else {}
 status={k:state.get(k) for k in ['status','phase','calls_completed','actual_surface_calls','error']}
 for label,s in [('controller',state),('gpu',worker),('wrapper',launch)]:
  try:status[label+'_alive_same_identity']=abs(obs(s['pid'])['created_unix']-s['created_unix'])<.01
  except Exception:status[label+'_alive_same_identity']=False
  if (OUT/(label+'.python_outcome.json')).exists():status[label+'_python_exit']=read(OUT/(label+'.python_outcome.json'))['exit_code']
 if state['status']!='complete':print(json.dumps(status,ensure_ascii=False));return
 if not all((OUT/n).exists() for n in ['controller.python_outcome.json','gpu.python_outcome.json']):print(json.dumps(dict(status='receipts_pending')));return
 assert worker['status']=='complete' and state['native_exit']==state['launcher_exit']==0
 for label,s in [('controller',state),('gpu',worker)]:
  receipt=read(OUT/(label+'.python_outcome.json'));assert receipt['exit_code']==0 and receipt['pid']==s['pid'] and Path(receipt['script']).resolve()==HERE/('run_cpu.py' if label=='controller' else 'gpu_worker.py')
 proc,torch=load_processor();saved=read(OUT/'ten_result.json');samples=read(OUT/'samples.json');assert len(saved['records'])==10
 packets=[];entries=[]
 for i,(s,row) in enumerate(zip(samples,saved['records']),1):
  cid=f'R{i:04}';assert row['call_id']==cid and row['sample_id']==s['id'];reqp=OUT/'requests'/(cid+'.json');outp=OUT/'inference'/(cid+'.output.json');req=read(reqp);out=read(outp);d=read(OUT/'deliveries'/(cid+'.json'));prompt,payload=render_sample(s)
  chosen=select(s,cfg['engine_seed']);assert chosen==read(OUT/'cpu_selections.json')[s['id']] and s['steps']==chosen['steps']
  expected=dict(experiment=cfg['experiment'],sample_id=s['id'],category=s['category'],payload=payload,before=dict(history=[],semantic_status='unverified'),source_inputs_sha256=sha(OUT/'samples.json'),fixed_sequence=True,adaptive_reselection=False)
  assert req['context']==expected and req['role']=='surface' and req['seed']==cfg['surface_seed'] and req['user_prompt']==prompt
  assert all(req[k]==v for k,v in prepare(proc,prompt).items())
  assert out['request_sha256']==d['request_sha256']==sha(reqp) and d['output_sha256']==sha(outp)
  assert out['input_ids']==req['processor_fields']['input_ids'][0] and proc.decode(out['output_ids'],skip_special_tokens=False)==out['raw_output']
  assert proc.parse_response(out['raw_output'],prefix=torch.tensor([out['input_ids']]))==d['parsed']
  assert out['generation_config']==cfg['surface']['generation_config'] and out['adapter_disabled'] is False and out['new_model_generation'] is True
  jp=OUT/'inference'/(cid+'_token_journal.jsonl');assert sha(jp)==out['journal_sha256'] and sum([x['ids'] for x in rows(jp)],[])==out['output_ids']
  reason=format_reason(d['body'],out['official_stop_reached']);assert row['format_reason']==reason and row['delivered']==(reason is None) and row['body']==d['body'] and row['raw_output']==out['raw_output']
  assert row['after_history']==([dict(text=d['body'],origin='offline unverified text; not Memory')] if reason is None else [])
  assert len(out['input_ids'])+1536<8192
  packets.append(dict(sample=s,selection=chosen,baseline=read(OUT/'reference/baseline/review_packet.json')['samples'][i-1],request=req,output=out,delivery=d,row=row,units=text_units(d['body'])))
  entries.append(dict(call_id=cid,sample_id=s['id'],input_tokens=len(out['input_ids']),output_tokens=len(out['output_ids']),eos=out['official_stop_reached'],request_sha256=sha(reqp),output_sha256=sha(outp)))
 assert saved['actual_surface_calls']==state['calls_completed']==worker['calls']==read(OUT/'requests/DONE.json')['calls']==10
 assert len(list((OUT/'requests').glob('R*.json')))==10 and len(list((OUT/'inference').glob('identity_*.json')))==1
 identity=read(OUT/'inference/identity_001.json');assert identity['role']=='instruct' and identity['adapter_tensors_loaded_exact'] and identity['adapter_sha256']==cfg['surface']['adapter_sha256'] and not identity['training']
 write(OUT/'review_packet.json',dict(samples=packets,scope='same H06 CPU selector on automatic lexical metadata + direct reaction fewshot; fixed Memory, independent one-shot; not adaptive; two combined changes; human0'))
 audit=dict(status='pass',new_surface_calls=10,current_exit0=True,all_inputs_exact=True,all_independent_empty_histories=True,planner_calls=0,guard_calls=0,training=0,quality_retries=0,memory_writes=0,entries=entries,review_packet_sha256=sha(OUT/'review_packet.json'))
 verify();write(OUT/'technical_audit.json',audit);print(json.dumps({k:v for k,v in audit.items() if k!='entries'},ensure_ascii=False))
if __name__=='__main__':main()
