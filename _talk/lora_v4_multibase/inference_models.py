"""Pinned offloaded bases, their own final adapters, and frozen generation rules."""
import json
import re
import sys
import time
from pathlib import Path
from multibase_common import ROOT,TALK,RUN,SEED,read,sha,log,verify_data,stage_dir,write
from prepare_data import tokenizer

def frozen_modules():
    # Import only read-only CPU functions. No old Models class is instantiated.
    sys.path.insert(0,str(TALK/'lora_v4_planner_talk'))
    import evaluate,contracts
    evaluate.write=write
    return evaluate,contracts

def protected_ids(tok,prompt,recent,budget=928):
    enc=tok.encode(prompt,add_special_tokens=False)
    start=prompt.index(recent);end=start+len(recent)
    removable=[i for i,(a,b) in enumerate(enc.offsets) if a>=start and b<=end]
    cut=max(0,len(enc.ids)-budget)
    if cut>len(removable):raise ValueError('Protected Memory/Plan/state exceed fixed inference budget')
    gone=set(removable[:cut])
    return [x for i,x in enumerate(enc.ids) if i not in gone],cut

def special_ids(key):
    cfg=read(ROOT/'models'/key/'generation_config.json')
    raw=read(ROOT/'models'/key/'config.json')
    eos=cfg.get('eos_token_id',raw.get('eos_token_id'))
    assert eos is not None
    eos_list=eos if isinstance(eos,list) else [eos]
    pad=cfg.get('pad_token_id',raw.get('pad_token_id'))
    if pad is None:pad=eos_list[0]
    return eos,pad

class Models:
    def __init__(self,key,planner_only=False):
        import torch
        from peft import PeftModel
        from load_offloaded import load_base
        verify_data(key)
        self.key=key;self.torch=torch;self.tok=tokenizer(key)
        self.eos,self.pad=special_ids(key)
        self.eos_set=set(self.eos if isinstance(self.eos,list) else [self.eos])
        self.hashes={};base,targets,counts,_=load_base(key)
        for role,name in [('planner','planner')]+([] if planner_only else [('talk_v3','v3'),('talk_v4','v4')]):
            result=read(stage_dir(key,role)/'training_result.json');assert result['status']=='complete'
            adapter=Path(result['final_adapter']);digest=sha(adapter/'adapter_model.safetensors')
            assert digest==result['final_adapter_sha256']
            if name=='planner':self.model=PeftModel.from_pretrained(base,str(adapter),adapter_name=name,is_trainable=False)
            else:self.model.load_adapter(str(adapter),adapter_name=name,is_trainable=False)
            self.hashes[name]=digest
        self.model.eval();self.model.config.use_cache=True

    def generate(self,adapter,prompt,recent,seed,planner=False,reseed=True,raw_ids=None,
                 generation=None,budget=928,sentence_limit=2,control_ids=None):
        from transformers import StoppingCriteria,StoppingCriteriaList
        torch=self.torch;self.model.set_adapter(adapter);self.model.eval()
        ids,cut=protected_ids(self.tok,prompt,recent,budget) if raw_ids is None else (list(raw_ids[-budget:]),max(0,len(raw_ids)-budget))
        assert ids
        if reseed:torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
        n=len(ids);tok=self.tok
        class Stop(StoppingCriteria):
            def __call__(self,input_ids,scores,**kw):
                generated=input_ids[0,n:].tolist();text=tok.decode(generated,skip_special_tokens=True)
                if control_ids is not None:
                    from policy import rescue_plan
                    return rescue_plan(text,control_ids)[0] is not None
                if planner:
                    try:return isinstance(json.loads(text),dict)
                    except ValueError:return False
                return len(generated)>=8 and sentence_limit>0 and len(re.findall(r'[。！？!?]',text))>=sentence_limit
        cfg=generation or {'max_new_tokens':192 if planner else 96,'temperature':.8,'top_p':.95,'top_k':50,'repetition_penalty':1.05}
        options={'max_new_tokens':cfg['max_new_tokens'],'do_sample':not planner,
                 'eos_token_id':self.eos,'pad_token_id':self.pad,'use_cache':True}
        if not planner:options.update({k:cfg[k] for k in ['temperature','top_p','top_k','repetition_penalty']})
        if planner or sentence_limit:options['stopping_criteria']=StoppingCriteriaList([Stop()])
        t0=time.perf_counter()
        with torch.inference_mode():
            inp=torch.tensor([ids],device='cuda')
            output=self.model.generate(input_ids=inp,attention_mask=torch.ones_like(inp),**options)
        gen=output[0,n:].cpu().tolist();text=tok.decode(gen,skip_special_tokens=True)
        reason='eos' if gen and gen[-1] in self.eos_set else 'token_cap' if len(gen)>=cfg['max_new_tokens'] else 'structured_or_sentence_stop'
        if control_ids is not None:
            from policy import rescue_plan
            if rescue_plan(text,control_ids)[0] is not None:reason='first_schema_valid_object'
        rec={'text':text,'input_text':prompt,'decoded_input':tok.decode(ids,skip_special_tokens=False),
            'input_ids':ids,'output_ids':gen,'input_tokens':len(ids),'output_tokens':len(gen),'context_cut_tokens':cut,
            'seed':seed,'generation':cfg,'effective_generation':options.copy(),'sentence_limit':sentence_limit,
            'model_key':self.key,'adapter':adapter,'adapter_sha256':self.hashes[adapter],
            'eos_token_id':self.eos,'pad_token_id':self.pad,'seconds':round(time.perf_counter()-t0,3),'stop_reason':reason}
        rec['effective_generation'].pop('stopping_criteria',None)
        log('generated',model=self.key,adapter=adapter,tokens=len(gen),seconds=rec['seconds'])
        return rec

    def plan(self,inp,retry=0):
        _,c=frozen_modules()
        return self.generate('planner',c.planner_prompt(inp),inp['recent'],SEED+retry,planner=True)

    def plan_control(self,inp,retry=0):
        _,c=frozen_modules()
        return self.generate('planner',c.planner_prompt(inp),inp['recent'],SEED+retry,planner=True,
                             control_ids=[m['id'] for m in inp['memory_candidates']])
