"""Bounded cumulative A-G mechanical probes. No LLM judge, Memory writes or trained Planner."""
import copy,re,unicodedata
from contract_runtime import validate

def literal_observations(body):
 s=unicodedata.normalize('NFKC',body).replace(',','');found={}
 rules={
 'result': bool(re.search(r'(9000|九千|9千)円',s) and 'A賞' in s and any(x in s for x in ['出な','当たら','当たん'])),
 'anger': 'B賞' in s and any(x in s for x in ['怒','悔','許せ','納得','ひど','ひどい','どうにか']),
 'mismatch': '景品' in s and any(x in s for x in ['当たら','当たん','出ない','出な']) and any(x in s for x in ['のに','でも','だけど']),
 'purchase': bool(re.search(r'(9000|九千|9千)円',s) and re.search(r'買(?:え|っ|う)',s) and any(x in s for x in ['なら','たら','れば','じゃない','では','かも','かな']))}
 for k,yes in rules.items():
  if yes:found[k]={'text':body,'rule':k+' lexical conjunction, not verified semantics','semantic_status':'unverified'}
 return found

def validate_catalog(case,catalog):
 validate(case);facts={f['id']:f['claim'] for f in case['facts']};seen=set();ev=set()
 assert len(catalog['views'])==4
 for v in catalog['views']:
  assert set(v)=={'id','fact_id','evidence_id','basis','label','instruction','rank','prerequisites'}
  assert v['id'] not in seen and v['evidence_id'] not in ev and v['fact_id'] in facts and v['basis'] in facts[v['fact_id']]
  assert v['basis'] and len(v['instruction'])<=160 and all(p in facts and p!=v['fact_id'] for p in v['prerequisites'])
  seen.add(v['id']);ev.add(v['evidence_id'])
 for e in catalog['links']:
  assert e['from'] in seen and e['to'] in seen and e['from']!=e['to'] and 0<=e['strength']<=2 and all(x in ev for x in e['basis_ids'])
 return True

