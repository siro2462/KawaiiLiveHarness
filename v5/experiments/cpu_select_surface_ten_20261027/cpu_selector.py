"""Unchanged H06 Engine + deterministic metadata adapter. Never read previous steps."""
import collections, copy, hashlib, importlib.util, json, math, re, unicodedata
from common import OUT, read
STOP=set('した して った って てい いる いた ない なか こと もの ある する から ため ので よう なる 思っ とい いう 本人 自分 その この には では だっ れた れて'.split())
def grams(text):
 text=unicodedata.normalize('NFKC',text).lower()
 spans=re.findall(r'[\w一-龥ぁ-んァ-ヶー]+',text)
 return set(g for word in spans for i in range(len(word)-1) if (g:=word[i:i+2]) not in STOP)
def sim(a,b):return len(a&b)/math.sqrt(len(a)*len(b)) if a and b else 0.0
def load_engine():
 p=OUT/'reference/h06_engine/engine.py';spec=importlib.util.spec_from_file_location('fixed_h06_engine',p);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def graph_from_memory(s):
 # Access only fixed Memory fields. No old steps, source line ordering, quotes, or output.
 title=s['title'];sid=s['id'];items=sorted(s['nodes'],key=lambda n:n['id'])
 tokens={n['id']:grams(n['title']) for n in items};topicgrams=grams(title)
 mapping={n['id']:'N'+hashlib.sha256((n['title']+'\0'+n['kind']+'\0'+n['epistemic']).encode()).hexdigest() for n in items}
 assert len(set(mapping.values()))==len(items)
 nodes=[]
 for n in items:
  nodes.append(dict(id=mapping[n['id']],topic=sid,kind=n['kind'],epistemic=n['epistemic'],title=n['title'],
   importance=round(1+2*sim(tokens[n['id']],topicgrams),6),tags=sorted(tokens[n['id']]),requires=[],source_lines=[],source_quotes=[]))
 nodes.sort(key=lambda n:n['id'])
 max(nodes,key=lambda n:n['importance'])['tags'].append('entry')
 def relation(n):
  if n['kind']=='E':return 'reaction'
  if n['kind']=='F':return 'detail'
  return {'unverified_suspicion':'suspicion','uncertain_memory':'uncertainty','counterfactual':'comparison','speaker_evaluation':'appraisal','speaker_expectation':'expectation'}.get(n['epistemic'],'thought')
 edges=[];candidates=[]
 for a in items:
  ranked=sorted([(sim(tokens[a['id']],tokens[b['id']]),mapping[b['id']],b) for b in items if b['id']!=a['id']],key=lambda z:(-z[0],z[1]))
  for score,_,b in ranked[:3]:
   if score<.18:continue
   rel=relation(b);edges.append(dict(src=mapping[a['id']],dst=mapping[b['id']],rel=rel))
   candidates.append(dict(src=a['id'],dst=b['id'],relation=rel,cosine=score,shared_bigrams=sorted(tokens[a['id']]&tokens[b['id']]),semantic_verification=False))
 return dict(nodes=nodes,edges=edges),mapping,dict(rule='bigrams cosine>=0.18; at most3 outgoing per node; importance=1+2*theme cosine; content-hash internal IDs; no requires inferred',edges=candidates)
def bind(mod,graph):
 mod.MEM=graph;mod.N={n['id']:n for n in graph['nodes']};mod.OUT=collections.defaultdict(list);mod.INC=collections.defaultdict(list)
 for e in graph['edges']:mod.OUT[e['src']].append(e);mod.INC[e['dst']].append(e)
def select(s,seed=17,observe=True):
 mod=load_engine();graph,mapping,metadata=graph_from_memory(s);bind(mod,graph);candidates=[]
 class ObservedEngine(mod.Engine):
  def _candidate(self,n):
   z=super()._candidate(n);candidates.append(dict(decision_index=len(self.trace)+1,**copy.deepcopy(z)));return z
  def _revisit_candidates(self):
   zs=super()._revisit_candidates();candidates.extend(dict(decision_index=len(self.trace)+1,**copy.deepcopy(z)) for z in zs);return zs
 cls=ObservedEngine if observe else mod.Engine
 trace=cls(seed=seed,mode='state',allow_cross=False).run(s['id'])
 reverse={v:k for k,v in mapping.items()};by={n['id']:n for n in s['nodes']};steps=[]
 for t in trace:
  mid=reverse[t['node_id']];n=by[mid];anchor=t['source_anchor']
  steps.append(dict(index=t['index'],memory_id=mid,operation=t['operation'],kind=n['kind'],content=n['title'],epistemic=n['epistemic'],relation=t['relation'],anchor_id=reverse[anchor] if anchor else None))
 return json.loads(json.dumps(dict(steps=steps,graph=graph,id_mapping=mapping,derived_metadata=metadata,trace=trace,candidates=candidates,engine_seed=seed,engine_mode='state',allow_cross=False,max_steps=45,manual_sequence=False),ensure_ascii=False))
def all_selected():
 return [dict(copy.deepcopy(s),steps=select(s)['steps'],operation_plan_author='unchanged H06 CPU Engine on automatically derived metadata; no manual operations') for s in read(OUT/'memory_fixed.json')]
