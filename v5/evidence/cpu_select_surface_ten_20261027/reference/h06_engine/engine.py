#!/usr/bin/env python3
"""① fragment recall + ② discourse-operation selector. NO ML, NLP LLM or surface generation.
No access to human_reference.json. A deterministic seeded symbolic policy.
"""
import argparse,collections,json,random,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MEM=json.loads((ROOT/'memory.json').read_text(encoding='utf8'))
N={v['id']:v for v in MEM['nodes']}
OUT=collections.defaultdict(list);INC=collections.defaultdict(list)
for e in MEM['edges']:
 OUT[e['src']].append(e);INC[e['dst']].append(e)
REL_ACTION={'reaction':'REACT','appraisal':'APPRAISE','reappraise':'REAPPRAISE','reframe':'REAPPRAISE',
 'suspicion':'SPECULATE','uncertainty':'REPAIR','resolve':'REPAIR','contrast':'COMPARE','compare':'COMPARE',
 'comparison':'COMPARE','cost_stakes':'REACT','regret':'REACT','generalize':'GENERALIZE',
 'generalization':'GENERALIZE','correction':'REPAIR','reenact':'REENACT',
 'luck_link':'ASSOCIATE','success_link':'ASSOCIATE','prize_link':'ASSOCIATE',
 'outcome':'REPORT','calculate':'REPORT','detail':'EVIDENCE','elaboration':'EVIDENCE','evidence':'EVIDENCE',
 'expectation':'SPECULATE','self_evaluate':'APPRAISE','evaluate':'APPRAISE',
 'verify':'REPAIR','action':'REPORT','thought':'EXPLORE','initial_belief':'SPECULATE',
 'explanation':'EXPLORE','sigh':'REACT','emphasis':'REVISIT'}
def color(n):return n['kind']
def relation(a,b):
 if not a:return None
 for e in OUT[a]:
  if e['dst']==b:return e['rel']
 return None
