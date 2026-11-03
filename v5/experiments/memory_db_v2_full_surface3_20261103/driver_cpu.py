from common import *
from stripe_runtime import validate_request
class Driver:
 def __init__(self,state,cfg,proc,torch,native):
  self.state=state;self.cfg=cfg;self.proc=proc;self.torch=torch;self.native=native;self.n=0
 def call(self,role,prompt,seed,context):
  if role!='surface':raise ValueError('Only Surface allowed')
  self.n+=1
  if self.n>self.cfg['max_calls']:raise ValueError('Bounded call budget exhausted')
  assert self.cfg['prefix_reuse']==[]
  cid=f'R{self.n:04}'
  messages=[dict(role='user',content=[dict(type='text',text=prompt)])]
  kw=dict(tokenize=True,return_dict=True,return_tensors='pt',add_generation_prompt=True,enable_thinking=False)
  f=self.proc.apply_chat_template(messages,**kw);ids=f['input_ids'][0].tolist();dec=self.proc.decode(ids,skip_special_tokens=False)
  assert self.proc.tokenizer.encode(dec,add_special_tokens=False)==ids
  req=dict(call_id=cid,role=role,seed=seed,context=context,user_prompt=prompt,messages=messages,template_kwargs=kw,processor_fields={k:v.tolist() for k,v in f.items()},decoded_input=dec)
  validate_request(req)
  path=OUT/'requests'/(cid+'.json');assert not path.exists();write(path,req)
  self.state.update(phase='waiting_output',call_id=cid,role=role,calls_submitted=self.n);write(OUT/'controller.json',self.state)
  dest=OUT/'inference'/(cid+'.output.json');deadline=time.monotonic()+2400
  while not dest.exists():
   if self.native.poll() is not None:raise RuntimeError('GPU native exited before output')
   if time.monotonic()>deadline:raise TimeoutError('Inference deadline exceeded')
   time.sleep(.5)
  rec=read(dest);assert rec['request_sha256']==sha(path)
  assert rec['input_ids']==ids and self.proc.decode(rec['output_ids'],skip_special_tokens=False)==rec['raw_output']
  parsed=self.proc.parse_response(rec['raw_output'],prefix=self.torch.tensor([ids]));assert parsed.get('role')=='assistant' and isinstance(parsed.get('content'),str)
  rec.update(body=parsed['content'],parsed=parsed)
  write(OUT/'deliveries'/(cid+'.json'),dict(call_id=cid,body=rec['body'],raw_output=rec['raw_output'],parsed=parsed,request_sha256=sha(path),output_sha256=sha(dest)))
  self.state['calls_completed']=self.n;write(OUT/'controller.json',self.state)
  return cid,rec
