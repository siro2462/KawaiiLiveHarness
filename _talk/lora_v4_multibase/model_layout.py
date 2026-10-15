"""Architecture-specific graph construction and deterministic weight mapping."""
import os
from collections import defaultdict
import torch
from torch import nn
from probe import ROOT
os.environ['HF_MODULES_CACHE']=str(ROOT/'module_cache')

def construct(key, tiny=False):
    os.environ['HF_MODULES_CACHE']=str(ROOT/'module_cache')
    from transformers import AutoConfig,AutoModelForCausalLM,Gemma4ForCausalLM
    from transformers.initialization import no_init_weights
    from accelerate import init_empty_weights
    cfg=AutoConfig.from_pretrained(ROOT/'models'/key,local_files_only=True,trust_remote_code=key.startswith('xing'))
    if key.startswith('gemma'):
        cfg=cfg.text_config
        cls=Gemma4ForCausalLM
    else:cls=None
    if tiny:
        cfg.hidden_size=128;cfg.num_hidden_layers=2;cfg.vocab_size=257
        cfg.num_attention_heads=4;cfg.num_key_value_heads=2
        cfg.intermediate_size=256;cfg.max_position_embeddings=2048
        if key.startswith('gemma'):
            cfg.head_dim=32;cfg.global_head_dim=32;cfg.num_global_key_value_heads=2
            cfg.num_experts=4;cfg.top_k_experts=2;cfg.moe_intermediate_size=64
            cfg.layer_types=['sliding_attention','full_attention'];cfg.num_kv_shared_layers=0
            cfg.hidden_size_per_layer_input=0;cfg.sliding_window=128
        elif key.startswith('llmjp'):
            cfg.head_dim=32;cfg.num_experts=4;cfg.num_experts_per_tok=2;cfg.moe_intermediate_size=64
        else:
            cfg.num_key_value_heads=4
            cfg.n_routed_experts=4;cfg.num_local_experts=4;cfg.num_experts_per_tok=2
            cfg.moe_intermediate_size=64;cfg.first_k_dense_replace=1
            cfg.q_lora_rank=32;cfg.kv_lora_rank=32;cfg.qk_nope_head_dim=16;cfg.qk_rope_head_dim=16;cfg.v_head_dim=16
            cfg.qk_head_dim=32;cfg.head_dim=16
        mini=cfg.to_dict();mini.pop('per_layer_config',None)
        cfg=type(cfg)(**mini)
    cfg._attn_implementation='sdpa'
    if not key.startswith('xing'):cfg._experts_implementation='eager'
    # Buffers (RoPE frequencies, scales) must be real CPU tensors, not meta.
    with no_init_weights(),init_empty_weights(include_buffers=False):
        model=cls._from_config(cfg,dtype=torch.bfloat16,attn_implementation='sdpa',experts_implementation='eager') if cls else AutoModelForCausalLM.from_config(cfg,trust_remote_code=key.startswith('xing'),dtype=torch.bfloat16,attn_implementation='sdpa')
        model.tie_weights()
    model.config.use_cache=False
    return model

def source_key(key,name):
    return name.replace('model.','model.language_model.',1) if key.startswith('gemma') and name.startswith('model.') else name

def group_for(name):
    parts=name.split('.')
    if len(parts)>2 and parts[:2]==['model','layers']:return 'layer_'+parts[2].zfill(3)
    return 'root'

