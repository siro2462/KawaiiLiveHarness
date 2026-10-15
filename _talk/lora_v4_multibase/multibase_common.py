import json
import math
import os
import random
import time
from pathlib import Path
from probe import ROOT,TALK,sha,write,emit

RUN=ROOT/'runs/offload_20261009'
SEED=20260925
def now():return time.strftime('%Y-%m-%dT%H:%M:%S%z')
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(s) for s in Path(p).read_text(encoding='utf8').splitlines() if s.strip()]
def log(event,**kw):emit({'time':now(),'event':event,**kw})

def stage_dir(key, kind):
    locations=RUN/'stage_locations.json'
    value=read(locations).get(key,{}).get(kind) if locations.exists() else None
    path=Path(value) if value else RUN/key/kind
    assert path.resolve().is_relative_to((RUN/key).resolve()),'Stage path outside model run'
    return path

class Lock:
    def __init__(self,path):self.path=Path(path);self.owned=False
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        with os.fdopen(fd,'w',encoding='utf8') as f:json.dump({'pid':os.getpid(),'created':now()},f)
        self.owned=True;return self
    def __exit__(self,*_):
        if self.owned:self.path.unlink()

def seed(torch):
    random.seed(SEED);torch.manual_seed(SEED);torch.cuda.manual_seed_all(SEED)

def verify_data(key):
    manifest=read(ROOT/'data'/key/'manifest.json')
    assert manifest['v3']['status']=='pass' and manifest['v4']['status']=='pass'
    for name,digest in read(ROOT/'audit/frozen_prepared_data.json')[key].items():
        assert sha(ROOT/'data'/key/name)==digest,'Prepared data changed: '+name
    for name,digest in read(ROOT/'audit/reference_hashes.json').items():
        assert sha(name)==digest,'Old reference changed: '+name
    return manifest

def batch(torch,row):
    start=row['target_start'];end=len(row['input_ids'])
    assert 0<start<end<=1024
    assert row['labels'][:start]==[-100]*start and row['labels'][start:]==row['input_ids'][start:]
    return {'input_ids':torch.tensor([row['input_ids']],device='cuda'),
        'attention_mask':torch.ones((1,end),dtype=torch.long,device='cuda'),
        'labels':torch.tensor([row['labels'][start-1:]],device='cuda'),
        'logits_to_keep':torch.arange(start-1,end,device='cuda')}

def resources(torch):
    import psutil
    m=psutil.Process().memory_info()
    return {'GPU_peak_allocated_bytes':torch.cuda.max_memory_allocated(),
        'GPU_peak_reserved_bytes':torch.cuda.max_memory_reserved(),
        'process_RAM_bytes':m.rss,'process_RAM_peak_bytes':getattr(m,'peak_wset',m.rss),
        'system_RAM_available_bytes':psutil.virtual_memory().available}
