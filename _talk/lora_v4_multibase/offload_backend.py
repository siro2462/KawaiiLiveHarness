"""Frozen NF4 CPU storage with bounded GPU staging and exact input gradients.

No optimizer owns base weights. Backward re-stages the same quantized matrix,
rather than retaining GPU weight tensors across all decoder layers. This module
does not alter installed bitsandbytes, Transformers or PEFT.
"""
from collections import OrderedDict
import copy
import torch
from torch import nn
from torch.nn import functional as F
import bitsandbytes as bnb

class QuantPack:
    def __init__(self, packed, state):
        self.packed=packed.detach().cpu().contiguous()
        self.state=copy.deepcopy(state)
        self.state.to(torch.device('cpu'))
        self.shape=tuple(state.shape)

    @classmethod
    def quantize(cls, weight):
        # Match installed Linear4bit's NF4 block size, nested statistics and dtype.
        packed,state=bnb.functional.quantize_4bit(weight.to('cuda',dtype=torch.bfloat16).contiguous(),
            blocksize=64,compress_statistics=True,quant_type='nf4',quant_storage=torch.uint8)
        return cls(packed,state)

    def serializable(self):
        return {'packed':self.packed,'state':self.state.as_dict(packed=True)}

    @classmethod
    def restore(cls, data):
        return cls(data['packed'],bnb.functional.QuantState.from_dict(dict(data['state']),device=torch.device('cpu')))

    @property
    def nbytes(self):
        n=self.packed.numel()*self.packed.element_size()
        for v in self.state.as_dict(packed=True).values():
            if isinstance(v,torch.Tensor):n+=v.numel()*v.element_size()
        return n

class StageCache:
    """Only packed weights/metadata are cached, never dequantized matrices."""
    def __init__(self, limit_bytes=4*2**30):
        self.limit=int(limit_bytes);self.bytes=0;self.high_water=0
        self.entries=OrderedDict();self.hits=0;self.misses=0;self.evictions=0

    def get(self, pack, device):
        key=(id(pack),str(device))
        if key in self.entries:
            self.hits+=1;self.entries.move_to_end(key)
            return self.entries[key][:2]
        self.misses+=1;n=pack.nbytes
        while self.entries and self.bytes+n>self.limit:
            _,(_,_,size,_)=self.entries.popitem(last=False)
            self.bytes-=size;self.evictions+=1
        q=pack.packed.to(device)
        state=copy.deepcopy(pack.state);state.to(device)
        if n<=self.limit:
            self.entries[key]=(q,state,n,pack);self.bytes+=n;self.high_water=max(self.high_water,self.bytes)
        return q,state

    def clear(self):
        self.entries.clear();self.bytes=0

    def summary(self):
        return {'limit_bytes':self.limit,'current_bytes':self.bytes,'high_water_bytes':self.high_water,
                'hits':self.hits,'misses':self.misses,'evictions':self.evictions}

CACHE=StageCache()

def dequant(pack, device, cache=None):
    q,state=(cache or CACHE).get(pack,device)
    return bnb.functional.dequantize_4bit(q,quant_state=state)

class _FrozenNF4(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, pack, cache):
        ctx.pack=pack;ctx.cache=cache;ctx.dtype=x.dtype
        weight=dequant(pack,x.device,cache)
        y=F.linear(x.to(torch.bfloat16),weight).to(x.dtype)
        return y

    @staticmethod
    def backward(ctx, dy):
        weight=dequant(ctx.pack,dy.device,ctx.cache)
        dx=torch.matmul(dy.to(torch.bfloat16),weight).to(ctx.dtype)
        return dx,None,None

