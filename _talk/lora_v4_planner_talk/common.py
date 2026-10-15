import hashlib
import json
import os
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parent
TALK=ROOT.parent
MODEL=TALK/'lora_talk_v1/raw/hf_model'
V3=TALK/'memory_talk_lora_abc_v2/runs/train_abc_v2_retry_20261004b/checkpoint-0238/adapter'
DATA=ROOT/'data/pilot_20261006c'
RUN=ROOT/'runs/pilot_20261006'
SEED=20260925

def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def rows(p):return [json.loads(s) for s in Path(p).read_text(encoding='utf8').splitlines() if s.strip()]
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def write(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8');tmp.replace(p)
def now():return time.strftime('%Y-%m-%dT%H:%M:%S%z')
def log(event,**kw):print(json.dumps({'time':now(),'event':event,**kw},ensure_ascii=False),flush=True)

class Lock:
    def __init__(self,path):self.path=Path(path);self.owned=False
    def __enter__(self):
        fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        with os.fdopen(fd,'w',encoding='utf8') as f:json.dump({'pid':os.getpid(),'created':now()},f)
        self.owned=True;return self
    def __exit__(self,*args):
        if self.owned:self.path.unlink()

def verify_dataset():
    manifest=read(DATA/'manifest.json')
    if manifest['root_individual_reviews']!=60:raise ValueError('Semantic review incomplete')
    for name,digest in manifest['files'].items():
        if sha(DATA/name)!=digest:raise ValueError('Dataset changed: '+name)
    return manifest

def training_config(kind):
    return {'major_version':4 if kind=='talk' else 1,'role':kind,'epochs':3 if kind=='talk' else 5,
        'learning_rate':2e-5 if kind=='talk' else 1e-4,'gradient_accumulation':8,'microbatch':1,
        'seq_len':1024,'r':8,'alpha':16,'dropout':.05,'seed':SEED,'warmup_ratio':.05,
        'scheduler':'cosine','quantization':'NF4 double quant BF16','target_only_loss':True,
        'checkpoint_selection':'fixed final; never selected on validation/test quality',
        'physical_model':'existing Gemma4 12B, distinct adapters, sequential GPU processes',
        'scope':'small pilot: 10 train / 5 validation / 5 test source trajectories',
        'initialization':'immutable v3 adapter copy' if kind=='talk' else 'fresh adapter on fixed existing Base'}

def load_base(torch,training=False):
    from transformers import AutoModelForMultimodalLM,BitsAndBytesConfig
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0]<10*2**30:
        raise RuntimeError('GPU unavailable or less than 10 GiB free; no process is stopped')
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)
    log('loading_fixed_base',training=training)
    model=AutoModelForMultimodalLM.from_pretrained(str(MODEL),local_files_only=True,
        quantization_config=quant,torch_dtype=torch.bfloat16,device_map={'':'cuda:0'},
        low_cpu_mem_usage=True,attn_implementation='sdpa')
    model.config.use_cache=not training
    return model

def model_batch(torch,row):
    start=row['target_start'];end=len(row['input_ids'])
    assert 0<start<end<=1024 and row['labels'][:start]==[-100]*start
    assert row['labels'][start:]==row['input_ids'][start:]
    # Gemma shifts causal labels internally: keep prior position through last
    # target, passing masked prior token plus every unmasked target token.
    return {'input_ids':torch.tensor([row['input_ids']],device='cuda:0'),
            'attention_mask':torch.ones((1,end),dtype=torch.long,device='cuda:0'),
            'labels':torch.tensor([row['labels'][start-1:end]],device='cuda:0'),
            'logits_to_keep':torch.arange(start-1,end,device='cuda:0')}
