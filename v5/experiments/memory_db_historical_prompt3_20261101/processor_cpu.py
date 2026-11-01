from common import *
def load_processor():
 sys.path.insert(0,str(CPU_DEPS))
 import torch
 from transformers import AutoProcessor
 assert torch.__version__.endswith('+cpu') and not torch.cuda.is_available()
 proc=AutoProcessor.from_pretrained(str(MULTI/'models'/read(OUT/'protocol.json')['surface']['model_key']),local_files_only=True,trust_remote_code=False)
 return proc,torch
def prepare(proc,prompt):
 messages=[dict(role='user',content=[dict(type='text',text=prompt)])]
 kw=dict(tokenize=True,return_dict=True,return_tensors='pt',add_generation_prompt=True,enable_thinking=False)
 fields={k:v.tolist() for k,v in proc.apply_chat_template(messages,**kw).items()}
 ids=fields['input_ids'][0];decoded=proc.decode(ids,skip_special_tokens=False)
 assert proc.tokenizer.encode(decoded,add_special_tokens=False)==ids
 return dict(user_prompt=prompt,messages=messages,template_kwargs=kw,processor_fields=fields,decoded_input=decoded)
