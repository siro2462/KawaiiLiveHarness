from common import *
import copy,tempfile,collections
from unittest.mock import patch
from processor_cpu import load_processor,prepare
from cpu_selector import select,load_engine
from stripe_runtime import render_sample,validate_sample,format_reason,text_units
import run_cpu
def main():
 cfg=verify();samples=read(OUT/'samples.json');fixed=read(OUT/'memory_fixed.json');old=read(OUT/'reference/baseline/samples.json');selections=read(OUT/'cpu_selections.json');checks=[]
 def check(n,v):checks.append(dict(name=n,passed=bool(v)));assert v,n
 def reject(n,fn):
  try:fn();ok=False
  except (AssertionError,ValueError,KeyError):ok=True
  check(n,ok)
 check('same exact LoRA model generation conditions',cfg['surface']==read(Path(cfg['source_run'])/'protocol.json')['surface'] and cfg['surface_seed']==20260925)
 check('one new Surface call per independent10 materials',len(samples)==cfg['max_calls']==10 and not cfg['prefix_reuse'])
 check('Planner Guard training quality retry all zero',all(cfg[k]==0 for k in ['new_planner_calls','new_guard_calls','training','quality_retries']))
 for n,h in read(OUT/'setup_manifest.json')['unchanged_core'].items():check('byte-identical core '+n,sha(HERE/n)==h==sha(Path(cfg['source_run'])/'executed_source'/n))
 h=Path(cfg['h06_source_run']);check('exact H06 selector source bytes',sha(OUT/'reference/h06_engine/engine.py')==sha(h/'reference/stripe_engine/engine.py'))
 engine=load_engine();tr=engine.Engine(seed=17,mode='state',allow_cross=False).run('H06');hs=read(h/'steps32.json')
 check('positive control exact original H06 all32',len(tr)==len(hs)==32 and all((a['node_id'],a['operation'],a['epistemic'],a['color'])==(b['memory_id'],b['operation'],b['epistemic'],b['kind']) for a,b in zip(tr,hs)))
 proc,torch=load_processor();prepared={};counts={}
 for s,m,b in zip(samples,fixed,old):
  sid=s['id'];choice=select(m)
  # Canonical JSON removes tuple/list storage representation differences without dropping fields.
  canonical=lambda z:json.loads(json.dumps(z,ensure_ascii=False))
  check(sid+' fixed Memory nodes/source/history unchanged',s['nodes']==m['nodes']==b['nodes'] and s['provenance']==b['provenance'] and s['initial_history']==[])
  check(sid+' selected cache exactly reproducible',canonical(choice)==selections[sid] and s['steps']==choice['steps'])
  check(sid+' observing candidates does not change decisions',select(m,observe=False)['trace']==choice['trace'])
  poison=copy.deepcopy(m);poison['steps']=[{'operation':'MANUAL_POISON','memory_id':'L99'}];poison['nodes'].reverse();poison['provenance']={'source_text':'POISON'}
  for n in poison['nodes']:n['source_quotes']=['POISON'];n['source_line_numbers']=[999]
  check(sid+' ignores old operations source order and quotes',select(poison)['steps']==choice['steps'])
  renamed=copy.deepcopy(m)
  for i,n in enumerate(renamed['nodes']):n['id']='ALT'+str(1000-i)
  other=select(renamed)['steps'];check(sid+' IDs carry no original order signal',[(x['content'],x['operation'],x['epistemic']) for x in other]==[(x['content'],x['operation'],x['epistemic']) for x in choice['steps']])
  check(sid+' CPU output accepted without manual reorder',validate_sample(s))
  prompt,payload=render_sample(s);inp=prepare(proc,prompt);prepared[sid]=inp
  actual=json.loads(inp['decoded_input'].split('【今回の操作列】\n',1)[1].split('<turn|>',1)[0])
  check(sid+' exact whole selected sequence reaches decoded input',actual==choice['steps']==payload['steps'])
  check(sid+' no truncation plus fixed1536 fits8192',len(inp['processor_fields']['input_ids'][0])+1536<8192)
  check(sid+' independent empty history',payload['history']==[] and '【直前の発話】\nなし' in prompt)
  check(sid+' fewshot present and examples separated','え、かぶった。……嘘やん。また同じ？' in prompt and '例の出来事や文句を今回の事実として混ぜない' in prompt)
  bad=copy.deepcopy(s);bad['steps'][0]['content']+='改変';reject(sid+' altered Memory content rejected',lambda:validate_sample(bad))
  bad=copy.deepcopy(s);bad['steps'][0]['anchor_id']='FUTURE';reject(sid+' invalid previous anchor rejected',lambda:validate_sample(bad))
  counts[sid]=dict(operations=len(s['steps']),unique_nodes=len({x['memory_id'] for x in s['steps']}),revisits=sum(x['operation']=='REVISIT' for x in s['steps']),omitted_ids=sorted({n['id'] for n in s['nodes']}-{x['memory_id'] for x in s['steps']}),input_tokens=len(inp['processor_fields']['input_ids'][0]))
 for b,e,w in [('',True,'empty'),('SPECULATE L01',True,'markup_or_operation_leak'),('途中。',False,'incomplete_stop_or_token_cap'),('え、かぶった。嘘やん。',True,None)]:check('format '+repr(b),format_reason(b,e)==w)
 class Stub:
  def __init__(self,held):self.n=0;self.held=held;self.contexts=[]
  def call(self,role,prompt,seed,context):
   self.n+=1;self.contexts.append(context);assert role=='surface' and seed==cfg['surface_seed']
   b='' if self.held else 'CPU模擬の短い本文。';return f'R{self.n:04}',dict(body=b,raw_output=b+'<turn|>',official_stop_reached=True)
 for held in [False,True]:
  with tempfile.TemporaryDirectory(dir=OUT/'cpu_temp') as tmp:
   q=Path(tmp);write(q/'samples.json',samples);write(q/'cpu_selections.json',selections)
   with patch.object(run_cpu,'OUT',q):stub=Stub(held);result=run_cpu.rollout(stub,cfg)
   check('real controller ten bounded no retries '+str(held),stub.n==10 and result['completed_samples']==10)
   check('real controller payload order all same as CPU '+str(held),all(c['payload']['steps']==selections[s['id']]['steps'] for c,s in zip(stub.contexts,samples)))
   check('real controller delivery histories '+str(held),all(x['delivered']==(not held) and len(x['after_history'])==(0 if held else 1) for x in result['records']))
 write(OUT/'prepared_inputs.json',dict(by_sample=prepared,CPU_no_generation=True))
 result=dict(status='pass',check_count=len(checks),checks=checks,new_model_calls=0,prepared_inputs_sha256=sha(OUT/'prepared_inputs.json'),counts=counts,context_cut_tokens=0,manual_reordering=False)
 verify();write(OUT/'cpu_preflight.json',result);print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
if __name__=='__main__':main()
