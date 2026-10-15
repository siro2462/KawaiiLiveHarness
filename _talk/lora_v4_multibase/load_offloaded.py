"""Load only validated local CPU NF4 caches, with no whole-model .cuda()."""
import json
import torch
from probe import ROOT,sha,emit
from model_layout import construct,install_records,move_buffers,attention_targets

def load_base(key):
    cache=ROOT/'quant_cache'/key
    manifest=json.loads((cache/'manifest.json').read_text(encoding='utf8'))
    assert manifest['status']=='complete'
    model=construct(key)
    for group,info in manifest['groups'].items():
        path=cache/info['file'];assert sha(path)==info['sha256'],'Quantized cache changed'
        emit({'event':'load_offloaded_group','model':key,'group':group})
        # File-backed CPU storage lets Windows page cold experts without first
        # materializing the entire model in limited physical RAM.
        payload=torch.load(path,map_location='cpu',weights_only=True,mmap=True)
        records=[r for r in manifest['records'] if r['group']==group]
        install_records(model,records,payload)
        del payload
    move_buffers(model)
    targets,counts=attention_targets(model,key)
    return model,targets,counts,manifest
