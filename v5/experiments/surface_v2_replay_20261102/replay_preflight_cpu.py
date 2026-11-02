"""Extra CPU proof of exact reproduction of the saved v2 B requests."""
from common import *
from processor_cpu import load_processor,prepare
from prompt_v2 import render
def main():
 cfg=verify();old=Path(cfg['source_v2_run']);source=read(old/'protocol.json');checks=[]
 def check(name,value):checks.append(dict(name=name,passed=bool(value)));assert value,name
 check('same surface model adapter and entire generation config',cfg['surface']==source['surface'])
 check('same seed schedule order cap4',cfg['seeds']==source['seeds']==[20260925] and cfg['max_calls']==cfg['max_new_model_calls']==4)
 check('new generations only no cached output replay',not cfg['prefix_reuse'])
 check('original cases bytes',sha(OUT/'cases.json')==sha(old/'cases.json'))
 for n,h in read(OUT/'replay_setup_manifest.json')['all_original_source_bytes'].items():check('original code/template '+n,sha(HERE/n)==sha(old/'executed_source'/n)==h)
 proc,torch=load_processor();records=[]
 for i,pair in enumerate(read(OUT/'cases.json'),1):
  cid=f'R{i:04}';saved=read(old/'requests'/(cid+'.json'));saved_out=read(old/'inference'/(cid+'.output.json'))
  actual=prepare(proc,render(pair['case']))
  context=dict(pair_id=pair['pair_id'],arm='B_v2',memory_id=pair['memory_id'],case=pair['case'],target_ids=[f['id'] for f in pair['case']['facts']],baseline_call_id=pair['source_call_id'],fixed_history=True)
  req=dict(call_id=cid,role='surface',seed=pair['seed'],context=context,**actual)
  check(cid+' full request dict including original context exact',req==saved)
  check(cid+' original generation settings exact',saved_out['generation_config']==cfg['surface']['generation_config'])
  check(cid+' original adapter enabled seed exact',saved_out['adapter_disabled'] is False and saved_out['seed']==pair['seed']==20260925)
  check(cid+' complete original v2 prompt and decoded exact',actual['user_prompt']==saved['user_prompt'] and actual['decoded_input']==saved['decoded_input'])
  check(cid+' no truncation',len(actual['processor_fields']['input_ids'][0])+384<8192)
  records.append(dict(call_id=cid,pair_id=pair['pair_id'],memory_id=pair['memory_id'],input_tokens=len(saved_out['input_ids']),prompt_chars=len(actual['user_prompt']),all_request_fields_exact=True,source_request_sha256=sha(old/'requests'/(cid+'.json'))))
 check('same complete case order',[p['pair_id'] for p in read(OUT/'cases.json')]==['P01','P02','P03','P04'])
 result=dict(status='pass',checks=checks,check_count=len(checks),new_model_calls=0,all4_full_request_dicts_exact=True,all_generation_settings_exact=True,records=records)
 write(OUT/'replay_cpu_proof.json',result)
 write(OUT/'setup_validation.json',dict(status='pass',all4_full_request_dicts_exact=True,all_generation_settings_exact=True,new_model_calls=0))
 print(json.dumps({k:v for k,v in result.items() if k not in ['checks','records']},ensure_ascii=False))
if __name__=='__main__':main()