class StagedLinear(nn.Linear):
    """Subclass permits PEFT's standard attention Linear adapter dispatcher."""
    def __init__(self, pack, bias=None, cache=None):
        nn.Module.__init__(self)
        self.out_features,self.in_features=pack.shape
        # The empty GPU marker lets PEFT place trainable LoRA on the compute device.
        self.weight=nn.Parameter(torch.empty(0,device='cuda'),requires_grad=False)
        self.bias=nn.Parameter(bias.to('cuda',dtype=torch.float32),requires_grad=False) if bias is not None else None
        self.pack=pack;self.cache=cache or CACHE

    def forward(self, x):
        y=_FrozenNF4.apply(x,self.pack,self.cache)
        return y if self.bias is None else y+self.bias.to(y.dtype)

class _FrozenFloatHead(torch.autograd.Function):
    @staticmethod
    def forward(ctx,x,weight,tile):
        ctx.weight=weight;ctx.tile=tile;ctx.dtype=x.dtype
        # Reference prepare_model_for_kbit_training makes lm_head FP32.
        outputs=[]
        for lo in range(0,weight.shape[0],tile):
            w=weight[lo:lo+tile].to(x.device)
            outputs.append(F.linear(x.float(),w))
        return torch.cat(outputs,dim=-1)

    @staticmethod
    def backward(ctx,dy):
        dx=torch.zeros((*dy.shape[:-1],ctx.weight.shape[1]),device=dy.device,dtype=torch.float32)
        for lo in range(0,ctx.weight.shape[0],ctx.tile):
            w=ctx.weight[lo:lo+ctx.tile].to(dy.device)
            dx.add_(torch.matmul(dy[...,lo:lo+ctx.tile].float(),w))
        return dx.to(ctx.dtype),None,None

class StagedHead(nn.Linear):
    def __init__(self,weight,tile=4096):
        nn.Module.__init__(self);self.out_features,self.in_features=weight.shape
        self.weight=nn.Parameter(torch.empty(0,device='cuda'),requires_grad=False)
        self.bias=None;self.cpu_weight=weight.detach().to('cpu',dtype=torch.float32).contiguous();self.tile=tile
    def forward(self,x):return _FrozenFloatHead.apply(x,self.cpu_weight,self.tile)

class StagedEmbedding(nn.Embedding):
    def __init__(self,weight,padding_idx=None,scale=1.0):
        nn.Module.__init__(self);self.num_embeddings,self.embedding_dim=weight.shape
        self.padding_idx=padding_idx;self.max_norm=None;self.norm_type=2.;self.scale_grad_by_freq=False;self.sparse=False
        self.weight=nn.Parameter(torch.empty(0,device='cuda'),requires_grad=False)
        self.cpu_weight=weight.detach().to('cpu',dtype=torch.float32).contiguous();self.scale=scale
    def forward(self,ids):
        return (F.embedding(ids.cpu(),self.cpu_weight,self.padding_idx)*self.scale).to(ids.device)

class StagedExperts(nn.Module):
    """Identical unfused arithmetic to Gemma4TextExperts/Qwen3MoeExperts."""
    def __init__(self, gate_up, down, act_fn, cache=None):
        super().__init__();assert len(gate_up)==len(down)
        self.num_experts=len(gate_up);self.gate_up=gate_up;self.down=down;self.act_fn=act_fn;self.cache=cache or CACHE

    def forward(self,hidden_states,top_k_index,top_k_weights):
        final=torch.zeros_like(hidden_states)
        with torch.no_grad():
            mask=F.one_hot(top_k_index,num_classes=self.num_experts).permute(2,1,0)
            hits=(mask.sum(dim=(-1,-2))>0).nonzero().flatten().tolist()
        for idx in hits:
            top_pos,token_idx=torch.where(mask[idx])
            gate,up=_FrozenNF4.apply(hidden_states[token_idx],self.gate_up[idx],self.cache).chunk(2,dim=-1)
            cur=self.act_fn(gate)*up
            cur=_FrozenNF4.apply(cur,self.down[idx],self.cache)
            cur=cur*top_k_weights[token_idx,top_pos,None]
            final.index_add_(0,token_idx,cur.to(final.dtype))
        return final
