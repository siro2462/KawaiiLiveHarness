"""Run original technical audit, then compare current execution with saved v2 B."""
from common import *
import observe_cpu
def main():
 observe_cpu.main()
 state=read(OUT/'controller.json') if (OUT/'controller.json').exists() else {}
 if state.get('status')!='complete' or not (OUT/'technical_audit.json').exists():return
 cfg=verify();original=read(Path(cfg['source_v2_run'])/'review_packet.json');current=read(OUT/'review_packet.json')
 audit=read(OUT/'technical_audit.json');assert audit['status']=='pass'
 # Original audit may be rerun, so preserve its unmodified result before replacing the view.
 write(OUT/'original_validation_packet.json',current);write(OUT/'original_validation_audit.json',audit)
 pairs=[];entries=[]
 for old,new in zip(original['pairs'],current['pairs']):
  a=old['B'];b=new['B'];assert old['pair']==new['pair']
  assert a['request']==b['request'] and a['output']['input_ids']==b['output']['input_ids']
  assert a['output']['generation_config']==b['output']['generation_config'] and a['output']['seed']==b['output']['seed']
  assert not b['output']['adapter_disabled'] and b['output']['new_model_generation']
  pair=dict(pair=new['pair'],A=a,B=b);pairs.append(pair)
  entries.append(dict(pair_id=new['pair']['pair_id'],memory_id=new['pair']['memory_id'],call_id=b['request']['call_id'],full_request_dict_exact=True,
   input_tokens_exact=True,output_tokens_exact=a['output']['output_ids']==b['output']['output_ids'],raw_exact=a['output']['raw_output']==b['output']['raw_output'],body_exact=a['delivery']['body']==b['delivery']['body']))
 assert len(entries)==4
 write(OUT/'review_packet.json',dict(pairs=pairs,references=original['references'],scope='saved v2 B vs exact-input new v2; same original fixed histories; no new output feedback; human0'))
 result=dict(status='pass',scope='exact saved model-facing conditions, not semantic quality',pairs=4,new_surface_calls=4,current_exit0=True,
  all4_full_request_dicts_exact=True,all_input_tokens_and_generation_settings_exact=True,output_tokens_equal=sum(e['output_tokens_exact'] for e in entries),body_equal=sum(e['body_exact'] for e in entries),
  entries=entries,review_packet_sha256=sha(OUT/'review_packet.json'),original_validation_audit_sha256=sha(OUT/'original_validation_audit.json'))
 write(OUT/'technical_audit.json',result);print(json.dumps({k:v for k,v in result.items() if k!='entries'},ensure_ascii=False))
if __name__=='__main__':main()
