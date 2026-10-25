from common import *
import copy,importlib,ast

def main():
 cfg=verify();checks=[]
 for f in HERE.rglob('*.py'):ast.parse(f.read_text(encoding='utf-8'));checks.append('syntax:'+f.name)
 for x in [BETA/'dependencies',GEMMA/'dependencies',GEMMA,MULTI,HERE/'vendor']:sys.path.insert(0,str(x))
 from alpha import Alpha
 import run_cpu as runner
 from runtime import EventStore,facts_for,surface_case,Progress
 from continuous_policy import signature
 from contract_runtime import render
 sys.path.insert(0,str(CPU_DEPS));import torch
 from transformers import AutoProcessor
 assert torch.__version__.endswith('+cpu') and not torch.cuda.is_available()
 proc=AutoProcessor.from_pretrained(str(MULTI/'models'/cfg['surface']['model_key']),local_files_only=True,trust_remote_code=False)
 refs=read(OUT/'reference/source_pairs.json');fixtures=read(HERE/'sources/fixtures_20.json')
 assert len(refs)==len(fixtures)==4 and sum(len(m['beats']) for m in fixtures)==9
 for r,m in zip(refs,fixtures):
  assert ''.join(f['claim'] for f in facts_for(m))==r['memory']
  assert r['human_text'] not in m['text'];checks.append('exact-memory-projection:'+m['id'])
 real_out=runner.OUT
 for scenario in ['valid_plan','invalid_plan']:
  folder=OUT/'cpu_sandbox'/scenario;folder.mkdir(parents=True,exist_ok=False)
  for d in ['plans','selections','turns']:(folder/d).mkdir()
  a=Alpha(folder/'alpha.sqlite');a.populate(HERE/'sources/v1_2.zip',HERE/'sources/fixtures_20.json');before=signature(a);seen=[];requests=[]
  class FakeDriver:
   n=0
   def call(self,role,prompt,seed,context):
    self.n+=1;cid=f'R{self.n:04}';assert self.n<=10
    if role=='planner':
     assert isinstance(prompt,dict);requests.append(prompt['prompt'])
     raw='{bad' if scenario=='invalid_plan' else json.dumps(dict(use_memory=False,memory_id=None,topic='CPU only',flow=['CPU1','CPU2']))
     return cid,dict(text=raw,raw_output=raw,official_stop_reached=scenario!='invalid_plan')
    assert prompt==render(context['case']);requests.append(prompt);ids=context['target_ids'];seen.extend(ids)
    fields=proc.apply_chat_template([dict(role='user',content=[dict(type='text',text=prompt)])],tokenize=True,return_dict=True,return_tensors='pt',add_generation_prompt=True,enable_thinking=False)
    ids0=fields['input_ids'][0].tolist();dec=proc.decode(ids0,skip_special_tokens=False);assert proc.tokenizer.encode(dec,add_special_tokens=False)==ids0 and len(ids0)+384<8192
    checks.append('official-processor-no-cut:'+scenario+':'+cid)
    body=''.join(f['claim'] for f in context['case']['facts'])
    return cid,dict(body=body,raw_output=body+'<turn|>',official_stop_reached=True)
  es=EventStore(folder/'events.sqlite');d=FakeDriver();runner.OUT=folder
  rr=runner.rollout(a,d,cfg,es,dict(status='cpu_test',calls_completed=0))
  es.close();assert signature(a)==before;a.close();runner.OUT=real_out
  assert len(rr['records'])==5 and len(seen)==len(set(seen))==9 and len(rr['selections'])==4 and rr['stop_reason']=='all_eligible_source_presented'
  assert rr['planner_format_fallbacks']==(5 if scenario=='invalid_plan' else 0)
  for text in requests:
   assert not any(r['human_text'] in text for r in refs)
   assert 'style:' not in text and 'future_trajectory' not in text
  checks.extend(['all9-targets-once:'+scenario,'all4-alpha-selected:'+scenario,'history-from-delivered-only:'+scenario,'source-memory-links-unchanged:'+scenario,'no-human-reference-in-requests:'+scenario,'bounded10calls:'+scenario])
 audit=dict(status='pass',CPU_checks=len(checks),checks=checks,new_model_calls=0,official_processor=True,no_context_cut=True,no_human_history=True,no_training=True)
 write(OUT/'cpu_preflight.json',audit);verify();print(json.dumps({k:v for k,v in audit.items() if k!='checks'},ensure_ascii=False))
if __name__=='__main__':main()