class Engine:
 def __init__(self,seed=17,mode='state',allow_cross=False):
  self.rng=random.Random(seed);self.mode=mode;self.allow_cross=allow_cross
  self.focus=None;self.topic=None;self.stack=[];self.used=collections.Counter();self.last=[];self.trace=[];self.shifted_pairs=set()
  self.open_needs=set();self.active_appraisals=set();self.moves=collections.Counter()
 def _score(self,n,rel,linked,stage):
  if n['id'] in self.used:return -999
  if any(self.used[p]==0 for p in n.get('requires',[])):return -999
  score=.60*n['importance']
  same=n['topic']==self.topic
  score += 1.35 if same else -4.1
  if linked: score+=3.30
  if rel in ('reaction','appraisal','reappraise','reframe','suspicion','correction','regret','contrast','comparison','cost_stakes','outcome'):
   score+=1.05
  if self.focus:
   shared=set(n['tags'])&set(N[self.focus]['tags'])
   score+=min(len(shared),2)*.52
  if self.mode=='state' and self.last:
   recent=[x['color'] for x in self.last[-3:]]
   if n['kind']==recent[-1]:score-=.95
   if len(recent)>=2 and n['kind']==recent[-1]==recent[-2]:score-=.80
   if n['kind']!=recent[-1] and linked:score+=.48
   if 'uncertain' in n['epistemic'] or 'suspicion' in n['epistemic']:
    score+=.6 if rel in ('suspicion','uncertainty','correction') else -.45
   if n['kind']=='T' and self.active_appraisals and rel in ('compare','comparison','reappraise','contrast'):
    score+=.65
  if not same:
   if not self.allow_cross:return -999
   # May only shift when an explicit edge is found and current episode has some substance.
   if not linked or sum(v for k,v in self.used.items() if N[k]['topic']==self.topic)<6:return -999
   if (self.topic,n['topic']) in self.shifted_pairs:return -999
   score+=1.5
  # stochastic variation, not fitted to human colors
  score+=self.rng.uniform(-.36,.36)
  return round(score,4)
 def _recall(self):
  """Recall only neighbor + same topic. Cross only typed explicit edges from focus or recent focus."""
  candidates={n['id'] for n in MEM['nodes'] if n['topic']==self.topic and not self.used[n['id']]}
  if self.focus:
   for anchor in [self.focus]+[x['node_id'] for x in self.last[-3:]]:
    for e in OUT[anchor]:
     if not self.used[e['dst']]:candidates.add(e['dst'])
    for e in INC[anchor]:
     if not self.used[e['src']]:candidates.add(e['src'])
  return [N[i] for i in sorted(candidates)]
 def _candidate(self,n):
  links=[]
  for anchor in [self.focus]+[x['node_id'] for x in self.last[-3:]]:
   if anchor is None:continue
   for e in OUT[anchor]:
    if e['dst']==n['id']:links.append((2,e['rel'],anchor))
   for e in INC[anchor]:
    if e['src']==n['id']:links.append((1,'related_'+e['rel'],anchor))
  links.sort(reverse=True)
  direct=[x for x in links if x[0]==2]
  rel=direct[0][1] if direct else (links[0][1] if links else None)
  sc=self._score(n,rel,bool(links),0)
  op=REL_ACTION.get(rel)
  if op is None:
   op={'F':'REPORT','E':'REACT','T':'EXPLORE'}[n['kind']]
  if op=='REPORT' and n['kind']!='F':op='EXPLORE' if n['kind']=='T' else 'REACT'
  if op=='REVISIT' and self.used[n['id']]==0:op='REACT' if n['kind']=='E' else 'APPRAISE' if n['kind']=='T' else 'REPORT'
  if n['topic']!=self.topic:op='ASSOCIATE_SHIFT'
  return {'node_id':n['id'],'operation':op,'color':n['kind'],'score':sc,'relation':rel,'source_anchor':(links[0][2] if links else None),'new_evidence':True}
 def _revisit_candidates(self):
  # A previously told fact can be revisited with NEW purpose, only after linked downstream activity.
  if self.mode!='state' or len(self.last)<4:return []
  recent_ids={x['node_id'] for x in self.last[-3:]}
  result=[]
  for n in MEM['nodes']:
   if n['topic']!=self.topic or n['kind']!='F' or not self.used[n['id']] or n['id'] in recent_ids:continue
   if self.used[n['id']]>=2:continue
   evidence=[]
   for x in self.last[-2:]:
    for e in OUT[n['id']]:
     if e['dst']==x['node_id'] and e['rel'] in ('contrast','compare','comparison','reappraise','appraisal','cost_stakes','outcome'):
      evidence.append((e['rel'],x['node_id']))
   if not evidence:continue
   key=(n['id'],evidence[0][1])
   if key in self.moves:continue
   score=2.5+.3*n['importance']
   if self.last[-1]['color']!='F':score+=.7
   score+=self.rng.uniform(-.25,.25)
   result.append(dict(node_id=n['id'],operation='REVISIT',color='F',score=round(score,4),relation=evidence[0][0],source_anchor=evidence[0][1],new_evidence=False,revisit_key=key))
  return result
 def start(self,topic):
  self.topic=topic;self.focus=None;self.last=[];self.used.clear();self.stack=[];self.trace=[];self.shifted_pairs.clear()
  # Introductions are MEMORY metadata, not human line positions; inference uses zero ground-truth labels.
  entry=[n for n in MEM['nodes'] if n['topic']==topic and 'entry' in n['tags']]
  if not entry:raise ValueError('entry missing')
  n=max(entry,key=lambda x:x['importance']);op='REPORT' if n['kind']=='F' else 'REACT'
  self._commit(dict(node_id=n['id'],operation=op,color=n['kind'],score=999.,relation='episode_entry',source_anchor=None,new_evidence=True))
 def _commit(self,w):
  n=N[w['node_id']];prev=self.focus
  if n['topic']!=self.topic:
   if self.topic is not None:
    self.stack.append(dict(topic=self.topic,focus=prev,at_step=len(self.trace)))
    self.shifted_pairs.add((self.topic,n['topic']))
    w['topic_shift_from']=self.topic
   self.topic=n['topic']
  self.focus=n['id'];self.used[n['id']]+=1
  if n['kind']=='E':self.active_appraisals.update(n['tags'])
  if w['operation'] in ('SPECULATE','EXPLORE'):
   self.open_needs.update(n['tags'])
  if 'revisit_key' in w:self.moves[tuple(w['revisit_key'])]+=1
  w.update(index=len(self.trace)+1,topic=n['topic'],title=n['title'],epistemic=n['epistemic'],source_lines=n['source_lines'],source_quotes=n['source_quotes'],memory_type=n['kind'],previous_node=prev)
  self.trace.append(w);self.last.append(w)
 def step(self):
  # Return from a temporary digression when the original thread still has unseen evidence.
  # This is a bounded stack policy; not a semantic interpretation of generated language.
  if self.stack:
   frame=self.stack[-1]
   remain=[n for n in MEM['nodes'] if n['topic']==frame['topic'] and not self.used[n['id']]]
   if remain and len(self.trace)-frame['at_step']>=8:
    self.stack.pop()
    self.topic=frame['topic'];self.focus=frame['focus']
    cand=[self._candidate(n) for n in remain]
    cand=[c for c in cand if c['score']>-900]
    if cand:
     best=max(cand,key=lambda x:x['score']);best['operation']='RESUME';best['return_from_digression']=True
     self._commit(best);return True
  cand=[self._candidate(n) for n in self._recall()]
  cand.extend(self._revisit_candidates())
  cand=[c for c in cand if c['score']>-900]
  if not cand:return False
  top=max(cand,key=lambda x:x['score'])
  # If remaining candidates are unlinked scraps, finish rather than endless topic hopping.
  if top['score']<1.4:return False
  self._commit(top)
  return True
 def run(self,topic,max_steps=45):
  self.start(topic)
  while len(self.trace)<max_steps and self.step():pass
  return list(self.trace)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=17);p.add_argument('--mode',choices=['state','graph'],default='state');p.add_argument('--cross',action='store_true');a=p.parse_args()
 result={t:Engine(seed=a.seed,mode=a.mode,allow_cross=a.cross).run(t) for t in ['H04','H06','H07']}
 print(json.dumps(result,ensure_ascii=False,indent=2))
