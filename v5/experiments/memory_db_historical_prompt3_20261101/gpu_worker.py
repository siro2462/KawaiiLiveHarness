from common import *
import traceback,gc,contextlib
def main():
 stage=OUT/'inference';stage.mkdir(exist_ok=False)
 state=dict(status='running',phase='waiting_observer',calls=0,**obs(os.getpid()),started_jst=now());write(stage/'state.json',state)
 try:
  deadline=time.monotonic()+120
  while not (stage/'observer_ready.json').exists():
   if time.monotonic()>deadline:raise TimeoutError('Native observer absent')
   time.sleep(.2)
  ready=read(stage/'observer_ready.json');assert ready['worker_pid']==state['pid'] and abs(ready['worker_created_unix']-state['created_unix'])<.01
  cfg=verify()
  for p in [BETA/'dependencies',GEMMA/'dependencies',MULTI,GEMMA]:sys.path.insert(0,str(p))
  import torch
  from transformers import GenerationConfig
  from prepare_data import tokenizer
  from peft import PeftModel,get_peft_model_state_dict
  from safetensors.torch import load_file
  from load_offloaded import load_base
  from multibase_common import Lock,resources
  from offload_backend import CACHE
  from token_journal import TokenJournal
  assert torch.version.hip and str(CPU_DEPS) not in torch.__file__
  mode=None;model=None;planner=None;tok=None;sw=0
  with Lock(MULTI/'gpu.lock'),Lock(TALK/'lora_v4_planner_talk/gpu.lock'):
   from request_protocol import request_stream
   for n,path in request_stream(OUT,cfg['max_calls']):
    cid=f'R{n:04}';state.update(phase='request_ready',next_call=cid);write(stage/'state.json',state)
    req=read(path)
    if n<=len(cfg['prefix_reuse']):
     dest=stage/(cid+'.output.json');deadline=time.monotonic()+60
     while not dest.exists():
      if (OUT/'stop_requested.json').exists():raise RuntimeError('Controller requested stop')
      if time.monotonic()>deadline:raise TimeoutError('Prefix replay receipt absent')
      time.sleep(.1)
     rec=read(dest);cache=cfg['prefix_reuse'][n-1]
     assert rec['request_sha256']==sha(path) and rec['new_model_generation'] is False
     assert rec['reuse']['source_output_sha256']==sha(cache['output'])==cache['output_sha256'] and rec['reuse']['full_input_context_identical']
     state.update(calls=n,reused_prefix=n,updated_jst=now());write(stage/'state.json',state);continue
    if req['role'] not in ('planner','surface'):raise ValueError('No semantic judge role in this offline experiment')
    wanted='planner' if req['role']=='planner' else 'instruct'
    if mode!=wanted:
     state.update(phase='load_'+wanted);write(stage/'state.json',state)
     model=None;planner=None;tok=None;gc.collect();CACHE.clear();torch.cuda.empty_cache()
     if wanted=='planner':
      from inference_v5 import V5Models
      planner=V5Models(planner_only=True);model=planner.model;tok=planner.tok
      adapter=Path(cfg['planner']['adapter']);disk=load_file(str(adapter/'adapter_model.safetensors'),device='cpu');live=get_peft_model_state_dict(model,adapter_name='planner')
     else:
      key=cfg['surface']['model_key'];base,_,_,_=load_base(key);base.name_or_path=str(MULTI/'models'/key);base.config._name_or_path=base.name_or_path
      adapter=Path(cfg['surface']['adapter']);model=PeftModel.from_pretrained(base,str(adapter),is_trainable=False,local_files_only=True);del base
      tok=tokenizer(key);disk=load_file(str(adapter/'adapter_model.safetensors'),device='cpu');live=get_peft_model_state_dict(model)
     assert set(disk)==set(live) and all(torch.equal(disk[k],live[k].detach().cpu()) for k in disk)
     assert not any(p.requires_grad for p in model.parameters());del disk,live
     model.eval();model.config.use_cache=True;mode=wanted;sw+=1
     write(stage/f'identity_{sw:03}.json',dict(role=mode,model_key=cfg[mode if mode=='planner' else 'surface']['model_key'],adapter=str(adapter),adapter_sha256=sha(adapter/'adapter_model.safetensors'),adapter_tensors_loaded_exact=True,training=False))
    state.update(phase='generate',call_id=cid,role=req['role'],updated_jst=now());write(stage/'state.json',state)
    started=time.perf_counter()
    if wanted=='planner':
     rec=planner.constrained_plan(req['prompt'],req['recent'],req['candidate_ids'],req['seed'],budget=2048,max_new_tokens=256)
     rec['official_stop_reached']=rec['strict_schema_valid'];rec['raw_output']=tok.decode(rec['output_ids'],skip_special_tokens=False)
    else:
     ids=req['processor_fields']['input_ids'][0];mask=req['processor_fields']['attention_mask'][0]
     assert tok.decode(ids,skip_special_tokens=False)==req['decoded_input']
     gen=GenerationConfig.from_dict(cfg['surface']['generation_config'])
     torch.manual_seed(req['seed']);torch.cuda.manual_seed_all(req['seed'])
     journal=TokenJournal(stage/(cid+'_token_journal.jsonl'),ids,lambda x:tok.decode(x,skip_special_tokens=False),cid)
     with contextlib.nullcontext():
      with torch.inference_mode():v=model.generate(input_ids=torch.tensor([ids],device='cuda'),attention_mask=torch.tensor([mask],device='cuda'),generation_config=gen,streamer=journal)
     out=v[0,len(ids):].detach().cpu().tolist();journal.close();assert out==journal.ids
     rec=dict(input_ids=ids,output_ids=out,raw_output=tok.decode(out,skip_special_tokens=False),official_stop_reached=bool(out and out[-1] in cfg['surface']['eos_ids']),generation_config=gen.to_dict(),journal_sha256=sha(journal.path),seed=req['seed'],adapter_disabled=False,resources=resources(torch))
     del v
    rec.update(new_model_generation=True,call_id=cid,role=req['role'],seconds=round(time.perf_counter()-started,3),request_sha256=sha(path))
    write(stage/(cid+'.output.json'),rec);state.update(calls=n,updated_jst=now());write(stage/'state.json',state)
   verify()
  state.update(status='complete',phase='worker_complete',finished_jst=now());write(stage/'state.json',state)
 except BaseException as e:
  state.update(status='failed',error=str(e),traceback=traceback.format_exc(),finished_jst=now());write(stage/'state.json',state);raise
if __name__=='__main__':main()

