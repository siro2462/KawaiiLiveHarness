from common import *
from processor_cpu import load_processor,prepare
from stripe_runtime import render_step,make_context,recent,format_reason,validate_request,groups
from cpu_selector import select

def main():
 cfg=verify();state=read(OUT/'controller.json') if (OUT/'controller.json').exists() else dict(status='startup_pending')
 worker=read(OUT/'inference/state.json') if (OUT/'inference/state.json').exists() else {}
 launch=read(OUT/'launch.json') if (OUT/'launch.json').exists() else {}
 status={k:state.get(k) for k in ['status','phase','calls_completed','actual_surface_calls','error']}
 for label,s in [('controller',state),('gpu',worker),('wrapper',launch)]:
  try:status[label+'_alive_same_identity']=abs(obs(s['pid'])['created_unix']-s['created_unix'])<.01
  except Exception:status[label+'_alive_same_identity']=False
 for label in ['controller','gpu']:
  p=OUT/(label+'.python_outcome.json')
  if p.exists():status[label+'_python_exit']=read(p)['exit_code']
 if state['status']!='complete':print(json.dumps(status,ensure_ascii=False));return
 if not all((OUT/n).exists() for n in ['controller.python_outcome.json','gpu.python_outcome.json']):print(json.dumps(dict(status='receipts_pending')));return
 assert worker['status']=='complete' and state['native_exit']==state['launcher_exit']==0
 for label,s in [('controller',state),('gpu',worker)]:
  receipt=read(OUT/(label+'.python_outcome.json'));assert receipt['exit_code']==0 and receipt['pid']==s['pid'] and Path(receipt['script']).resolve()==HERE/('run_cpu.py' if label=='controller' else 'gpu_worker.py')
 proc,torch=load_processor();result=read(OUT/'surface_result.json');samples=read(OUT/'samples.json');schedule=read(OUT/'unit_schedule.json')
 assert len(result['records'])==len(schedule)==cfg['max_calls']==11
 baseline_by={t['sample']['id']:t for t in read(OUT/'baseline_packet.json')['samples']}
 packets=[];entries=[];prior_global=[];n=0
 for sample in samples:
  assert select(sample,cfg['engine_seed'])==sample['selection']==read(OUT/'cpu_selections.json')[sample['id']]
  prior=[];turns=[];base=baseline_by[sample['id']];assert base['sample']==sample
  for index in range(len(groups(sample))):
   n+=1;cid=f'R{n:04}';row=result['records'][n-1]
   assert row['call_id']==cid and row['sample_id']==sample['id'] and row['unit_index']==index+1 and row['operations']==groups(sample)[index]
   reqp=OUT/'requests'/(cid+'.json');outp=OUT/'inference'/(cid+'.output.json')
   req=read(reqp);out=read(outp);delivery=read(OUT/'deliveries'/(cid+'.json'))
   prompt,payload=render_step(sample,index,prior);assert req['context']==make_context(sample,index,prior,payload)
   assert req['user_prompt']==prompt and validate_request(req,prior_global)
   assert all(req[k]==v for k,v in prepare(proc,prompt).items())
   assert out['request_sha256']==delivery['request_sha256']==sha(reqp) and delivery['output_sha256']==sha(outp)
   assert out['input_ids']==req['processor_fields']['input_ids'][0] and proc.decode(out['output_ids'],skip_special_tokens=False)==out['raw_output']
   assert proc.parse_response(out['raw_output'],prefix=torch.tensor([out['input_ids']]))==delivery['parsed']
   assert out['generation_config']==cfg['surface']['generation_config'] and not out['adapter_disabled'] and out['new_model_generation'] is True
   journal=OUT/'inference'/(cid+'_token_journal.jsonl')
   assert sha(journal)==out['journal_sha256'] and sum([x['ids'] for x in rows(journal)],[])==out['output_ids']
   reason=format_reason(delivery['body'],out['official_stop_reached'])
   assert row['format_reason']==reason and row['delivered']==(reason is None) and row['body']==delivery['body'] and row['raw_output']==out['raw_output'] and row['eos']==out['official_stop_reached']
   assert row['before_history']==recent(prior)
   prior.append(row);prior_global.append(row)
   assert row['after_history']==recent(prior)
   turns.append(dict(request=req,output=out,delivery=delivery,row=row))
   entries.append(dict(call_id=cid,sample_id=sample['id'],unit_index=index+1,input_tokens=len(out['input_ids']),output_tokens=len(out['output_ids']),history_calls=[x['call_id'] for x in payload['history']],current_operation_count=len(groups(sample)[index]),eos=out['official_stop_reached'],format_reason=reason,request_sha256=sha(reqp),output_sha256=sha(outp)))
  group=next(g for g in result['groups'] if g['sample_id']==sample['id'])
  text='\n'.join(r['body'] for r in prior if r['delivered'])
  assert group['full_text']==text and group['records']==prior
  packets.append(dict(sample=sample,baseline=base,turns=turns,full_text=text,selection=sample['selection']))
 assert n==result['actual_surface_calls']==state['calls_completed']==worker['calls']==read(OUT/'requests/DONE.json')['calls']==11
 assert len(list((OUT/'requests').glob('R*.json')))==11 and len(list((OUT/'inference').glob('identity_*.json')))==1
 identity=read(OUT/'inference/identity_001.json');assert identity['role']=='instruct' and identity['adapter_tensors_loaded_exact'] and identity['adapter_sha256']==cfg['surface']['adapter_sha256'] and not identity['training']
 write(OUT/'review_packet.json',dict(samples=packets,scope='same fixed3 Memory and CPU40 operations; up to4 operations per call, actual delivered text last2/800 feedback; no adaptive reselection; A saved one-operation40/B group4 new11'))
 audit=dict(status='pass',new_surface_calls=11,current_exit0=True,all_actual_inputs_replayed_exact=True,operations_per_call_max4=True,actual_delivered_history_exact=True,deferred_unchanged=1,planner_calls=0,guard_calls=0,training=0,quality_retries=0,memory_writes=0,entries=entries,review_packet_sha256=sha(OUT/'review_packet.json'))
 verify();write(OUT/'technical_audit.json',audit);print(json.dumps({k:v for k,v in audit.items() if k!='entries'},ensure_ascii=False))
if __name__=='__main__':main()
