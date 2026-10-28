from common import *
import copy,tempfile,importlib.util
from unittest.mock import patch
from processor_cpu import load_processor,prepare
from stripe_runtime import *
import run_cpu

def main():
 cfg=verify();steps=read(OUT/'steps32.json');nodes=read(OUT/'memory_h06.json')['nodes'];memory=read(OUT/'legacy_memory.json');checks=[]
 def check(n,c):checks.append(dict(name=n,passed=bool(c)));assert c,n
 def rejects(n,fn):
  try:fn();bad=False
  except(AssertionError,ValueError,KeyError):bad=True
  check(n,bad)
 prior=read(Path(cfg['source_run'])/'protocol.json');new=copy.deepcopy(cfg['surface']);old=copy.deepcopy(prior['surface']);new['generation_config'].pop('max_new_tokens');old['generation_config'].pop('max_new_tokens')
 check('model adapter all generation options except declared cap fixed',new==old and cfg['surface']['generation_config']['max_new_tokens']==1536)
 check('bounded11 no other models or reuse',cfg['max_calls']==11 and all(cfg[k]==0 for k in ['new_planner_calls','new_guard_calls','training','quality_retries']) and not cfg['prefix_reuse'])
 check('empty initial history all arms',read(OUT/'initial_history.json')==[])
 for n,h in read(OUT/'setup_manifest.json')['unchanged_core'].items():check('core bytes '+n,sha(HERE/n)==h==sha(Path(cfg['source_run'])/'executed_source'/n))
 manifest=read(OUT/'reference/source_manifest.json')
 for rel,h in manifest['files'].items():check('source copy '+rel,sha(OUT/'reference/stripe_engine'/rel)==h)
 check('all32 titles epistemic exact source',validate_steps(steps,nodes))
 for label,change in [('unknown node',lambda q:q[0].update(memory_id='X')),('epistemic certainty edit',lambda q:q[28].update(epistemic='observed')),('order edit',lambda q:q.reverse()),('operation edit',lambda q:q[0].update(operation='UNKNOWN'))]:
  q=copy.deepcopy(steps);change(q);rejects(label,lambda:validate_steps(q,nodes))
 spec=importlib.util.spec_from_file_location('stripe_reference_engine',OUT/'reference/stripe_engine/engine.py');eng=importlib.util.module_from_spec(spec);spec.loader.exec_module(eng);trace=eng.Engine(seed=17,mode='state',allow_cross=False).run('H06')
 check('original CPU engine reproduces fixed32 CSV',len(trace)==32 and all(z['node_id']==s['memory_id'] and z['operation']==s['operation'] and z['epistemic']==s['epistemic'] and z['color']==s['kind'] for z,s in zip(trace,steps)))
 check('plan switch rate20/31',sum(a['kind']!=b['kind'] for a,b in zip(steps,steps[1:]))==20)
 jobs=schedule(steps);check('A2 B1 C8 groups',[(s['arm'],len(s['groups'])) for s in jobs]==[('A',2),('B',1),('C',8)])
 check('C four ops each exact complete ordering',[s for g in jobs[2]['groups'] for s in g['steps']]==steps and all(len(g['steps'])==4 for g in jobs[2]['groups']))
 check('late uncertain recall preserved',steps[16]['memory_id']=='L08' and steps[23]['memory_id']=='L07' and steps[28]['memory_id']=='L15')
 proc,torch=load_processor();prepared={};all_inputs=[]
 for spec in jobs:
  history=[]
  for turn,group in enumerate(spec['groups'],1):
   prompt,payload=render(group,history,memory,steps);inp=prepare(proc,prompt);all_inputs.append(dict(arm=spec['arm'],turn=turn,official_input=inp,CPU_mock_history=bool(history)))
   if turn==1:prepared[spec['arm']]=inp
   check(spec['arm']+str(turn)+' full context plus1536',len(inp['processor_fields']['input_ids'][0])+1536<8192)
   if group['kind']=='stripe':
    check(spec['arm']+str(turn)+' actual op content epistemic decoded',all(s['content'] in inp['decoded_input'] and s['epistemic'] in inp['decoded_input'] and s['operation'] in inp['decoded_input'] for s in group['steps']))
    check(spec['arm']+str(turn)+' source quotes absent schema','source_quotes' not in prompt and payload['source_quotes_sent'] is False)
    if spec['arm']=='C':check('C'+str(turn)+' no later step payload',max(s['index'] for s in payload['steps'])==turn*4 and len(payload['steps'])==4)
   if history:check(spec['arm']+str(turn)+' actual mock previous text reaches decoded',history[-1]['text'] in inp['decoded_input'])
   history.append(dict(text='CPU経路検査の前発話'+str(turn)+'。',memory_id='H06',origin='offline text delivered, semantically unverified'))
 check('B versus C same renderer common instructions',prepared['B']['user_prompt'].split('【直前の発話】')[0]==prepared['C']['user_prompt'].split('【直前の発話】')[0])
 check('no teacher example or source chronology transmitted','source_lines' not in prepared['B']['user_prompt'] and 'source_quotes' not in prepared['B']['user_prompt'])
 check('token cap retained as observed failure',format_reason('途中です。',False)=='incomplete_stop_or_token_cap')
 check('legitimate revisits not suppressed',format_reason('9000円。9000円。9000円。9000円。',True) is None)
 check('empty held',format_reason('',True)=='empty')
 check('operation IDs held',format_reason('REPORT L01 内容。',True)=='markup_or_operation_leak')
 check('shared length cap6000',format_reason('あ'*1801+'。',True) is None and format_reason('あ'*6001,True)=='excessive_length_over6000')
 for text in ['あ。え？\nそう！','  あ。\n\nえ。  ','9000円なら、買えたのでは。悔しい。']:
  units=text_units(text);check('fixed segmentation preserves all chars '+repr(text),''.join(x['text'] for x in units)==text)
 class Stub:
  def __init__(self,held=False):self.n=0;self.held=held;self.seen=[]
  def call(self,role,prompt,seed,context):
   self.n+=1;assert role=='surface' and seed==20260925;self.seen.append(context)
   body='' if self.held else 'CPUの経路検査です。'+str(context['turn'])+'。'
   return f'R{self.n:04}',dict(body=body,raw_output=body+'<turn|>',official_stop_reached=True)
 for held in [False,True]:
  with tempfile.TemporaryDirectory() as tmp:
   q=Path(tmp)
   for n in ['steps32.json','memory_h06.json','legacy_memory.json','initial_history.json']:write(q/n,read(OUT/n))
   with patch.object(run_cpu,'OUT',q):d=Stub(held);res=run_cpu.rollout(d,cfg)
   check('actual rollout no retries '+str(held),d.n==(3 if held else 11) and res['completed_arms']==3)
   if not held:check('C delivered actual text enters next real controller prompt',d.seen[4]['before']['history'][-1]['text']=='CPUの経路検査です。1。')
 write(OUT/'prepared_inputs.json',dict(initial_by_arm=prepared,cpu_mock_all=all_inputs,CPU_mock_not_real_generation=True))
 result=dict(status='pass',checks=checks,check_count=len(checks),new_model_calls=0,context_cut_tokens=0,prepared_inputs_sha256=sha(OUT/'prepared_inputs.json'),initial_tokens={k:len(v['processor_fields']['input_ids'][0]) for k,v in prepared.items()},surface_max_new_tokens=1536)
 verify();write(OUT/'cpu_preflight.json',result);print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
if __name__=='__main__':main()
