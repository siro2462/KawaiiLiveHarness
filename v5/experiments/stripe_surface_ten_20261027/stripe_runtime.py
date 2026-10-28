"""Same prior B renderer; only the formerly hard-coded theme is parameterized."""
import copy
from baseline_stripe_runtime import OPS,EPI,render as original_render,format_reason,text_units

def validate_sample(s):
 assert s['initial_history']==[] and len(s['nodes'])==29 and len(s['steps'])==32
 by={n['id']:n for n in s['nodes']};assert len(by)==29
 seen=set();visits=0
 for i,x in enumerate(s['steps'],1):
  assert x['index']==i and x['operation'] in OPS and x['epistemic'] in EPI and x['kind'] in 'FET'
  n=by[x['memory_id']];assert (x['content'],x['kind'],x['epistemic'])==(n['title'],n['kind'],n['epistemic'])
  if x['anchor_id']:assert x['anchor_id'] in seen
  if x['operation']=='REVISIT':assert x['memory_id'] in seen;visits+=1
  seen.add(x['memory_id'])
 assert len(seen)==29 and visits==3
 for n in s['nodes']:assert n['source_quotes'] and all(q in s['provenance']['source_text'] for q in n['source_quotes'])
 return True

def render_sample(s):
 validate_sample(s)
 prompt,payload=original_render(dict(kind='stripe',steps=copy.deepcopy(s['steps'])),[],None,s['steps'])
 old='【現在のテーマ】\nガラポンでA賞が出なかった体験\n'
 assert prompt.count(old)==1 and '\n' not in s['title']
 prompt=prompt.replace(old,'【現在のテーマ】\n'+s['title']+'\n',1)
 return prompt,payload
