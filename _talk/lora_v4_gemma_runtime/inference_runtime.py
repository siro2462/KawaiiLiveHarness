"""v5 Runtime generator with explicit Recent spans. Frozen models and sampling."""
import json
import time
from inference_v5 import V5Models
from schema_constraints import SchemaConstraint
from planner_policy import planner_prompt, parse_plan
from context_runtime import protected_ids


class RuntimeModels(V5Models):
    def plan(self, inp, retry=0):
        return self.planner(planner_prompt(inp),inp['recent'],[m['id'] for m in inp['memory_candidates']],retry)

    def planner(self, prompt, recent, candidate_ids, retry=0):
        recent=recent.rstrip('\n')
        start=prompt.index('【直近の確定発話】\n')+len('【直近の確定発話】\n')
        ids,history=protected_ids(self.tok,prompt,recent,[start,start+len(recent)])
        constraint=SchemaConstraint(self.schema_data,candidate_ids,len(ids))
        torch=self.torch
        from transformers import StoppingCriteria,StoppingCriteriaList
        tok=self.tok;n=len(ids)
        class Stop(StoppingCriteria):
            def __call__(self,input_ids,scores,**kwargs):
                try:return isinstance(json.loads(tok.decode(input_ids[0,n:].tolist(),skip_special_tokens=True)),dict)
                except ValueError:return False
        seed=20260925+retry
        torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
        self.model.set_adapter('planner');self.model.eval()
        options={'max_new_tokens':192,'do_sample':False,'eos_token_id':self.eos,'pad_token_id':self.pad,'use_cache':True,
                 'prefix_allowed_tokens_fn':constraint,'stopping_criteria':StoppingCriteriaList([Stop()])}
        started=time.perf_counter()
        with torch.inference_mode():
            tensor=torch.tensor([ids],device='cuda')
            output=self.model.generate(input_ids=tensor,attention_mask=torch.ones_like(tensor),**options)
        generated=output[0,n:].cpu().tolist();text=tok.decode(generated,skip_special_tokens=True)
        try:parse_plan(text,candidate_ids);error=None
        except (ValueError,TypeError,KeyError) as exc:error=str(exc)
        return {'text':text,'input_text':prompt,'decoded_input':tok.decode(ids,skip_special_tokens=False),
                'input_ids':ids,'output_ids':generated,'input_tokens':len(ids),'output_tokens':len(generated),
                **history,'seed':seed,'model_key':self.key,'adapter':'planner','adapter_sha256':self.hashes['planner'],
                'seconds':round(time.perf_counter()-started,3),'eos_token_id':self.eos,'pad_token_id':self.pad,
                'effective_generation':{k:v for k,v in options.items() if k not in {'prefix_allowed_tokens_fn','stopping_criteria'}},
                'constraint':{'enabled':True,'schema':constraint.schema,'steps':constraint.trace,
                              'backend':'lm-format-enforcer==0.11.3; v5 cached Unicode adapter'},
                'strict_schema_error':error,'stop_reason':'whole_schema_valid_object' if error is None else
                              'token_cap' if len(generated)>=192 else 'invalid_complete_object'}

    def talk(self, context, seed, retry_note=''):
        prompt=retry_note+context['prompt']
        span=[x+len(retry_note) for x in context['recent_span']]
        ids,history=protected_ids(self.tok,prompt,context['recent'],span)
        rec=super().generate('v4',prompt,context['recent'],seed,raw_ids=ids,budget=928)
        rec.update(history)
        rec['original_grounding']=context['grounding']
        return rec
