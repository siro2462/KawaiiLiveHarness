"""Offline presentation tracking. No semantic entailment or factual-memory writes."""
import copy,json,re,sqlite3,unicodedata
from common import digest

def facts_for(m):return [dict(id=f'{m["id"]}-{i+1}',claim=s+'。',kind='intent' if any(x in s for x in ('ことにした','つもり','と思った','しようと思った')) else 'event') for i,s in enumerate(m['beats'])]
def grams(s):
 s=''.join(c for c in unicodedata.normalize('NFKC',s) if c.isalnum());return {s[i:i+2] for i in range(max(0,len(s)-1))}
from flow_apply import plan_order

class Progress:
 def __init__(self,memory,plan):
  self.memory=copy.deepcopy(memory);self.source_sha=digest(json.dumps(memory,ensure_ascii=False,sort_keys=True));self.ids=[f['id'] for f in facts_for(memory)]
  self.facts={i:dict(presentations=0,delivery='not_presented',semantic_status='unverified',exact_source_quote=None) for i in self.ids}
  self.order,self.mapping=plan_order(plan,facts_for(memory));self.last_seq=0
 def pending(self):return [i for i in self.order if not self.facts[i]['presentations']]
 def focus(self,arm):
  selected=self.pending()[:(6 if arm=='A' else 2)];return [i for i in self.ids if i in selected]
 def presented(self,ids):
  if not ids or len(set(ids))!=len(ids) or any(i not in self.facts or self.facts[i]['presentations'] for i in ids):raise ValueError('Unknown/duplicate target presentation')
  for i in ids:self.facts[i].update(presentations=1,delivery='attempted_not_confirmed')
 def finish(self,ids,body,event_seq):
  if event_seq is not None and (type(event_seq)is not int or event_seq<=self.last_seq):raise ValueError('Delivery receipt out of order')
  claims={f['id']:f['claim'] for f in facts_for(self.memory)}
  for i in ids:
   if self.facts[i]['presentations']!=1 or self.facts[i]['delivery']!='attempted_not_confirmed':raise ValueError('Invalid delivery state')
   self.facts[i].update(delivery='text_delivered_unverified' if event_seq is not None else 'format_held_not_reoffered',exact_source_quote=claims[i] if event_seq is not None and claims[i] in body else None)
  if event_seq is not None:self.last_seq=event_seq
 def reorder(self,plan):
  self.order,self.mapping=plan_order(plan,facts_for(self.memory))
 def snapshot(self):return copy.deepcopy(dict(memory_id=self.memory['id'],source_sha256=self.source_sha,selection_order=self.order,mapping=self.mapping,facts=self.facts,last_delivery_seq=self.last_seq,pending_target_ids=self.pending(),progress_definition='presentation/delivery != verified semantic coverage'))
class EventStore:
 def __init__(self,path):
  self.db=sqlite3.connect(str(path));self.db.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL)')
 def append(self,kind,payload):
  q=self.db.execute('INSERT INTO events(kind,payload) VALUES(?,?)',(kind,json.dumps(payload,ensure_ascii=False)));self.db.commit();return q.lastrowid
 def recent(self):
  rows=[dict(json.loads(p),seq=n) for p,n in self.db.execute("SELECT payload,seq FROM events WHERE kind='text_delivery_confirmed' ORDER BY seq")];keep=[]
  for row in reversed(rows):
   if len(keep)==2 or sum(len(x['text']) for x in keep)+len(row['text'])>800:break
   keep.insert(0,row)
  return keep
 def close(self):self.db.close()
def format_failure(body,stopped):
 if not isinstance(body,str) or not body.strip():return 'empty'
 if not stopped:return 'incomplete_stop_or_token_cap'
 if len(body)>1800:return 'excessive_length'
 if re.search(r'<[^>]+>|^\s*[\[{]|【|^\s*#{1,6}\s',body):return 'markup_or_explanation'
 if re.search(r'(.{3,20})\1{3,}',body):return 'pathological_intra_utterance_repetition'
 return None
def repetition_observation(body,history):return dict(exact_previous=any(body==h['text'] for h in history),repeated_opening=any(body[:8]==h['text'][:8] for h in history if len(body)>=8),adoption_gate=False)
def surface_case(memory,ids,history,shared,summary,pair_id):
 facts=[f for f in facts_for(memory) if f['id'] in ids];old=history[-1]['memory_id'] if history else None
 op='start' if not history else 'continue' if old==memory['id'] else 'related_shift' if shared else 'topic_shift'
 flow=[dict(fact_ids=[f['id']],relation='sequence',label='気づき・発見' if any(w in f['claim'] for w in ('気づ','見つ','入っていた')) else '予定・判断' if f['kind']=='intent' else '出来事の進展') for f in facts]
 return dict(schema='surface-contract-1',pair_id=pair_id,facts=facts,history=copy.deepcopy(history),operation=op,relation=dict(type='sequence' if op=='continue' else 'association' if op=='related_shift' else 'none',summary='同じ出来事の未提示部分に進む。直前の本文は発話済みだが未検証。新事実の根拠にしない。' if op=='continue' else summary),flow=flow)
