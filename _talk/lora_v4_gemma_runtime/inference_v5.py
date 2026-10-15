"""v5 Planner override; frozen old model loader and Talk generation unchanged."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / 'lora_v4_multibase'
sys.path.insert(0, str(OLD))
from inference_models import Models, protected_ids
sys.path.insert(0, str(ROOT))
from planner_policy import parse_plan
from schema_constraints import SchemaConstraint, tokenizer_data


class V5Models(Models):
    def __init__(self, planner_only=False):
        super().__init__('gemma4_26b_a4b', planner_only=planner_only)
        self.schema_data = tokenizer_data(self.tok, OLD / 'models' / self.key / 'tokenizer.json', self.eos)

    def constrained_plan(self, prompt, recent, candidate_ids, seed, budget=928, max_new_tokens=192):
        from transformers import StoppingCriteria, StoppingCriteriaList
        torch = self.torch
        self.model.set_adapter('planner')
        self.model.eval()
        ids, cut = protected_ids(self.tok, prompt, recent, budget)
        n = len(ids)
        constraint = SchemaConstraint(self.schema_data, candidate_ids, n)
        tokenizer = self.tok

        class WholeObjectStop(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                text = tokenizer.decode(input_ids[0, n:].tolist(), skip_special_tokens=True)
                try:
                    return isinstance(json.loads(text), dict)
                except ValueError:
                    return False

        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        options = {'max_new_tokens': max_new_tokens, 'do_sample': False,
                   'eos_token_id': self.eos, 'pad_token_id': self.pad, 'use_cache': True,
                   'prefix_allowed_tokens_fn': constraint,
                   'stopping_criteria': StoppingCriteriaList([WholeObjectStop()])}
        started = time.perf_counter()
        with torch.inference_mode():
            inp = torch.tensor([ids], device='cuda')
            output = self.model.generate(input_ids=inp, attention_mask=torch.ones_like(inp), **options)
        generated = output[0, n:].cpu().tolist()
        text = tokenizer.decode(generated, skip_special_tokens=True)
        try:
            parse_plan(text, candidate_ids)
            valid = True
            error = None
        except (ValueError, TypeError, KeyError) as exc:
            valid = False
            error = str(exc)
        return {'text': text, 'input_text': prompt, 'decoded_input': tokenizer.decode(ids, skip_special_tokens=False),
                'input_ids': ids, 'output_ids': generated, 'input_tokens': n, 'output_tokens': len(generated),
                'context_cut_tokens': cut, 'seed': seed, 'model_key': self.key,
                'adapter': 'planner', 'adapter_sha256': self.hashes['planner'],
                'eos_token_id': self.eos, 'pad_token_id': self.pad,
                'seconds': round(time.perf_counter() - started, 3),
                'effective_generation': {k: v for k, v in options.items() if k not in {'prefix_allowed_tokens_fn', 'stopping_criteria'}},
                'constraint': {'enabled': True, 'backend': 'lm-format-enforcer==0.11.3',
                               'schema': constraint.schema, 'steps': constraint.trace,
                               'tokenizer': self.schema_data.v5_metadata,
                               'adoption_cross_field_check': 'strict parser; not boolean const masking'},
                'strict_schema_valid': valid, 'strict_schema_error': error,
                'stop_reason': 'whole_schema_valid_object' if valid else
                               'token_cap' if len(generated) >= max_new_tokens else 'invalid_complete_object'}
