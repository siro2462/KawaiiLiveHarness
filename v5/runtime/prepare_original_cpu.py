from common import *
import ast,copy,tempfile,subprocess,shutil
from runtime import *
from continuous_policy import *
from driver_cpu import Driver

def main():
 cfg=verify();checks=[];metrics={}
 def check(n,v):
  if not v:raise AssertionError(n)
  checks.append(n)
 for path in [BETA/'dependencies',GEMMA/'dependencies',GEMMA,MULTI,HERE/'vendor']:sys.path.insert(0,str(path))
 from alpha import Alpha
 from planner_policy import parse_plan
 from prepare_data import tokenizer
 from contract_runtime import render
 tok=tokenizer(cfg['planner']['model_key'])
 tree=ast.parse((MULTI/'inference_models.py').read_text(encoding='utf-8'));node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='protected_ids');ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(MULTI/'inference_models.py'),'exec'),ns);protected=ns['protected_ids']
 sys.path.insert(0,str(CPU_DEPS));import torch
 from transformers import AutoProcessor
 check('CPU-only torch',torch.__version__.endswith('+cpu') and not torch.cuda.is_available())
 proc=AutoProcessor.from_pretrained(str(MULTI/'models'/cfg['surface']['model_key']),local_files_only=True,trust_remote_code=False)
 class Capture(Driver):
  def __init__(self):self.input=None
  def call(self,role,request,seed,context):
   self.input=(request,context)
   return 'CPU',dict(text=json.dumps(dict(use_memory=False,memory_id=None,topic='CPU',flow=['未生成','未生成']),ensure_ascii=False))
 root=OUT/'cpu_sandbox_attempt2';root.mkdir(exist_ok=False)
 a=Alpha(root/'alpha.sqlite');a.populate(HERE/'sources/v1_2.zip',HERE/'sources/fixtures_20.json');sig=signature(a);allm=a.all('fixtures')
 check('20 eligible synthetic memories only',set(m['id'] for m in allm)==set(cfg['eligible_memory_ids']) and all(m['authority']=='synthetic_fixture' for m in allm))
 check('94 original facts',sum(len(facts_for(m)) for m in allm)==94)
 check('computed 55 utterance bound',sum((len(facts_for(m))+1)//2 for m in allm)==55)
 check('110 call bound equals two per utterance',cfg['max_calls']==2*cfg['max_surface_calls']==2*cfg['max_replan_calls']==110)
 check('text duration assumption',cfg['target_chars']/cfg['chars_per_minute_assumption']==10)
 check('count excludes whitespace only',count_chars(' あ\nいう　。 ')==4)
 es=EventStore(root/'events.sqlite');es.append('format_held',dict(text='HELD'));check('held absent in actual history',es.recent()==[])
 es.append('text_delivery_confirmed',dict(text='x'*400,memory_id='F01'));es.append('text_delivery_confirmed',dict(text='y'*401,memory_id='F01'));check('800-char bound',len(es.recent())==1 and es.recent()[0]['text']=='y'*401)
 es.append('text_delivery_confirmed',dict(text='z',memory_id='F01'));check('last two delivered entries',len(es.recent())==2 and [x['text'] for x in es.recent()]==['y'*401,'z']);es.close()
 # Exercise the unchanged selector through all reachable source topics with source-only mock text. No model output claimed.
 recent='';selected=[];calls=0
 for index in range(1,22):
  m,traces=choose(a,recent,set(cfg['eligible_memory_ids']),index)
  if not m:break
  check(f'{index} alpha proposal is eligible and unseen',m['id'] not in selected and any(t['result']['proposal'].get('memory_ids')==[m['id']] for t in traces))
  selected.append(m['id']);p=Progress(m,None)
  while p.pending():
   ids=p.focus('C');check(m['id']+' source target1-2 '+str(calls),1<=len(ids)<=2)
   p.presented(ids);text=''.join(f['claim'] for f in facts_for(m) if f['id'] in ids);calls+=1;p.finish(ids,text,calls);observe_alpha(a,m,p,True);recent=text
  check(m['id']+' no semantic promotion',all(f['semantic_status']=='unverified' and f['presentations']==1 for f in p.facts.values()))
 check('no repeated memory',len(selected)==len(set(selected)))
 check('source/link invariants after selector+progress',signature(a)==sig)
 metrics['mock_selector_memory_sequence']=selected;metrics['mock_selector_topics']=len(selected);metrics['mock_surface_calls']=calls
 # Actual canonical Planner builder equals old Driver.replan, including generated recent protection.
 planner_tokens=[];surface_tokens=[]
 for m in allm:
  p=Progress(m,None);ids=p.focus('C');p.presented(ids);p.finish(ids,'CPU',1)
  prev=dict(use_memory=False,memory_id=None,topic=m['title'],flow=['続き','未提示部分'])
  recent='あの話、まだ続きがあってさ。'*20
  cap=Capture();cap.replan(m,recent,cfg['seeds'][0],prev,p.snapshot())
  req,ctx=make_planner_request(m,recent,prev,p.snapshot());check(m['id']+' unchanged actual Planner builder',cap.input==(req,ctx))
  ii,cut=protected(tok,req['prompt'],recent,budget=2048);check(m['id']+' no Planner context cut representative',cut==0);planner_tokens.append(len(ii))
  # Extreme permitted history, plus source progress and previous Plan remain protected by existing budget routine.
  extreme='あ'*800;rq,_=make_planner_request(m,extreme,prev,p.snapshot());ei,ec=protected(tok,rq['prompt'],extreme,budget=2048)
  check(m['id']+' bounded/protected extreme Planner input',len(ei)<=2048 and ec>=0)
  h=[dict(text='前の本文。',memory_id=m['id'],origin='offline text delivered, semantically unverified')];c=surface_case(m,p.focus('C') or Progress(m,None).focus('C'),h,[],'',m['id']);prompt=render(c)
  kw=dict(tokenize=True,return_dict=True,return_tensors='pt',add_generation_prompt=True,enable_thinking=False);messages=[dict(role='user',content=[dict(type='text',text=prompt)])];f=proc.apply_chat_template(messages,**kw);tt=f['input_ids'][0].tolist()
  check(m['id']+' official Processor exact roundtrip',proc.tokenizer.encode(proc.decode(tt,skip_special_tokens=False),add_special_tokens=False)==tt)
  check(m['id']+' Surface context limit',len(tt)+384<8192);surface_tokens.append(len(tt))
  check(m['id']+' actual history reaches Surface',h[0]['text'] in prompt)
  p.reorder(prev);check(m['id']+' false Plan preserves fixed order',p.order==p.ids)
 check('source/link invariants after input controls',signature(a)==sig);a.close()
 # Strict schema failure and no quality retries: existing parser rejects, orchestration has a single call before its exception.
 try:parse_plan('{"topic":"broken"}', ['F01']);bad=False
 except ValueError:bad=True
 check('invalid Plan rejected rather than rescued',bad)
 check('quality retries forbidden',cfg['quality_retries']==0 and not cfg['semantic_guard'] and cfg['prefix_reuse']==[])
 # Import actual launch target through child_guard with the same PYTHONPATH transport. Imports only, no main/model.
 env=dict(os.environ,PYTHONPATH=os.pathsep.join(map(str,[HERE,BETA,MULTI,GEMMA])),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONIOENCODING='utf-8')
 receipt=OUT/'startup_import.python_outcome.json'
 q=subprocess.run([cfg['gpu_python'],'-X','utf8','-B',str(MULTI/'child_guard.py'),'--receipt',str(receipt),str(HERE/'startup_import_probe.py')],cwd=BETA,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
 (OUT/'startup_import.stdout.txt').write_text(q.stdout,encoding='utf-8');(OUT/'startup_import.stderr.txt').write_text(q.stderr,encoding='utf-8')
 check('actual child_guard import and exit0',q.returncode==read(receipt)['exit_code']==0)
 metrics.update(planner_tokens=planner_tokens,surface_tokens=surface_tokens,model_calls=0,actual_tts=False)
 verify();write(OUT/'cpu_preflight.json',dict(status='pass',count=len(checks),checks=checks,metrics=metrics,source_identity_sha256=sha(OUT/'source_identity.json'),startup_python_outcome_sha256=sha(receipt),meaning='CPU plumbing only; no generated speech/Planner quality certification'))
 print(json.dumps(dict(status='pass',checks=len(checks),mock_topics=len(selected),mock_surface_calls=calls,planner_token_range=[min(planner_tokens),max(planner_tokens)],surface_token_range=[min(surface_tokens),max(surface_tokens)],model_calls=0),ensure_ascii=False))
if __name__=='__main__':main()
