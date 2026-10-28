from common import *
import copy,tempfile
from unittest.mock import patch
from processor_cpu import load_processor,prepare
from stripe_runtime import *
from baseline_stripe_runtime import render as base_render
import run_cpu

def main():
 cfg=verify();samples=read(OUT/'samples.json');checks=[]
 def check(n,v):checks.append(dict(name=n,passed=bool(v)));assert v,n
 def reject(n,fn):
  try:fn();ok=False
  except (AssertionError,KeyError,ValueError):ok=True
  check(n,ok)
 old=read(Path(cfg['source_run'])/'protocol.json')
 check('same Surface model adapter and all generation options',cfg['surface']==old['surface'])
 check('exact10 bounded independent calls',cfg['max_calls']==10 and not cfg['prefix_reuse'] and len(samples)==10)
 check('five VTuber five fiction',[s['category'] for s in samples].count('vtuber_saved_edited_transcript')==5 and [s['category'] for s in samples].count('designer_original_fiction')==5)
 check('no new Planner Guard training retry',all(cfg[k]==0 for k in ['new_planner_calls','new_guard_calls','training','quality_retries']))
 for n,h in read(OUT/'setup_manifest.json')['unchanged_core'].items():check('unchanged core '+n,sha(HERE/n)==h==sha(Path(cfg['source_run'])/'executed_source'/n))
 check('exact baseline renderer copy',sha(HERE/'baseline_stripe_runtime.py')==sha(Path(cfg['source_run'])/'executed_source/stripe_runtime.py'))
 source=read(OUT/'setup_manifest.json');check('original source bytes unchanged',sha(source['source_path'])==source['source_sha256']==sha(OUT/'reference/luna_edited_source.yaml'))
 prev=Path(cfg['source_run']);mem=read(prev/'memory_h06.json')['nodes'];test=dict(title='ガラポンでA賞が出なかった体験',nodes=mem,steps=read(prev/'steps32.json'),initial_history=[],provenance=dict(source_text='\n'.join(q for n in mem for q in n['source_quotes'])))
 parity,payload=render_sample(test);prior=read(prev/'requests/R0003.json');check('H06 B prompt byte exact through generalized renderer',parity==prior['user_prompt'] and payload==prior['context']['payload'])
 proc,torch=load_processor();prepared={}
 for s in samples:
  sid=s['id'];check(sid+' all32 and29 grounded nodes',validate_sample(s))
  prompt,payload=render_sample(s);inp=prepare(proc,prompt);prepared[sid]=inp
  check(sid+' full input plus1536 within8192',len(inp['processor_fields']['input_ids'][0])+1536<8192)
  check(sid+' independent empty history','【直前の発話】\nなし' in prompt and payload['history']==[])
  check(sid+' all content and epistemic reach official decoded',all(x['content'] in inp['decoded_input'] and x['epistemic'] in inp['decoded_input'] and x['operation'] in inp['decoded_input'] for x in s['steps']))
  check(sid+' theme replaced once',('【現在のテーマ】\n'+s['title']+'\n') in inp['decoded_input'])
  check(sid+' no source schema expected output labels','source_quotes' not in prompt and 'source_text' not in prompt and 'dominant_color' not in prompt and 'provenance' not in prompt)
  altered=copy.deepcopy(s);altered['steps'][0]['epistemic']='invalid';reject(sid+' altered certainty rejected',lambda:validate_sample(altered))
  altered=copy.deepcopy(s);altered['steps'][0]['anchor_id']='NOT_PRESENT';reject(sid+' future anchor rejected',lambda:validate_sample(altered))
  if sid.startswith('V'):check(sid+' source quotes exact',all(q in s['provenance']['source_text'] for n in s['nodes'] for q in n['source_quotes']))
  else:check(sid+' fiction explicitly disclosed',s['provenance']['fiction'] is True and s['provenance']['human_quality_labels']==0)
 for body,eos,expected in [('',True,'empty'),('REPORT L01',True,'markup_or_operation_leak'),('途中。',False,'incomplete_stop_or_token_cap'),('同じ。再び。',True,None)]:check('format '+repr(body),format_reason(body,eos)==expected)
 for body in ['あ。え？\nそう！','  あ。\n\nえ。  ']:check('fixed units retain chars '+repr(body),''.join(x['text'] for x in text_units(body))==body)
 class Stub:
  def __init__(self,held):self.n=0;self.held=held;self.inputs=[]
  def call(self,role,prompt,seed,context):
   self.n+=1;self.inputs.append(context);assert role=='surface' and seed==20260925
   body='' if self.held else 'CPU検査の模擬本文です。'
   return f'R{self.n:04}',dict(body=body,raw_output=body+'<turn|>',official_stop_reached=True)
 for held in [False,True]:
  with tempfile.TemporaryDirectory(dir=OUT/'cpu_temp') as tmp:
   q=Path(tmp);write(q/'samples.json',samples)
   with patch.object(run_cpu,'OUT',q):d=Stub(held);res=run_cpu.rollout(d,cfg)
   check('ten actual controller iterations no retry '+str(held),d.n==10 and res['completed_samples']==10)
   check('actual controller independent histories '+str(held),all(x['before']['history']==[] for x in d.inputs))
   check('adoption/holding observed '+str(held),all(x['delivered']==(not held) and len(x['after_history'])==(0 if held else 1) for x in res['records']))
 write(OUT/'prepared_inputs.json',dict(by_sample=prepared,CPU_no_generation=True))
 result=dict(status='pass',checks=checks,check_count=len(checks),new_model_calls=0,context_cut_tokens=0,prepared_inputs_sha256=sha(OUT/'prepared_inputs.json'),input_tokens={k:len(v['processor_fields']['input_ids'][0]) for k,v in prepared.items()},all_surface_options_fixed=True)
 verify();write(OUT/'cpu_preflight.json',result);print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
if __name__=='__main__':main()
