from common import *
import copy
from processor_cpu import load_processor, prepare
from contract_runtime import render as render_a, digest as case_digest
from viewpoint_runtime import render, apply_angle, AngleAttempts, SECTION

def main():
 cfg=verify(); checks=[]
 def check(name, ok):
  checks.append(dict(name=name,pass_check=bool(ok))); assert ok,name
 def rejects(name, fn):
  try: fn(); bad=False
  except (ValueError,AssertionError): bad=True
  check(name,bad)
 check('two Surface calls only',cfg['max_calls']==cfg['max_new_model_calls']==2 and cfg['new_planner_calls']==cfg['new_guard_calls']==cfg['training']==cfg['quality_retries']==0 and not cfg['prefix_reuse'])
 check('same 384 token generation budget',cfg['surface']['generation_config']['max_new_tokens']==384)
 manifest=read(OUT/'setup_manifest.json')
 for name,h in manifest['unchanged_core'].items():
  check('unchanged core: '+name,sha(HERE/name)==h==sha(Path(manifest['source_run'])/'executed_source'/name))
 repo=TALK.parent/'KawaiiLiveHarness/v5/runtime/contract_runtime.py'
 check('baseline equals current v5 renderer',sha(HERE/'contract_runtime.py')==sha(repo))
 pairs=read(OUT/'cases.json'); a,b=pairs
 check('both angles use identical whole case',a['case']==b['case'])
 check('only viewpoint and probe ID differ',all(a[k]==b[k] for k in a if k not in ('pair_id','viewpoint')))
 check('distinct angles, same source basis',a['viewpoint']['angle_id']!=b['viewpoint']['angle_id'] and a['viewpoint']['basis']==b['viewpoint']['basis'])
 original=copy.deepcopy(a['case']); packet=apply_angle(a['case'],a['viewpoint'])
 check('application preserves whole case and digest',packet['case']==original and packet['case_sha256']==case_digest(original))
 packet['case']['facts'][0]['claim']='test mutation'
 check('application does not mutate caller',a['case']==original)
 check('no angle reconstructs current prompt byte exact',render(a['case'])==render_a(a['case']))
 for name,modify in [
  ('unknown fact',lambda v:v['basis'][0].update(fact_id='H99-1')),
  ('quote mismatch',lambda v:v['basis'][0].update(quote='確定していない経験')),
  ('empty basis',lambda v:v.update(basis=[])),
  ('duplicate basis',lambda v:v['basis'].append(copy.deepcopy(v['basis'][0]))),
  ('empty instruction',lambda v:v.update(instruction=' ')),
  ('unversioned schema',lambda v:v.update(schema='unknown')),
  ('extra expected speech',lambda v:v.update(expected_output='台詞'))]:
  v=copy.deepcopy(a['viewpoint']);modify(v)
  rejects(name,lambda:apply_angle(original,v))
 attempts=AngleAttempts(2); key=attempts.begin(original,a['viewpoint'])
 rejects('same angle cannot retry before completion',lambda:attempts.begin(original,a['viewpoint']))
 attempts.finish(key,'CPU001',True)
 rejects('same angle cannot retry after completion',lambda:attempts.begin(original,a['viewpoint']))
 rejects('cannot finish same attempt twice',lambda:attempts.finish(key,'CPU001',True))
 k2=attempts.begin(original,b['viewpoint']);attempts.finish(k2,'CPU002',False)
 check('same Fact permits distinct angle',len(attempts.records)==2)
 check('delivery or hold is not semantic success',all(x['semantic_status']=='unverified' for x in attempts.records))
 v=copy.deepcopy(b['viewpoint']);v['angle_id']='third'
 rejects('cannot exceed explicit attempt budget',lambda:attempts.begin(original,v))
 proc,torch=load_processor(); prepared=[]
 for pair in pairs:
  pid=pair['pair_id'];case=pair['case'];v=pair['viewpoint'];req=read(pair['baseline_request_path']);out=read(pair['baseline_output_path']);dd=read(pair['baseline_delivery_path'])
  check(pid+' baseline whole case',req['context']['case']==case)
  check(pid+' baseline original renderer',req['user_prompt']==render_a(case))
  aa=prepare(proc,render_a(case));bb=prepare(proc,render(case,v))
  check(pid+' official baseline Processor exact',all(req[k]==x for k,x in aa.items()))
  check(pid+' baseline output SHA linkage',out['request_sha256']==dd['request_sha256']==sha(pair['baseline_request_path']) and dd['output_sha256']==sha(pair['baseline_output_path']))
  check(pid+' same generation config',out['generation_config']==cfg['surface']['generation_config'])
  check(pid+' same seed adapter enabled',req['seed']==pair['seed']==out['seed']==20260925 and out['adapter_disabled'] is False)
  check(pid+' unchanged base prefix',bb['user_prompt'].split(SECTION)[0]==aa['user_prompt'])
  check(pid+' complete Fact and history retained',all(f['claim'] in bb['user_prompt'] for f in case['facts']) and all(h['text'] in bb['user_prompt'] for h in case['history']))
  check(pid+' selected angle reaches actual decoded input',v['instruction'] in bb['decoded_input'] and v['label'] in bb['decoded_input'])
  other=next(x for x in pairs if x['pair_id']!=pid)['viewpoint']
  check(pid+' other angle instruction not injected',other['instruction'] not in bb['user_prompt'])
  check(pid+' no truncation',len(bb['processor_fields']['input_ids'][0])+384<8192)
  check(pid+' same official template except text',aa['template_kwargs']==bb['template_kwargs'])
  prepared.append(dict(pair_id=pid,A=aa,B=bb,input_tokens_A=len(aa['processor_fields']['input_ids'][0]),input_tokens_B=len(bb['processor_fields']['input_ids'][0])))
 p1,p2=[x['B'] for x in prepared]
 check('angle is sole prompt delta between new arms',p1['user_prompt'].split('見る角度：')[0]==p2['user_prompt'].split('見る角度：')[0])
 check('distinct actual token inputs',p1['processor_fields']['input_ids']!=p2['processor_fields']['input_ids'])
 first=read(OUT/'reference/common_first.json');fr=read(first['baseline_request_path'])
 check('common first part is same saved reference',first['memory_id']=='H06' and first['baseline_body']==a['case']['history'][-1]['text'])
 check('common first part request reconstructs exactly',fr['user_prompt']==render_a(first['case']) and all(fr[k]==v for k,v in prepare(proc,render_a(first['case'])).items()))
 write(OUT/'prepared_inputs.json',prepared)
 result=dict(status='pass',checks=checks,check_count=len(checks),new_model_calls=0,processor='official CPU AutoProcessor',context_cut_tokens=0,prepared_inputs_sha256=sha(OUT/'prepared_inputs.json'),token_counts=[{k:x[k] for k in ['pair_id','input_tokens_A','input_tokens_B']} for x in prepared])
 write(OUT/'cpu_preflight.json',result);print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
if __name__=='__main__':main()
