from common import *
import copy,tempfile
from unittest.mock import patch
from processor_cpu import load_processor,prepare
from ag_runtime import Control,render,validate_catalog,literal_observations
import run_cpu

def main():
 cfg=verify();initial=read(OUT/'initial_case.json');catalog=read(OUT/'catalog.json');arms=read(OUT/'arms.json');checks=[]
 def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
 def rejects(name,fn):
  try:fn();bad=False
  except (AssertionError,ValueError):bad=True
  check(name,bad)
 prior=read(Path(cfg['source_run'])/'protocol.json')
 check('fixed model LoRA seed generation condition',cfg['surface']==prior['surface'] and cfg['planner']==prior['planner'])
 check('max28 no auxiliary calls',cfg['max_calls']==28 and all(cfg[k]==0 for k in ['new_planner_calls','new_guard_calls','training','quality_retries']) and not cfg['prefix_reuse'])
 first=read(OUT/'reference/common_first.json');later=read(OUT/'reference/baseline_later.json')
 check('same H06 original facts and pre-H06 initial history',initial['facts']==later['source_facts'] and initial['history']==first['case']['history'])
 for n,h in read(OUT/'setup_manifest.json')['unchanged_core'].items():check('core unchanged '+n,sha(HERE/n)==h==sha(Path(cfg['source_run'])/'executed_source'/n))
 check('all catalog evidence exact source substrings',validate_catalog(initial,catalog))
 for label,change in [('bad evidence',lambda q:q['views'][0].update(basis='架空')),('unknown dependency',lambda q:q['views'][1].update(prerequisites=['UNKNOWN'])),('duplicate viewpoint',lambda q:q['views'][1].update(id='result')),('unknown relation',lambda q:q['links'][0].update(to='UNKNOWN'))]:
  q=copy.deepcopy(catalog);change(q);rejects(label,lambda:validate_catalog(initial,q))
 texts={'result':'1回600円を15回、9000円使ったのにA賞が一度も出なかったんですよ。','anger':'B賞ばかりで、もう許せないって怒っちゃって。','mismatch':'A賞の景品はたくさんあるのに、当たらないんですよね。','purchase':'9000円なら、普通に一つ買えたんじゃないかなって。悔しいですね。'}
 proc,torch=load_processor();prepared={};mock_records=[]
 for arm in arms:
  c=Control(initial,catalog,arm);first_choice=c.choose();p=prepare(proc,render(c,first_choice));prepared[arm['id']]=p
  check(arm['id']+' official complete input without truncation',len(p['processor_fields']['input_ids'][0])+384<8192 and all(f['claim'] in p['decoded_input'] for f in initial['facts']))
  check(arm['id']+' exact initial history reaches decoded input',all(h['text'] in p['decoded_input'] for h in initial['history']))
  observed=[]
  while (choice:=c.choose()) is not None:
   before=c.snapshot();body=texts[choice['view']['id']];actual_prompt=render(c,choice);official=prepare(proc,actual_prompt)
   check(arm['id']+' every mock step official input exact '+str(len(observed)+1),official['user_prompt']==actual_prompt and choice['view']['basis'] in official['decoded_input'] and len(official['processor_fields']['input_ids'][0])+384<8192)
   if c.has('C') and c.appraisal:check(arm['id']+' appraisal reaches decoded input '+str(len(observed)+1),c.appraisal['label'] in official['decoded_input'])
   if c.has('D') and choice['link']:check(arm['id']+' relation reaches decoded input '+str(len(observed)+1),choice['link']['label'] in official['decoded_input'])
   c.begin(choice);c.finish('CPU'+str(len(observed)+1),body,None);observed.append(choice['view']['id'])
   check(arm['id']+' delivered text reaches next prompt '+str(len(observed)),c.recent()[-1]['text']==body and c.snapshot()['verified_fact_ids']==[])
  check(arm['id']+' bounded end and independent source',1<=len(observed)<=4 and initial==read(OUT/'initial_case.json') and c.initial==initial)
  check(arm['id']+' expected feature exposure',observed==(['result','anger','mismatch','purchase'] if arm['id'] in 'FG' else ['result','anger','mismatch']))
  mock_records.append(dict(arm=arm['id'],view_order=observed,final=c.snapshot()))
 # E permits revisiting a fact, while inherited end-of-facts remains until F.
 e=Control(initial,catalog,arms[4]);e.delivered_facts=['H06-1','H06-3'];e.attempts=[dict(view_id='result'),dict(view_id='mismatch')]
 check('E new angle on existing Fact eligible while topic open',next(x for x in e.candidates() if x['view']['id']=='purchase')['eligible'])
 b=Control(initial,catalog,arms[1]);b.delivered_facts=['H06-1','H06-3'];check('B old Fact gate blocks new angle',not next(x for x in b.candidates() if x['view']['id']=='purchase')['eligible'])
 c=Control(initial,catalog,arms[3]);ch=c.choose();c.begin(ch);c.finish('C1',texts['result'],None);ch=c.choose();c.begin(ch);c.finish('C2',texts['anger'],None);ch=c.choose()
 check('C appraisal state grounded and actual text retained',c.appraisal['evidence_id']=='EV2' and c.appraisal['observed_text']==texts['anger'])
 check('D relation affects score and prompt',ch['link']['type']=='contrast' and ch['score_parts']['link']==2 and ch['link']['label'] in render(c,ch))
 g=Control(initial,catalog,arms[6])
 for i,body in enumerate([texts['result'],texts['anger'],texts['mismatch']+texts['purchase']]):
  ch=g.choose();g.begin(ch);g.finish('G'+str(i),body,None)
 check('G lexical observation suppresses already spoken extra view',g.choose() is None and 'purchase' in g.observed and len(g.attempts)==3)
 for arm in arms:
  c=Control(initial,catalog,arm);ch=c.choose();c.begin(ch);c.finish('FAIL','', 'empty');check(arm['id']+' format hold no retry or consumption',c.choose() is None and c.delivered_facts==[])
 check('purchase execution is not hypothetical lexical signal','purchase' not in literal_observations('9000円で普通に一つ買いました。'))
 check('NFKC comma hypothetical recognized','purchase' in literal_observations('９，０００円なら、一つ買えたかも。'))
 class Stub:
  n=0
  def call(self,role,prompt,seed,context):
   self.n+=1;assert role=='surface' and seed==20260925
   body=texts[context['choice']['view']['id']]
   if context['turn']>1:assert context['control_before']['recent'][-1]['text'] in prompt
   return 'R'+str(self.n).zfill(4),dict(body=body,raw_output=body+'<turn|>',official_stop_reached=True)
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp)
  for name in ['initial_case.json','catalog.json','arms.json']:write(root/name,read(OUT/name))
  with patch.object(run_cpu,'OUT',root):d=Stub();result=run_cpu.rollout(d,cfg)
  check('actual controller full seven-arm CPU rollout',result['completed_arms']==7 and d.n==23 and result['actual_surface_calls']==d.n)
 check('official reference contract unchanged',all(read(first['baseline_request_path'])[k]==v for k,v in prepare(proc,__import__('contract_runtime').render(first['case'])).items()))
 write(OUT/'prepared_inputs.json',dict(initial_by_arm=prepared,cpu_mock_records=mock_records,mock_is_not_generation=True))
 verify();summary=dict(status='pass',check_count=len(checks),checks=checks,new_model_calls=0,context_cut_tokens=0,prepared_inputs_sha256=sha(OUT/'prepared_inputs.json'),initial_input_tokens={k:len(v['processor_fields']['input_ids'][0]) for k,v in prepared.items()},feature_warning='A-E may share choices; E eligibility exists but terminal gate retained until F; F/G new choice and lexical stopping are not semantic cognition')
 write(OUT/'cpu_preflight.json',summary);print(json.dumps({k:v for k,v in summary.items() if k!='checks'},ensure_ascii=False))
if __name__=='__main__':main()
