from common import *
from continuous_policy import count_chars

def main():
 cfg=verify();state=read(OUT/'controller.json') if (OUT/'controller.json').exists() else dict(status='startup_pending');worker=read(OUT/'inference/state.json') if (OUT/'inference/state.json').exists() else {}
 result={k:state.get(k) for k in ['status','phase','calls_completed','surface_candidates','text_delivered','delivered_chars','planner_calls','stop_reason','target_met','error']}
 for label,s in [('controller',state),('gpu',worker),('wrapper',read(OUT/'launch.json') if (OUT/'launch.json').exists() else {})]:
  try:result[label+'_alive_same_identity']=abs(obs(s['pid'])['created_unix']-s['created_unix'])<.01
  except Exception:result[label+'_alive_same_identity']=False
  if (OUT/(label+'.python_outcome.json')).exists():result[label+'_python_exit']=read(OUT/(label+'.python_outcome.json'))['exit_code']
 if state['status']!='complete':print(json.dumps(result,ensure_ascii=False));return
 if not all((OUT/f).exists() for f in ['controller.python_outcome.json','gpu.python_outcome.json']):print(json.dumps(dict(status='receipts_pending')));return
 assert worker['status']=='complete' and state['native_exit']==state['launcher_exit']==0
 for name,s in [('controller',state),('gpu',worker)]:
  q=read(OUT/(name+'.python_outcome.json'));assert q['exit_code']==0 and q['pid']==s['pid']
  assert abs(q.get('create_time',s['created_unix'])-s['created_unix'])<.01
 sys.path.insert(0,str(CPU_DEPS));import torch
 from transformers import AutoProcessor
 assert torch.__version__.endswith('+cpu') and not torch.cuda.is_available()
 proc=AutoProcessor.from_pretrained(str(MULTI/'models'/cfg['surface']['model_key']),local_files_only=True,trust_remote_code=False)
 for p in [MULTI,GEMMA]:sys.path.insert(0,str(p))
 from prepare_data import tokenizer
 from planner_policy import parse_plan
 from contract_runtime import render
 tok=tokenizer(cfg['planner']['model_key']);byid={};entries=[]
 for f in sorted((OUT/'requests').glob('R*.json')):
  r=read(f);cid=r['call_id'];o=read(OUT/'inference'/(cid+'.output.json'));assert o['request_sha256']==sha(f) and o['new_model_generation'] is True
  assert r['role'] in ('surface','planner')
  if r['role']=='surface':
   ff=proc.apply_chat_template(r['messages'],**r['template_kwargs']);assert {k:v.tolist() for k,v in ff.items()}==r['processor_fields']
   assert o['input_ids']==r['processor_fields']['input_ids'][0] and proc.decode(o['output_ids'],skip_special_tokens=False)==o['raw_output'] and o['adapter_disabled'] is False
   dd=read(OUT/'deliveries'/(cid+'.json'));assert proc.parse_response(o['raw_output'],prefix=torch.tensor([o['input_ids']]))==dd['parsed']
   jp=OUT/'inference'/(cid+'_token_journal.jsonl');assert sha(jp)==o['journal_sha256'] and sum([x['ids'] for x in rows(jp)],[])==o['output_ids']
   assert render(r['context']['case'])==r['user_prompt']
  else:
   assert o['strict_schema_valid'];parse_plan(o['text'],r['candidate_ids'])
   assert tok.decode(o['input_ids'],skip_special_tokens=False)==o['decoded_input'] and tok.decode(o['output_ids'],skip_special_tokens=False)==o['raw_output']
  byid[cid]=(r,o);entries.append(dict(call_id=cid,role=r['role'],seconds=o['seconds'],request_sha256=sha(f),output_sha256=sha(OUT/'inference'/(cid+'.output.json')),context_cut_tokens=o.get('context_cut_tokens',0)))
 assert len(entries)==state['calls_completed']==worker['calls']==read(OUT/'requests/DONE.json')['calls']<=cfg['max_calls']
 for f in (OUT/'inference').glob('identity_*.json'):
  q=read(f);role='surface' if q['role']=='instruct' else 'planner';assert q['adapter_tensors_loaded_exact'] and q['adapter_sha256']==cfg[role]['adapter_sha256'] and not q['training']
 rr=read(OUT/'continuous_result.json');rs=rr['records'];prior=[];used=[];packet=[]
 assert len(rs)<=cfg['max_surface_calls'] and len(rr['plans'])==len(rs)<=cfg['max_replan_calls']
 for row in rs:
  r,o=byid[row['call_id']];pr,po=byid[row['planner_call_id']];keep=[]
  for item in reversed(prior):
   if len(keep)==2 or sum(len(x['text']) for x in keep)+len(item['text'])>800:break
   keep.insert(0,item)
  assert [x['text'] for x in row['case']['history']]==[x['text'] for x in keep]
  assert pr['recent']=='\n'.join(x['text'] for x in keep) and pr['context']['planner_input']['recent']==pr['recent']
  assert row['body']==read(OUT/'deliveries'/(row['call_id']+'.json'))['body'] and row['raw_output']==o['raw_output']
  assert row['case']==r['context']['case'] and row['plan']==parse_plan(po['text'],pr['candidate_ids'])
  assert 1<=len(r['context']['target_ids'])<=2 and all(f['semantic_status']=='unverified' for f in row['after']['facts'].values())
  used+=r['context']['target_ids']
  if row['delivered']:prior.append(dict(text=row['body']))
  packet.append(dict(row,actual_surface_request=r,actual_surface_output=o,actual_planner_request=pr,actual_planner_output=po,plan_application=read(OUT/'plans'/(row['planner_call_id']+'.json'))))
 assert len(used)==len(set(used))
 chars=sum(count_chars(x['text']) for x in prior);assert chars==rr['delivered_chars'] and rr['target_met']==(chars>=cfg['target_chars'])
 assert (OUT/'speech.txt').read_text(encoding='utf-8')=='\n\n'.join(x['text'] for x in prior)+'\n'
 import sqlite3
 db=sqlite3.connect((OUT/'events.sqlite').as_uri()+'?mode=ro',uri=True);db.execute('PRAGMA query_only=ON')
 assert [json.loads(x[0])['text'] for x in db.execute("SELECT payload FROM events WHERE kind='text_delivery_confirmed' ORDER BY seq")]==[x['text'] for x in prior]
 assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close()
 db=sqlite3.connect((OUT/'live_alpha.sqlite').as_uri()+'?mode=ro',uri=True);db.execute('PRAGMA query_only=ON')
 signature={t:digest(json.dumps([list(x) for x in db.execute('SELECT * FROM '+t+' ORDER BY 1,2,3')],ensure_ascii=False)) for t in ('memories','links')};db.close();assert signature==read(OUT/'memory_invariants.json')
 selected=[x['selected_memory']['id'] for x in rr['selections'] if x['selected_memory']]
 assert len(selected)==len(set(selected)) and set(selected)<=set(cfg['eligible_memory_ids'])
 for s in rr['selections']:
  m=s['selected_memory']
  if m:assert any(t['result']['proposal'].get('memory_ids')==[m['id']] and t['result']['proposal']['decision']=='sandbox_propose' for t in s['traces'])
 write(OUT/'review_packet.json',dict(turns=packet,selections=rr['selections'],final_state=rr,scope='known condition designer AI review; human quality labels0'))
 for n,i in enumerate(range(0,len(packet),3),1):write(OUT/f'review_page_{n:02}.json',packet[i:i+3])
 verify();audit=dict(status='pass',scope='execution/input/history/source integrity, not semantic quality',surface_candidates=len(rs),delivered=len(prior),planner_calls=len(rr['plans']),calls=len(entries),delivered_chars=chars,target_met=rr['target_met'],stop_reason=rr['stop_reason'],source_memory_links_unchanged=True,no_repeated_source_fact_targets=True,actual_history_exact=True,official_decode_journals=True,current_exit0=True,semantic_guard_calls=0,quality_retries=0,training_updates=0,actual_tts=False,human_quality_labels=0,entries=entries,review_packet_sha256=sha(OUT/'review_packet.json'))
 write(OUT/'technical_audit.json',audit);print(json.dumps({k:v for k,v in audit.items() if k!='entries'},ensure_ascii=False))
if __name__=='__main__':main()
