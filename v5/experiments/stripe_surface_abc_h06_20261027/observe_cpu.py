from common import *
import tempfile
from unittest.mock import patch
from processor_cpu import load_processor,prepare
from stripe_runtime import text_units
import run_cpu

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
 proc,torch=load_processor();saved=read(OUT/'abc_result.json');packets=[];entries=[]
 class Replay:
  n=0
  def call(self,role,prompt,seed,context):
   self.n+=1;cid=f'R{self.n:04}';reqp=OUT/'requests'/(cid+'.json');outp=OUT/'inference'/(cid+'.output.json');req=read(reqp);out=read(outp);d=read(OUT/'deliveries'/(cid+'.json'))
   assert req['role']==role=='surface' and req['seed']==seed==20260925 and req['context']==context and req['user_prompt']==prompt
   assert all(req[k]==v for k,v in prepare(proc,prompt).items())
   assert out['request_sha256']==d['request_sha256']==sha(reqp) and d['output_sha256']==sha(outp)
   assert out['input_ids']==req['processor_fields']['input_ids'][0] and proc.decode(out['output_ids'],skip_special_tokens=False)==out['raw_output']
   assert proc.parse_response(out['raw_output'],prefix=torch.tensor([out['input_ids']]))==d['parsed']
   assert out['generation_config']==cfg['surface']['generation_config'] and out['adapter_disabled'] is False and out['new_model_generation'] is True
   jp=OUT/'inference'/(cid+'_token_journal.jsonl');assert sha(jp)==out['journal_sha256'] and sum([x['ids'] for x in rows(jp)],[])==out['output_ids']
   assert len(out['input_ids'])+1536<8192
   packets.append(dict(request=req,output=out,delivery=d,units=text_units(d['body'])))
   entries.append(dict(call_id=cid,arm=context['arm'],input_tokens=len(out['input_ids']),output_tokens=len(out['output_ids']),eos=out['official_stop_reached'],request_sha256=sha(reqp),output_sha256=sha(outp)))
   return cid,dict(out,body=d['body'])
 with tempfile.TemporaryDirectory() as tmp:
  q=Path(tmp)
  for n in ['steps32.json','memory_h06.json','legacy_memory.json','initial_history.json']:write(q/n,read(OUT/n))
  with patch.object(run_cpu,'OUT',q):d=Replay();replayed=run_cpu.rollout(d,cfg)
  assert replayed==saved
 count=d.n;assert 3<=count<=11 and count==saved['actual_surface_calls']==state['calls_completed']==worker['calls']==read(OUT/'requests/DONE.json')['calls']
 assert len(list((OUT/'requests').glob('R*.json')))==count and len(list((OUT/'inference').glob('identity_*.json')))==1
 identity=read(OUT/'inference/identity_001.json');assert identity['role']=='instruct' and identity['adapter_tensors_loaded_exact'] and identity['adapter_sha256']==cfg['surface']['adapter_sha256'] and not identity['training']
 enriched=[]
 for arm in saved['arms']:
  calls=[]
  for row in arm['records']:
   item=next(x for x in packets if x['request']['call_id']==row['call_id']);calls.append(dict(item,row=row))
  enriched.append(dict(arm=arm['arm'],turns=calls,stop_reason=arm['stop_reason'],unattempted_groups=arm['unattempted_groups']))
 human=read(OUT/'reference/human_h06.json');human_text='\n'.join(x['text'] for x in human)
 write(OUT/'review_packet.json',dict(arms=enriched,steps=read(OUT/'steps32.json'),memory=read(OUT/'memory_h06.json'),legacy_memory=read(OUT/'legacy_memory.json'),human_reference=human,human_text=human_text,human_units=text_units(human_text),input_source_manifest=read(OUT/'reference/source_manifest.json'),scope='fixed operation realization; no adaptive operation reselection; A differs in information; human0/designer known condition'))
 audit=dict(status='pass',scope='technical integrity, not semantic quality',new_surface_calls=count,arms=3,current_exit0=True,all_inputs_exact=True,all_actual_histories_replayed=True,planner_calls=0,guard_calls=0,training=0,quality_retries=0,memory_writes=0,surface_max_new_tokens=1536,entries=entries,review_packet_sha256=sha(OUT/'review_packet.json'))
 verify();write(OUT/'technical_audit.json',audit);print(json.dumps({k:v for k,v in audit.items() if k!='entries'},ensure_ascii=False))
if __name__=='__main__':main()