class Control:
 def __init__(self,initial,catalog,arm):
  validate_catalog(initial,catalog)
  assert arm['id'] in 'ABCDEFG' and arm['features']==list('ABCDEFG'[:ord(arm['id'])-64]) and arm['max_calls']==4
  self.initial=copy.deepcopy(initial);self.catalog=copy.deepcopy(catalog);self.arm=copy.deepcopy(arm)
  self.history=copy.deepcopy(initial['history']);self.attempts=[];self.delivered_facts=[];self.observed={};self.appraisal=None;self.active=None;self.stop_reason=None
 def has(self,c):return c in self.arm['features']
 def recent(self):
  keep=[]
  for h in reversed(self.history):
   if len(keep)==2 or sum(len(x['text']) for x in keep)+len(h['text'])>800:break
   keep.insert(0,copy.deepcopy(h))
  return keep
 def snapshot(self):
  return copy.deepcopy(dict(arm=self.arm,attempts=self.attempts,delivered_fact_ids=self.delivered_facts,observed_viewpoints=self.observed,current_appraisal=self.appraisal,active=self.active,stop_reason=self.stop_reason,recent=self.recent(),semantic_status='unverified',memory_writes=0,verified_fact_ids=[]))
 def candidates(self):
  tried={a['view_id'] for a in self.attempts};result=[]
  for v0 in self.catalog['views']:
   v=copy.deepcopy(v0)
   if not self.has('B'):
    if v['id']=='purchase':continue
    v['instruction']='今回のまとまりにある内容を伝える。';v['basis']=next(f['claim'] for f in self.initial['facts'] if f['id']==v['fact_id']);v['label']='まとまり '+v['fact_id']
   reasons=[]
   if v['id'] in tried:reasons.append('already_attempted_no_retry')
   if not self.has('E') and v['fact_id'] in self.delivered_facts:reasons.append('fact_once_gate')
   if any(x not in self.delivered_facts for x in v['prerequisites']):reasons.append('prerequisite_not_delivered')
   if self.has('G') and v['id'] in self.observed:reasons.append('literal_view_already_observed_unverified')
   score=10-v['rank'];parts={'source_order':score,'appraisal':0,'link':0,'novelty':0}
   if self.has('C') and self.appraisal:
    if self.appraisal['tag']=='anger' and v['id']=='mismatch':parts['appraisal']=1
    if self.appraisal['tag']=='regret' and v['id']=='purchase':parts['appraisal']=1
   edge=None
   if self.has('D') and self.attempts:
    previous=self.attempts[-1]['view_id']
    edge=next((e for e in self.catalog['links'] if e['from']==previous and e['to']==v['id']),None)
    if edge:parts['link']=edge['strength']
   if self.has('G'):parts['novelty']=2 if v['id'] not in self.observed else -3
   result.append(dict(view=v,eligible=not reasons,reasons=reasons,score=sum(parts.values()),score_parts=parts,link=edge))
  return result
 def choose(self):
  if self.active is not None:raise ValueError('In flight')
  if self.stop_reason:return None
  if len(self.attempts)>=self.arm['max_calls']:self.stop_reason='call_bound_unverified';return None
  all_facts={f['id'] for f in self.initial['facts']}<=set(self.delivered_facts)
  if not self.has('F') and all_facts:self.stop_reason='fact_presentation_end_retained';return None
  candidates=[r for r in self.candidates() if r['eligible']]
  if not candidates:self.stop_reason='eligible_views_exhausted_unverified' if self.has('F') else 'eligible_chunks_exhausted_unverified';return None
  return copy.deepcopy(sorted(candidates,key=lambda x:(-x['score'],x['view']['rank']))[0])
 def begin(self,choice):
  assert self.choose()==choice
  v=choice['view'];self.active=v['id'];self.attempts.append(dict(view_id=v['id'],fact_id=v['fact_id'],evidence_id=v['evidence_id'],status='started',semantic_status='unverified'))
 def finish(self,cid,body,reason):
  assert self.active and cid and not any(a.get('call_id')==cid for a in self.attempts)
  if reason is None and any(h['text']==body for h in self.history):reason='exact_duplicate_history'
  a=self.attempts[-1];a.update(call_id=cid,status='format_held' if reason else 'text_delivered',format_reason=reason)
  if reason is None:
   self.history.append(dict(text=body,memory_id='H06',origin='offline text delivered, semantically unverified'))
   if a['fact_id'] not in self.delivered_facts:self.delivered_facts.append(a['fact_id'])
   obs=literal_observations(body)
   for k,v in obs.items():self.observed.setdefault(k,dict(v,call_id=cid))
   a['literal_view_ids']=list(obs)
   if self.has('C'):
    if any(w in body for w in ['悔','ショック']):self.appraisal=dict(tag='regret',label='元Factの悔しさへの文字手掛かり',basis_fact_id='H06-3',evidence_id='EV4',observed_text=body,call_id=cid,semantic_status='unverified')
    elif any(w in body for w in ['怒','許せ','納得','どうにか']):self.appraisal=dict(tag='anger',label='元Factの怒りへの文字手掛かり',basis_fact_id='H06-2',evidence_id='EV2',observed_text=body,call_id=cid,semantic_status='unverified')
  self.active=None
  if reason:self.stop_reason='format_held_no_retry'
  elif len(body)>800:self.stop_reason='last_text_exceeds_history_window'
  else:self.choose()
  return reason

def render(control,choice):
 v=choice['view'];history='\n\n'.join(h['text'] for h in control.recent()) or 'なし';facts='\n'.join(f['claim'] for f in control.initial['facts'])
 text=('雑談配信の自然な口語で、今回のまとまりだけを語る。発話本文だけを出す。\n数量・否定・仮定・確実性を保ち、新しい出来事・理由・感情を足さない。\n履歴は流れのための未検証文で、事実の根拠にしない。全体の説明し直しや未指定部分の先取りは不要。\n\n【直前の発話】\n'+history+'\n\n【元Fact・文面固定】\n'+facts+'\n\n【今回使う根拠の箇所】\n'+v['basis'])
 if control.has('B'):text+='\n【今回の注目点】\n'+v['instruction']
 if control.has('C') and control.appraisal:text+='\n【直前の評価状態・文字観測で未検証】\n'+control.appraisal['label']+'。これを新事実にしない。'
 if control.has('D') and choice['link']:text+='\n【前の注目点との関係】\n'+choice['link']['label']
 return text
