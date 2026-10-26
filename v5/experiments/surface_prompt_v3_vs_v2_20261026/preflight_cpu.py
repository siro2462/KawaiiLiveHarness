from common import *
from processor_cpu import load_processor,prepare
from prompt_v2 import render as render_a
from prompt_v3 import render as render_b

def main():
 cfg=verify();checks=[]
 def check(name,condition):
  checks.append(dict(name=name,pass_check=bool(condition)))
  assert condition,name
 check('only four Surface calls',cfg['max_calls']==4 and cfg['new_planner_calls']==0 and not cfg['prefix_reuse'])
 check('fixed generation cap',cfg['surface']['generation_config']['max_new_tokens']==384)
 check('v3 is only three-point insertion and title change over exact v2',read(OUT/'prompt_provenance.json')['v2_unchanged_outside_three_point_insertion'])
 old=Path(cfg['source_run'])
 for name in ['gpu_worker.py','driver_cpu.py','runtime.py','flow_apply.py','contract_runtime.py','common.py','request_protocol.py']:
  check('copied unchanged: '+name,sha(HERE/name)==sha(old/'executed_source'/name))
 proc,torch=load_processor();prepared=[]
 for pair in read(OUT/'cases.json'):
  pid=pair['pair_id'];req=read(pair['baseline_request_path']);out=read(pair['baseline_output_path']);dd=read(pair['baseline_delivery_path'])
  check(pid+' same saved case',pair['case']==req['context']['case'])
  check(pid+' baseline reconstructed',render_a(pair['case'])==req['user_prompt'])
  aa=prepare(proc,render_a(pair['case']));bb=prepare(proc,render_b(pair['case']))
  check(pid+' official baseline Processor exact',all(req[k]==v for k,v in aa.items()))
  check(pid+' baseline request/output hashes',out['request_sha256']==dd['request_sha256']==sha(pair['baseline_request_path']) and dd['output_sha256']==sha(pair['baseline_output_path']))
  check(pid+' same model generation config',out['generation_config']==cfg['surface']['generation_config'])
  check(pid+' same seed and adapter enabled',req['seed']==pair['seed']==20260925 and out['adapter_disabled'] is False)
  check(pid+' target claims unchanged',all(f['claim'] in bb['user_prompt'] for f in pair['case']['facts']))
  check(pid+' fixed history unchanged',all(h['text'] in bb['user_prompt'] for h in pair['case']['history']))
  check(pid+' operation and relation unchanged',pair['case']['relation']['summary'] in bb['user_prompt'])
  check(pid+' prompt differs',aa['user_prompt']!=bb['user_prompt'])
  check(pid+' no context truncation',len(bb['processor_fields']['input_ids'][0])+384<8192)
  prepared.append(dict(pair_id=pid,A=aa,B=bb,input_tokens_A=len(aa['processor_fields']['input_ids'][0]),input_tokens_B=len(bb['processor_fields']['input_ids'][0])))
 write(OUT/'prepared_inputs.json',prepared)
 result=dict(status='pass',checks=checks,check_count=len(checks),new_model_calls=0,processor='official CPU AutoProcessor',context_cut_tokens=0,prepared_inputs_sha256=sha(OUT/'prepared_inputs.json'),token_counts=[{k:x[k] for k in ['pair_id','input_tokens_A','input_tokens_B']} for x in prepared])
 write(OUT/'cpu_preflight.json',result);print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
if __name__=='__main__':main()
