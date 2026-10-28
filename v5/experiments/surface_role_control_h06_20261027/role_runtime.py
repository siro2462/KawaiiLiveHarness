"""Bounded H06 roles and literal-angle observations. No semantic judge or Memory writes."""
import copy,re,unicodedata
from contract_runtime import validate

def validate_roles(case,roles):
 validate(case)
 if not isinstance(roles,list) or not roles:raise ValueError('Missing roles')
 facts={x['id']:x['claim'] for x in case['facts']};seen=set()
 for r in roles:
  if set(r)!={'id','label','instruction','fact_id','basis'}:raise ValueError('Unexpected role fields')
  if r['id'] not in ('result_mismatch','purchase_comparison') or r['id'] in seen:raise ValueError('Unknown or repeated role')
  if any(not isinstance(r[k],str) or not r[k].strip() for k in r):raise ValueError('Empty role field')
  if r['fact_id'] not in facts or r['basis'] not in facts[r['fact_id']]:raise ValueError('Role basis not in fixed Fact')
  if len(r['instruction'])>200:raise ValueError('Role instruction too long')
  seen.add(r['id'])
 return roles

def render(case,role):
 validate_roles(case,[role])
 history='\n\n'.join(h['text'] for h in case['history']) or 'なし'
 facts='\n'.join(f['claim'] for f in case['facts'])
 return ('雑談配信の自然な口語で、今回の役割だけを語る。根拠全文の説明し直しは不要。\n'
         '数量・否定・仮定・確実性を保ち、新しい出来事・理由・感情を足さない。\n'
         '履歴は文脈用で未検証。既に語った点を説明し直さず、別の役割を先取りしない。発話本文だけを出す。\n\n'
         '【直前の発話】\n'+history+'\n\n【根拠Fact】\n'+facts+
         '\n\n【今回の役割】\n'+role['instruction']+'\n【今回使う根拠の箇所】\n'+role['basis'])

def literal_angle_evidence(body):
 s=unicodedata.normalize('NFKC',body).replace(',','')
 found={}
 if '景品' in s and any(w in s for w in ['当たら','当たん']) and any(w in s for w in ['のに','なのに','でも','だけど']):
  found['result_mismatch']={'text':body,'cue_rule':'景品 + 当たら/当たん + 対比語','semantic_status':'unverified'}
 if re.search(r'(?:9000|九千|9千)円',s) and re.search(r'買(?:え|っ|う)',s) and any(w in s for w in ['なら','たら','れば','じゃない','では','かも','かな']):
  found['purchase_comparison']={'text':body,'cue_rule':'9000円 + 購入語 + 仮定/疑問語','semantic_status':'unverified'}
 return found

class RoleControl:
 def __init__(self,case,roles,max_calls=2):
  validate_roles(case,roles)
  if type(max_calls) is not int or not 1<=max_calls<=2:raise ValueError('Call bound must be 1 or 2')
  self.initial_case=copy.deepcopy(case);self.roles=copy.deepcopy(roles);self.max_calls=max_calls
  self.history=copy.deepcopy(case['history']);self.attempts=[];self.observed={};self.active=None;self.stop_reason=None
 def recent(self):
  keep=[]
  for row in reversed(self.history):
   if len(keep)==2 or sum(len(x['text']) for x in keep)+len(row['text'])>800:break
   keep.insert(0,copy.deepcopy(row))
  return keep
 def case(self):
  c=copy.deepcopy(self.initial_case);c['history']=self.recent();validate(c);return c
 def next_role(self):
  if self.active is not None:raise ValueError('Attempt already in flight')
  if self.stop_reason:return None
  if all(r['id'] in self.observed for r in self.roles):self.stop_reason='all_angles_have_literal_cues_unverified';return None
  if len(self.attempts)>=self.max_calls:self.stop_reason='call_budget_exhausted_unverified';return None
  attempted={a['role_id'] for a in self.attempts}
  eligible=[r for r in self.roles if r['id'] not in attempted and r['id'] not in self.observed]
  if not eligible:self.stop_reason='assigned_roles_exhausted_unverified';return None
  return copy.deepcopy(eligible[0])
 def begin(self,role_id):
  role=self.next_role()
  if role is None or role['id']!=role_id:raise ValueError('Unexpected next role')
  self.active=role_id;self.attempts.append({'role_id':role_id,'status':'started','semantic_status':'unverified'})
 def finish(self,call_id,body,format_reason):
  if self.active is None or not call_id:raise ValueError('No active attempt or call ID')
  if any(a.get('call_id')==call_id for a in self.attempts):raise ValueError('Call receipt already used')
  if format_reason is None and any(body==h['text'] for h in self.history):format_reason='exact_duplicate_history'
  row=self.attempts[-1];row.update(call_id=call_id,status='format_held' if format_reason else 'text_delivered',format_reason=format_reason)
  evidence={}
  if format_reason is None:
   evidence=literal_angle_evidence(body)
   for aid,e in evidence.items():self.observed.setdefault(aid,dict(e,call_id=call_id))
   self.history.append({'text':body,'memory_id':'H06','origin':'offline text delivered, semantically unverified'})
  row['literal_angle_ids']=list(evidence);self.active=None
  if format_reason:self.stop_reason='format_held_no_retry'
  elif len(body)>800 and not all(r['id'] in self.observed for r in self.roles):self.stop_reason='last_delivery_exceeds_history_window'
  else:self.next_role()
  return format_reason
 def snapshot(self):
  return copy.deepcopy({'roles':self.roles,'attempts':self.attempts,'observed_angles':self.observed,'active_role':self.active,'stop_reason':self.stop_reason,'calls_used':len(self.attempts),'max_calls':self.max_calls,'semantic_status':'unverified','source_fact_progress_updated':False,'history_size':len(self.history),'recent':self.recent(),'observation_definition':'literal phrase cues only; not verified meaning or factual coverage'})
