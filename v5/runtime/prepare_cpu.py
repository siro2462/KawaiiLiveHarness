from common import *
import copy,subprocess,tempfile
from runtime import *
from continuous_policy import *

def main():
 cfg=verify();checks=[]
 def check(name,v):
  if not v:raise AssertionError(name)
  checks.append(name)
 for p in [BETA/'dependencies',GEMMA/'dependencies',GEMMA,MULTI,HERE/'vendor']:sys.path.insert(0,str(p))
 from planner_delivery import resolve
 from alpha import Alpha
 import run_cpu,driver_cpu
 from driver_cpu import Driver
 from contract_runtime import render
 invalid_cases=['{','', '```json\n{}\n```', '{"use_memory":true,"memory_id":"UNKNOWN","topic":"x","flow":["a","b"]}', '{"use_memory":false,"memory_id":null,"topic":"x","flow":["a","b"],"extra":1}', '{"use_memory":false,"memory_id":null,"topic":"x","flow":["a","b"],"topic":"y"}']
 for index,text in enumerate(invalid_cases):
  z=resolve(text,['F01']);p=Progress(dict(id='F01',beats=['元の事実A','元の事実B']),None);p.reorder(z['plan'])
  check(f'invalid{index} preserves raw and uses no plan',z['plan'] is None and not z['syntax_valid'] and z['format_fallback'] and z['error'])
  check(f'invalid{index} fixed original target',p.focus('C')==['F01-1','F01-2'] and not p.mapping['adopted'])
 valid=json.dumps(dict(use_memory=False,memory_id=None,topic='棄権',flow=['a','b']),ensure_ascii=False)
 check('valid false is not a format failure',resolve(valid,['F01'])['syntax_valid'] and not resolve(valid,['F01'])['format_fallback'])
 failed=read(Path(cfg['source_failed_run'])/'inference/R0017.output.json');z=resolve(failed['text'],['F08'])
 check('actual previous R0017 becomes no-retry fallback',not z['syntax_valid'] and z['plan'] is None and failed['output_tokens']==256)
 for i,c in enumerate(cfg['prefix_reuse'],1):
  check(f'prefix{i} original input and output SHA',sha(c['request'])==c['request_sha256'] and sha(c['output'])==c['output_sha256'])
 sys.path.insert(0,str(CPU_DEPS));import torch
 from transformers import AutoProcessor
 check('CPU-only torch',torch.__version__.endswith('+cpu') and not torch.cuda.is_available())
 proc=AutoProcessor.from_pretrained(str(MULTI/'models'/cfg['surface']['model_key']),local_files_only=True,trust_remote_code=False)
 sandbox=OUT/'cpu_sandbox';sandbox.mkdir(exist_ok=False)
 fixtures=read(HERE/'sources/fixtures_20.json');claims={m['id']:{f['id']:f['claim'] for f in facts_for(m)} for m in fixtures}
 class Native:
  def poll(self):return None
 class SimDriver(Driver):
  def __init__(self,state,root):
   super().__init__(state,cfg,proc,torch,Native());self.saved_prefix=0;self.root=root;self.sim_planner=0;self.sim_surface=0
  def call(self,role,prompt,seed,context):
   if self.n<len(cfg['prefix_reuse']):
    cid,rec=super().call(role,prompt,seed,context);self.saved_prefix+=1;return cid,rec
   self.n+=1;assert self.n<=cfg['max_calls'];cid=f'R{self.n:04}'
   if role=='planner':
    self.sim_planner+=1
    # Consecutive bad plans must never prevent progress or cause a model retry.
    text='{' if self.sim_planner%3!=0 else json.dumps(dict(use_memory=False,memory_id=None,topic='CPU simulation',flow=['元Fact','未提示部分']),ensure_ascii=False)
    return cid,dict(text=text,raw_output=text,strict_schema_valid=text!='{',new_model_generation=False,cpu_simulation=True)
   assert role=='surface';self.sim_surface+=1
   text=''.join(claims[context['memory_id']][fid] for fid in context['target_ids'])
   # One format-held candidate also must not be reoffered or enter actual history.
   return cid,dict(body=text,raw_output=text+'<turn|>',official_stop_reached=self.sim_surface!=3,new_model_generation=False,cpu_simulation=True)
 root=sandbox/'whole_flow';root.mkdir();(root/'inference').mkdir();original_run=run_cpu.OUT;original_driver=driver_cpu.OUT;run_cpu.OUT=root;driver_cpu.OUT=root
 try:
  a=Alpha(root/'alpha.sqlite');a.populate(HERE/'sources/v1_2.zip',HERE/'sources/fixtures_20.json');sig=signature(a);es=EventStore(root/'events.sqlite');state={};d=SimDriver(state,root)
  simcfg=copy.deepcopy(cfg);simcfg['target_chars']=100000
  result=run_cpu.rollout(a,d,simcfg,es,state)
  check('exact original seventeen-call prefix verified by actual Driver',d.saved_prefix==17)
  check('first new Surface resumes F08-5 after invalid R0017',result['records'][8]['case']['facts'][0]['id']=='F08-5' and result['records'][8]['planner_format_fallback'] and result['records'][8]['plan'] is None)
  check('multiple invalid Plans do not terminate rollout',result['planner_format_fallbacks']>2 and len(result['records'])>9)
  check('single call per Plan and Surface, no retry',d.n==2*len(result['records'])<=cfg['max_calls'])
  used=[f['id'] for row in result['records'] for f in row['case']['facts']];check('all used target IDs unique',len(used)==len(set(used)))
  check('unverified semantics maintained',all(f['semantic_status']=='unverified' for row in result['records'] for f in row['after']['facts'].values()))
  check('memory and links unchanged by continuation/fallback',signature(a)==sig)
  prior=[]
  for row in result['records']:
   keep=[]
   for h in reversed(prior):
    if len(keep)==2 or sum(len(q['text']) for q in keep)+len(h['text'])>800:break
    keep.insert(0,h)
   check(f"T{row['turn']} actual adopted history",[h['text'] for h in row['case']['history']]==[h['text'] for h in keep])
   check(f"T{row['turn']} renderer contract",bool(render(row['case'])))
   if row['delivered']:prior.append(dict(text=row['body']))
  check('format held candidate excluded from history',sum(not x['delivered'] for x in result['records'])==1)
  check('no padding on exhausted sources',not result['target_met'] and result['stop_reason'] in ['all_eligible_source_presented','alpha_no_supported_unmentioned_candidate'])
  check('full source scope reached in mock continuation',len(used)==94 and len(result['records'])==55)
  es.close();a.close()
 finally:run_cpu.OUT=original_run;driver_cpu.OUT=original_driver
 # CPU simulation above used saved raw outputs and source quotations, not new model generation.
 env=dict(os.environ,PYTHONPATH=os.pathsep.join(map(str,[HERE,BETA,MULTI,GEMMA])),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONIOENCODING='utf-8')
 receipt=OUT/'startup_import.python_outcome.json';p=subprocess.run([cfg['gpu_python'],'-X','utf8','-B',str(MULTI/'child_guard.py'),'--receipt',str(receipt),str(HERE/'startup_import_probe.py')],cwd=BETA,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
 (OUT/'startup_import.stdout.txt').write_text(p.stdout,encoding='utf-8');(OUT/'startup_import.stderr.txt').write_text(p.stderr,encoding='utf-8');check('actual child_guard startup import/exit0',p.returncode==read(receipt)['exit_code']==0)
 check('no GPU launch during preflight',not (OUT/'controller.json').exists() and not (OUT/'inference').exists())
 verify();audit=dict(status='pass',count=len(checks),checks=checks,exact_prefix_calls=17,old_failed_Plan_reused_without_regeneration=True,mock_surface_turns=len(result['records']),mock_target_ids=len(used),mock_format_fallbacks=result['planner_format_fallbacks'],new_model_calls=0,actual_tts=False,human_quality_labels=0,source_memory_links_unchanged=True,original251_checks='historical original preflight; fixed source SHA retained, not rerun as251 new checks',startup_receipt_sha256=sha(receipt))
 write(OUT/'cpu_preflight.json',audit);print(json.dumps({k:v for k,v in audit.items() if k!='checks'},ensure_ascii=False))
if __name__=='__main__':main()