def layout(model,key):
    records=[];owned=set()
    for name,module in model.named_modules():
        if module.__class__.__name__ in {'Gemma4TextExperts','Qwen3MoeExperts'}:
            names=[name+'.gate_up_proj',name+'.down_proj']
            records.append({'name':name,'type':'experts','keys':names,
                'shapes':[list(getattr(module,n.rsplit('.',1)[-1]).shape) for n in names]})
            owned.update(names)
        elif isinstance(module,nn.Embedding):
            names=[name+'.weight'];owned.update(names)
            records.append({'name':name,'type':'embedding','keys':names,'shapes':[list(module.weight.shape)],
                'padding_idx':module.padding_idx,'scale':float(module.embed_scale.float()) if hasattr(module,'embed_scale') else 1.0})
        elif isinstance(module,nn.Linear):
            names=[name+'.weight']+([name+'.bias'] if module.bias is not None else [])
            owned.update(names)
            typ='head' if name=='lm_head' else 'linear'
            if typ=='head' and model.config.tie_word_embeddings:typ='tied_head'
            records.append({'name':name,'type':typ,'keys':names,
                'shapes':[list(module.weight.shape)]+([list(module.bias.shape)] if module.bias is not None else [])})
    for name,param in model.named_parameters(remove_duplicate=False):
        if name not in owned:
            records.append({'name':name,'type':'parameter','keys':[name],'shapes':[list(param.shape)]})
            owned.add(name)
    for name,buffer in model.named_buffers():
        # Persistent checkpoint buffer (Xing router bias) is loaded if present.
        owner=model.get_submodule(name.rsplit('.',1)[0]);leaf=name.rsplit('.',1)[-1]
        if leaf not in owner._non_persistent_buffers_set:
            records.append({'name':name,'type':'buffer','keys':[name],'shapes':[list(buffer.shape)]})
    for rec in records:
        rec['source_keys']=[source_key(key,n) for n in rec['keys']]
        if key.startswith('llmjp') and rec['type']=='experts':
            # This official checkpoint stores separate experts; Transformers
            # normally fuses them on load. Preserve gate/up concatenation order.
            rec['source_experts']=[{s:rec['name']+'.'+str(i)+'.'+s+'_proj.weight'
                                    for s in ['gate','up','down']} for i in range(rec['shapes'][0][0])]
            rec['source_keys']=[n for expert in rec['source_experts'] for n in expert.values()]
        rec['group']=group_for(rec['name'])
    return records

def attention_targets(model,key):
    leaves={'q_a_proj','q_b_proj','kv_a_proj_with_mqa','kv_b_proj','o_proj'} if key.startswith('xing') else {'q_proj','k_proj','v_proj','o_proj'}
    names=[n for n,_ in model.named_modules() if '.self_attn.' in n and n.rsplit('.',1)[-1] in leaves]
    assert names and all(n.startswith('model.layers.') for n in names)
    counts={s:sum(n.endswith('.'+s) for n in names) for s in leaves}
    layers=model.config.num_hidden_layers
    assert counts.get('o_proj')==layers
    if key.startswith('xing'):assert all(counts[s]==layers for s in leaves)
    else:assert counts['q_proj']==layers and counts['k_proj']==layers and counts['v_proj']>0
    return names,counts

def assign_small(model,name,tensor,buffer=False):
    parent,leaf=name.rsplit('.',1);owner=model.get_submodule(parent)
    if buffer:owner._buffers[leaf]=tensor.to('cuda')
    else:owner._parameters[leaf]=nn.Parameter(tensor.to('cuda',dtype=torch.float32),requires_grad=False)

def install_records(model,records,payload):
    from offload_backend import QuantPack,StagedLinear,StagedEmbedding,StagedHead,StagedExperts
    for rec in records:
        name=rec['name'];typ=rec['type'];data=payload[name]
        if typ in {'parameter','buffer'}:
            assign_small(model,name,data['value'],buffer=typ=='buffer');continue
        old=model.get_submodule(name)
        if typ=='linear':new=StagedLinear(QuantPack.restore(data['weight']),data.get('bias'))
        elif typ=='embedding':new=StagedEmbedding(data['weight'],rec['padding_idx'],rec['scale'])
        elif typ=='head':new=StagedHead(data['weight'])
        elif typ=='tied_head':new=StagedHead(model.get_input_embeddings().cpu_weight)
        elif typ=='experts':
            new=StagedExperts([QuantPack.restore(v) for v in data['gate_up']],
                              [QuantPack.restore(v) for v in data['down']],old.act_fn)
        else:raise ValueError(typ)
        parent,leaf=name.rsplit('.',1) if '.' in name else ('',name)
        setattr(model.get_submodule(parent) if parent else model,leaf,new)

def move_buffers(model):
    for _,module in model.named_modules():
        for name,buffer in list(module._buffers.items()):
            if buffer is not None:
                if buffer.is_meta:raise RuntimeError('Unmaterialized buffer '+name)
                module._buffers[name]=buffer.to('cuda')
    assert not any(p.is_meta for p in model.parameters()),'Unmaterialized parameter remains'
    model.is_loaded_in_4bit=True
    model.quantization_method='cpu_staged_nf4'
