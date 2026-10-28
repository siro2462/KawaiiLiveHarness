from common import *
import copy,tempfile
from unittest.mock import patch
from processor_cpu import load_processor,prepare
from contract_runtime import render as render_a
from role_runtime import RoleControl,render,validate_roles,literal_angle_evidence
import run_cpu

def main():
 cfg=verify();base=read(OUT/'baseline_case.json');case=base['case'];roles=read(OUT/'roles.json');checks=[]
 def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
 def rejects(name,fn):
  try:fn();bad=False
  except (ValueError,AssertionError):bad=True
  check(name,bad)
 check('max2 Surface, no other calls',cfg['max_calls']==2 and all(cfg[k]==0 for k in ['new_planner_calls','new_guard_calls','training','quality_retries']) and not cfg['prefix_reuse'])
 prior=read(Path(cfg['source_run'])/'protocol.json')
 check('exact fixed LoRA/model/generation config',cfg['surface']==prior['surface'] and cfg['planner']==prior['planner'])
 for name,h in read(OUT/'setup_manifest.json')['unchanged_core'].items():check('unchanged core '+name,sha(HERE/name)==h==sha(Path(cfg['source_run'])/'executed_source'/name))
 check('same original baseline case',case==read(base['baseline_request_path'])['context']['case'])
 check('two distinct source grounded roles',len(roles)==2 and validate_roles(case,roles)==roles)
 for label,change in [('unknown fact',lambda r:r[0].update(fact_id='H99-1')),('bad basis',lambda r:r[0].update(basis='存在しない根拠')),('duplicate role',lambda r:r.append(copy.deepcopy(r[0]))),('unexpected field',lambda r:r[0].update(expected_speech='台詞'))]:
  rr=copy.deepcopy(roles);change(rr);rejects(label,lambda:RoleControl(case,rr))
 rejects('cannot request unbounded3 calls',lambda:RoleControl(case,roles,3))
 c=RoleControl(case,roles);snapshot=c.snapshot();snapshot['roles'][0]['label']='mutation';check('snapshot and caller immutable',c.roles==roles and case==base['case'])
 rejects('cannot begin second role first',lambda:c.begin(roles[1]['id']))
 c.begin(roles[0]['id']);rejects('cannot begin while in flight',lambda:c.begin(roles[0]['id']))
 one='A賞の景品はたくさんあるのに、当たらないんですよね。';two='9000円なら、普通に一つ買えたんじゃないかなって。悔しいですね。'
 c.finish('CPU1',one,None);check('only first role observed by cue',list(c.observed)==['result_mismatch'])
 check('actual delivered body reaches next history',c.case()['history'][-1]['text']==one and c.case()['facts']==case['facts'])
 c.begin(roles[1]['id']);c.finish('CPU2',two,None)
 check('normal terminal state no next call',c.next_role() is None and c.stop_reason=='all_angles_have_literal_cues_unverified')
 rejects('cannot finish same attempt twice',lambda:c.finish('CPU2',two,None))
 rejects('no retries after finished roles',lambda:c.begin(roles[0]['id']))
 check('literal cues are not semantic certification',all(x['semantic_status']=='unverified' for x in c.observed.values()) and not c.snapshot()['source_fact_progress_updated'])
 check('actual purchase not mistaken for hypothetical',not literal_angle_evidence('9000円で普通に一つ買いました。'))
 check('unrelated mention not marked as comparison',not literal_angle_evidence('9000円使ったけど、景品は当たりました。'))
 check('wide numeric and comma normalization','purchase_comparison' in literal_angle_evidence('９，０００円なら、一つ買えたかも。'))
 class Stub:
  def __init__(self,texts):self.texts=texts;self.n=0;self.seen=[]
  def call(self,role,prompt,seed,context):
   self.n+=1;assert self.n<=len(self.texts);assert role=='surface' and prompt==render(context['case'],context['role_spec']) and seed==base['seed']
   self.seen.append(copy.deepcopy(context));body=self.texts[self.n-1]
   return 'CPU'+str(self.n),dict(body=body,raw_output=body+'<turn|>',official_stop_reached=True)
 def mock_rollout(texts):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);write(p/'baseline_case.json',base);write(p/'roles.json',roles);d=Stub(texts)
   with patch.object(run_cpu,'OUT',p):out=run_cpu.rollout(d,cfg)
   return d,out
 d,out=mock_rollout([one,two]);check('actual rollout uses2 roles and real prior text',d.n==2 and d.seen[1]['case']['history'][-1]['text']==one and out['records'][1]['delivered'])
 d,out=mock_rollout([base['baseline_body']]);check('already expressed both roles stop after1',d.n==1 and out['final_control']['stop_reason']=='all_angles_have_literal_cues_unverified')
 d,out=mock_rollout(['そうなんですよね。','そういう感じです。']);check('ambiguous text stops at bound without meaning claim',d.n==2 and not out['final_control']['observed_angles'] and out['final_control']['semantic_status']=='unverified')
 d,out=mock_rollout(['']);check('format failure stops without quality retry',d.n==1 and not out['records'][0]['delivered'] and out['final_control']['stop_reason']=='format_held_no_retry')
 d,out=mock_rollout([case['history'][-1]['text']]);check('exact prior duplicate held without another call',d.n==1 and out['records'][0]['format_reason']=='exact_duplicate_history')
 proc,torch=load_processor();a=prepare(proc,render_a(case));first=prepare(proc,render(case,roles[0]));c=RoleControl(case,roles);c.begin(roles[0]['id']);c.finish('CPU1',one,None);second=prepare(proc,render(c.case(),roles[1]))
 req=read(base['baseline_request_path']);check('official baseline Processor exactly reconstructs',all(req[k]==v for k,v in a.items()))
 for name,p,role in [('first',first,roles[0]),('mock second',second,roles[1])]:
  check(name+' role reaches official decoded input',role['instruction'] in p['decoded_input'] and role['basis'] in p['decoded_input'])
  check(name+' fixed complete Fact remains available',all(f['claim'] in p['decoded_input'] for f in case['facts']))
  check(name+' complete context without truncation',len(p['processor_fields']['input_ids'][0])+384<8192)
  check(name+' unchanged official generation template',p['template_kwargs']==a['template_kwargs'])
 check('first exact original initial history',all(h['text'] in first['decoded_input'] for h in case['history']))
 check('mock second actual feedback reaches tokens',one in second['decoded_input'] and case['history'][0]['text'] not in second['decoded_input'])
 check('original full-task instruction not carried forward','今回話す内容はすべて扱い' not in first['user_prompt'] and '今回の役割だけ' in first['user_prompt'])
 ref=read(OUT/'reference/common_first.json');rr=read(ref['baseline_request_path']);check('same saved common first reference',ref['baseline_body']==case['history'][-1]['text'] and all(rr[k]==v for k,v in prepare(proc,render_a(ref['case'])).items()))
 write(OUT/'prepared_inputs.json',dict(baseline=a,first_controlled=first,cpu_mock_second=second,mock_second_is_not_real_generation=True))
 result=dict(status='pass',checks=checks,check_count=len(checks),new_model_calls=0,context_cut_tokens=0,prepared_inputs_sha256=sha(OUT/'prepared_inputs.json'),input_token_counts=dict(baseline=len(a['processor_fields']['input_ids'][0]),first_controlled=len(first['processor_fields']['input_ids'][0]),cpu_mock_second=len(second['processor_fields']['input_ids'][0])),second_actual_input_checked_after_generation=True)
 verify();write(OUT/'cpu_preflight.json',result);print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
if __name__=='__main__':main()
