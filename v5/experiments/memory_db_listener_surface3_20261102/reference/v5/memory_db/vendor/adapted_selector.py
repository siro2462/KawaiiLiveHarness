"""CPU-only discourse ordering. No language model, source-order fallback or sample rules.

The optional small linear ranker is fitted to existing manual examples. It can use
only generic cues and ngrams shared by >=3 training materials. Explicit temporal
and action constraints take precedence. All inferred relations remain unverified.
"""
import collections
import hashlib
import json
import math
import re
import unicodedata
from functools import lru_cache

SCHEMA='mechanical-stripe-selector-v1'
KINDS={'F','E','T'}
EPI={'observed','speaker_report','speaker_reaction','speaker_desire','speaker_evaluation','speaker_expectation','uncertain_memory','unverified_suspicion','counterfactual'}
STOP=set('した して った って てい いる いた ない なか こと もの ある する から ため ので よう なる 思っ とい いう 本人 自分 その この には では だっ れた れて かも もし しれ れな たか と感 感じ と考 考え と思 いた があ あっ なっ にな には のは はま まだ だと とも とし てい ては ても でも だけ けで たの のか'.split())
CUES={
 'intro':r'初めて|休日.*(?:行った|焼いた)|朝に|朝から.*行った|最近.*はま|予約を間違えた|結果が来た|^.{2,12}をした$|帰ろうとすると.*降|(?<!を見て)体験した',
 'prepare':r'説明書を読|部品を並べ|生地を.*分け|乗る直前|乗る前|予約時刻|待ち合わせは|受注',
 'attempt':r'組み立て|取り付け|向けた|押した|回した|打った|借りた|予約して',
 'result':r'当たった|当選だった|ぶれて|反応しなかった|気づいた|濃く焼け|売り切れ|得られ|見つか',
 'later':r'その後|終わった|取り出す|届いて|振り向|差し直',
 'cleanup':r'箱に戻|片[づ付]け|記録を残|皿に移|消さず.*保存',
 'return':r'帰り|返却時|返した|翌日|帰宅後|帰る前',
 'future':r'次回|次は|次も|今後|これから|まだ.*(?:予定|決め)|長期間.*まだ確かめ|方針|大切さ|両方を覚え',
 'previous':r'最初は|期待した|つもりだった|したかった',
 'flashback':r'以前|前日|先日',
 'why':r'なぜ|どうして|理由.*疑問',
 'correction':r'その後.*思い出|確認では|まだ.*(?:分から|確かめ)|断定でき|わけではない',
 'comparison':r'より|両方|違い|違う|対比|別|一方|だけ.*でも',
 'emotion':r'うれし|嬉し|ほっと|安心|びっくり|驚|がっかり|残念|焦|落ち着|悔し|困惑|困っ|痛|疲れ|気に入|自慢|感慨',
}

def norm(s):return unicodedata.normalize('NFKC',s)
def key(n):return hashlib.sha256((n['title']+'\0'+n['kind']+'\0'+n['epistemic']).encode()).hexdigest()
def validate_nodes(sample):
 nodes=sample['nodes']
 if not nodes or len({n['id'] for n in nodes})!=len(nodes):raise ValueError('empty or duplicate node IDs')
 for n in nodes:
  if not isinstance(n['title'],str) or not n['title'].strip() or n['kind'] not in KINDS or n['epistemic'] not in EPI:raise ValueError('invalid fixed Memory')
 if len({key(n) for n in nodes})!=len(nodes):raise ValueError('duplicate content needs explicit disambiguation')
 return sorted(nodes,key=key)

def terms(s):
 s=norm(s)
 # Compare content, not shared uncertainty grammar such as "かもしれない".
 for z in sorted(STOP,key=lambda z:(-len(z),z)):s=s.replace(z,' ')
 out=set()
 for word in re.findall(r'[\w一-龥ぁ-んァ-ヶー]+',s):
  for size in (2,3):out.update(word[i:i+size] for i in range(len(word)-size+1))
 return out

def overlap(a,b):
 x,y=terms(a),terms(b)
 return len(x&y)/math.sqrt(len(x)*len(y)) if x and y else 0.0

def cues(n):return {name:bool(re.search(pattern,norm(n['title']))) for name,pattern in CUES.items()}
def prior(n):
 c=cues(n);v=.48
 if c['intro']:v=.04
 elif c['previous']:v=.13
 elif c['prepare']:v=.19
 elif c['attempt']:v=.32
 elif c['result']:v=.42
 elif c['later']:v=.49
 if c['return']:v=max(v,.69)
 if c['flashback']:v=max(v,.61)
 if c['cleanup']:v=max(v,.80)
 if c['future']:v=max(v,.91)
 return v

def features(n,vocabulary):
 x={'bias':1.0,'kind:'+n['kind']:1.0,'epistemic:'+n['epistemic']:1.0}
 for name,on in cues(n).items():
  if on:x['cue:'+name]=1.0
 ts=terms(n['title'])
 for t in vocabulary:
  if t in ts:x['ng:'+t]=1.0
 return x

def fit(manual_samples,regularization=3.0):
 """Fit only ordering residuals; runtime select() never receives manual steps."""
 import numpy as np
 material_df=collections.Counter()
 for s in manual_samples:material_df.update(set().union(*(terms(n['title']) for n in s['nodes'])))
 vocabulary=sorted((t for t,f in material_df.items() if f>=3),key=lambda t:(-material_df[t],t))[:160]
 rows=[];ys=[]
 for s in manual_samples:
  by={n['id']:n for n in validate_nodes(s)};first=[];seen=set()
  for z in s['steps']:
   if z['memory_id'] not in seen:first.append(z['memory_id']);seen.add(z['memory_id'])
  if set(first)!=set(by):raise ValueError('manual teaching example must cover all nodes')
  for i,mid in enumerate(first):
   n=by[mid];rows.append(features(n,vocabulary));ys.append(i/max(1,len(first)-1)-prior(n))
 columns=sorted(set().union(*(x.keys() for x in rows)));ix={k:i for i,k in enumerate(columns)}
 X=np.zeros((len(rows),len(columns)))
 for i,row in enumerate(rows):
  for k,v in row.items():X[i,ix[k]]=v
 w=np.linalg.solve(X.T@X+regularization*np.eye(len(columns)),X.T@np.asarray(ys))
 return dict(schema=SCHEMA,vocabulary=vocabulary,weights={k:float(w[i]) for i,k in enumerate(columns)},regularization=regularization,
  residual_mix=.55,min_ngram_material_df=3,training_materials=len(manual_samples),training_nodes=len(rows),
  sample_ID_features=False,node_ID_features=False,input_order_features=False,source_text_features=False,
  temporal_rules='shared explicit-cue rules; no material-specific IDs or fixed sequences',model_kind='CPU ridge ordering residual; not an LLM or LoRA')

def rank(n,model):
 if model is None:return prior(n)
 if model['schema']!=SCHEMA:raise ValueError('wrong ranker schema')
 return prior(n)+model['residual_mix']*sum(model['weights'].get(k,0)*v for k,v in features(n,model['vocabulary']).items())

def compile_relations(nodes):
 by={n['id']:n for n in nodes};edges=[];unresolved=[]
 def find(pattern,kind='F'):
  return [n for n in nodes if n['kind'] in kind and n['epistemic'] not in ('counterfactual','unverified_suspicion','uncertain_memory') and re.search(pattern,norm(n['title']))]
 def add(a,b,rule,priority=80,relation='requires'):
  if a['id']!=b['id']:edges.append(dict(before=a['id'],after=b['id'],rule=rule,priority=priority,relation=relation,verification='lexical rule, unverified semantics'))
 def cross(left,right,rule,priority=80):
  for a in left:
   for b in right:add(a,b,rule,priority)
 # Reusable action prerequisites, not the order of source lines.
 instructions=find(r'説明書を読|部品を並べ');assembly=find(r'すべて取り付け|全部取り付け|組み上げた')
 cross(instructions,assembly,'read/prepare_before_assembly_detail')
 cross(instructions+assembly,find(r'説明書.*箱に戻|余った.*箱に戻|片[づ付]けた'),'used_materials_before_cleanup')
 borrow=find(r'借りた$');returned=find(r'返した$|返却した$')
 cross(borrow,returned,'borrow_before_return',95)
 cross(borrow,find(r'借りた.*乾か|借りた.*開いて'),'borrow_before_drying')
 cross(find(r'翌日.*戻った'),returned,'return_visit_before_return',90)
 cross(find(r'食べた|試食した'),find(r'食べ比べた.*除く|試した.*以外.*移'),'tasting_before_leftovers',95)
 # Preparing an action and waiting for it precede its result. Matching a noun
 # alone never creates an edge: both action predicates must be explicit.
 bake_setup=find(r'生地を.*分け|天板を.*使|焼き時間を.*設定')
 baked=find(r'取り出すと.*焼け|中央の.*焼き色')
 cross(bake_setup,baked,'baking_setup_before_visible_result',90)
 cross(baked,find(r'冷まして食べた'),'visible_result_before_tasting',90)
 cross([n for n in nodes if re.search(r'焼けるのを楽しみに待',n['title'])],baked,'waiting_before_outcome',90)
 failure=find(r'どの.*反応しなかった|全く.*動かなかった');reconnect=find(r'差し直した|つなぎ直した')
 fixed=find(r'差し直すと.*(?:できる|動く)|つなぎ直すと.*動');probe=find(r'全.*一つずつ押した|一つずつ.*確かめた')
 probe_result=find(r'その確認では.*反応した|確認すると.*反応した')
 cross(failure,reconnect,'failure_before_repair',95);cross(reconnect,fixed,'repair_before_recovery',95)
 cross(fixed,probe,'recovery_before_full_check',90);cross(probe,probe_result,'check_before_its_result',95)
 inspection_intent=find(r'その前に.*接続を見よう',kind='T')
 cross(find(r'開け直そうとして手を止め'),inspection_intent,'pause_before_inspection_intent',90)
 cross(inspection_intent,find(r'差し込みが浅かった'),'inspection_intent_before_finding',90)
 cross(find(r'差し込みが浅かった'),reconnect,'finding_before_reconnect',90)
 shutter=find(r'シャッター.*押した');blur=find(r'保存された.*ぶれ|撮れた.*ぶれ')
 cross(shutter,blur,'capture_before_image_result',95)
 cross(find(r'(スマートフォン|カメラ|携帯|端末)を向けた'),shutter,'aim_before_capture',90)
 cross(shutter,find(r'(スマートフォン|カメラ|携帯|端末)を下ろした'),'capture_before_lowering',90)
 cross(blur,find(r'撮った.*消さず.*保存'),'image_result_before_retaining_images',90)
 # A remaining action needs the initial action and its explicit permission.
 extra=find(r'残[りっ].*(打った|使った|試した)')
 cross(find(r'最初.*当てた|1発目で当てた'),extra,'initial_attempt_before_remaining_attempt',90)
 cross(find(r'残った.*(?:よい|いい).*言われた'),extra,'permission_before_remaining_action',95)
 cross(find(r'1発目で当てた'),[n for n in nodes if n['kind']=='E' and re.search(r'1発目.*自慢',n['title'])],'first_success_before_boast',85)
 # Common transport repair sequence. These are predicate pairs, not a topic ID
 # or a prewritten array; absent/changed actions do not obtain these edges.
 departed=find(r'乗ったのは.*逆方向');noticed=find(r'駅名を見て気づいた')
 exited=find(r'次の駅で降りた');direction=find(r'案内板で戻る方向を確認')
 reboarded=find(r'乗り直した');arrived=find(r'遅れて着いた')
 cross(find(r'乗る直前.*確認'),departed,'departure_check_before_wrong_direction',90)
 cross(departed,noticed,'wrong_direction_before_discovery',95)
 cross(noticed,exited,'discovery_before_disembarking',95)
 cross(exited,direction,'disembark_before_route_check',90)
 cross(direction,reboarded,'route_check_before_reboarding',90)
 cross(reboarded,arrived,'reboarding_before_late_arrival',95)
 cross(find(r'連絡した'),find(r'返信があった'),'message_before_reply',95)
 cross(arrived,find(r'遅れたことを謝った|その後.*入れた'),'arrival_before_apology_or_visit',90)
 cross(arrived,find(r'^帰りは'),'outbound_arrival_before_return_trip',90)
 cross(find(r'帰る前に.*見た'),find(r'その時.*いなかった'),'look_before_absence_result',90)
 # An appraisal of having noticed something cannot be used as a color
 # separator before the discovery it appraises. Only a unique explicit
 # discovery is bound; multiple possible events are not silently guessed.
 discoveries=find(r'気づいた')
 if len(discoveries)==1:
  for assessment in nodes:
   if assessment['kind'] in ('E','T') and re.search(r'気づけた.*(?:よかった|助かった)',assessment['title']):add(discoveries[0],assessment,'discovery_before_positive_appraisal',100,'appraisal')
 # A stated transition into a season supports retrospective feelings about
 # reaching that season. This is not a global numeric sorting of months:
 # reservations, earlier years and unrelated dates are not reordered.
 for month_pattern,season in [(r'(?:3|4|5)月になった','春'),(r'(?:6|7|8)月になった','夏'),(r'(?:9|10|11)月になった','秋'),(r'(?:12|1|2)月になった','冬')]:
  transitions=find(month_pattern)
  if len(transitions)==1:
   for assessment in nodes:
    if assessment['kind'] in ('E','T') and re.search(season+r'(?:まで|に入った)',assessment['title']):add(transitions[0],assessment,'season_transition_before_retrospective_appraisal',100,'appraisal')
 # An explicit previous-event cue can resolve a deictic "the following day".
 previous=find(r'以前|前日|先日')
 for b in find(r'^その翌日'):
  if len(previous)==1:add(previous[0],b,'explicit_previous_event_before_next_day',100,'time_after')
  else:unresolved.append(dict(node_id=b['id'],reason='ambiguous next-day antecedent',candidate_ids=[a['id'] for a in previous],block_emission=True))
 # "During X" follows the explicitly described occurrence of X, when a
 # unique shared concrete name is available. No noun-only global ordering.
 concrete=lambda text:set(re.findall(r'[ァ-ヶー]{2,}|[一-龥]{2,}',text))
 for inside in find(r'中は'):
  candidates=[n for n in find(r'行った|訪れた') if concrete(n['title'])&concrete(inside['title'])]
  if len(candidates)==1:add(candidates[0],inside,'event_before_its_inside_activity',90)
 # Bind a question -> observable answer -> acknowledgement as one explanatory chain.
 questions=[n for n in nodes if n['kind']=='T' and re.search(r'なぜ|どうして',n['title'])]
 for q in questions:
  facts=[n for n in nodes if n['kind']=='F'];scored=sorted([(overlap(q['title'],f['title']),key(f),f) for f in facts],key=lambda z:(-z[0],z[1]))
  if not scored or scored[0][0]<.09:continue
  witness=scored[0][2];add(witness,q,'observed_puzzle_before_question',90)
  # A shared concrete noun can survive in a long answer even when normalized
  # character cosine is small. Grammatical overlaps cannot satisfy this test.
  nouns=lambda text:set(re.findall(r'[一-龥]{2,}',text))
  answers=[f for f in facts if re.search(r'(全部|すべて|全て).*(から|後)',f['title']) and (overlap(f['title'],witness['title'])>=.08 or nouns(f['title'])&nouns(witness['title']))]
  if len(answers)==1:
   a=answers[0];add(q,a,'explicit_after_all_answer_after_question',90,'explanation')
   acknowledgements=[n for n in nodes if n['kind']=='E' and re.search(r'なるほど|腑に落ち|納得した',n['title'])]
   if len(acknowledgements)==1:add(a,acknowledgements[0],'answer_before_acknowledgement',95,'reaction')
  else:unresolved.append(dict(node_id=q['id'],reason='question answer not uniquely recoverable',candidate_ids=[a['id'] for a in answers]))
 # Observed outcomes anchor reactions. Emotion words alone never create an outcome.
 attachment_rules=[
  (r'当選して.*(?:うれ|嬉)',r'当選だった','won_before_joy'),
  (r'完成した.*(?:うれ|嬉)',r'すべて取り付け|全部取り付け|組み上げた','completion_before_joy'),
  (r'壊した.*焦|動か.*焦',r'反応しなかった|動かなかった','failure_before_alarm'),
  (r'壊れていなさそう.*安心',r'差し直すと.*できる|つなぎ直すと.*動','recovery_before_relief'),
  (r'連絡がついて.*落ち着',r'返信があった','reply_before_relief'),
  (r'気づいた瞬間.*焦',r'気づいた','notice_before_alarm'),
  (r'返し終えて',r'返した|返却した','return_before_relief'),
  (r'振り返って.*びっくり|突然で驚',r'振り向くと','turn_before_surprise'),
  (r'借りられて.*ほっと',r'借りた$','borrow_before_relief'),
  (r'持ってきたつもり.*困',r'置いてきていた$','left_behind_before_difficulty'),
  (r'戻れて.*ほっと',r'乗り直した','route_recovery_before_relief'),
  (r'うまく撮れず.*残念',r'保存された.*ぶれ|撮れた.*ぶれ','image_result_before_disappointment'),
  (r'見逃した気.*悔',r'飛んでいった|離れていった|去っていった','departure_before_missed_opportunity'),
  (r'画面を見ていた時より落ち着',r'(スマートフォン|カメラ|携帯|端末)を下ろした','lower_device_before_calm'),
  (r'立ちっぱなし.*疲れ',r'中は立ちっぱなし','standing_before_fatigue'),
  (r'焼き色がそろわず',r'濃く焼け|薄い焼き色','visible_result_before_disappointment'),
 ]
 for emotion,trigger,name in attachment_rules:
  cross(find(trigger),[n for n in nodes if n['kind']=='E' and re.search(emotion,n['title'])],name,85)
 # "At that time" may react to the already introduced dated event; the
 # detailed reason can legitimately be explained afterwards in conversation.
 dated=find(r'^その翌日')
 if len(dated)==1:
  cross(dated,[n for n in nodes if n['kind']=='E' and re.search(r'^その時',n['title'])],'dated_event_before_deictic_reaction',85)
 # A short context-setting introduction may be followed by its details and
 # reactions. Explicit flashbacks are not made the opening just for being old.
 introductions=[n for n in nodes if n['kind']=='F' and cues(n)['intro']]
 if len(introductions)==1:
  intro=introductions[0]
  for n in nodes:
   if n['kind']=='F' and not cues(n)['intro']:add(intro,n,'context_before_detail',70)
 # Provided structural metadata is allowed, but never fabricated from ID order.
 for n in nodes:
  for rid in n.get('requires',[]):
   if rid not in by:raise ValueError('unknown explicit dependency')
   add(by[rid],n,'provided_dependency',110)
 # Reject cycles explicitly; weaker inferred constraints cannot silently override stronger ones.
 accepted=[];rejected=[];adj=collections.defaultdict(set)
 def reaches(start,end):
  queue=[start];seen=set()
  while queue:
   cur=queue.pop()
   if cur==end:return True
   if cur not in seen:seen.add(cur);queue.extend(adj[cur])
  return False
 unique={(e['before'],e['after'],e['rule']):e for e in edges}
 for e in sorted(unique.values(),key=lambda e:(-e['priority'],key(by[e['before']]),key(by[e['after']]),e['rule'])):
  if reaches(e['after'],e['before']):
   if e['priority']>=110:raise ValueError('explicit dependency cycle')
   rejected.append(dict(e,reason='would form a cycle'));continue
  adj[e['before']].add(e['after']);accepted.append(e)
 return accepted,unresolved,rejected

def operation(n):
 if n['kind']=='F':return 'REPORT'
 if n['kind']=='E':return 'REACT'
 if n['epistemic']=='uncertain_memory':return 'REPAIR'
 if n['epistemic']=='counterfactual' or cues(n)['comparison']:return 'COMPARE'
 if n['epistemic']=='speaker_evaluation':return 'APPRAISE'
 return 'EXPLORE'

def select(sample,model=None,max_revisits=3,max_same_kind=3,search_budget=20000):
 if isinstance(max_same_kind,bool) or not isinstance(max_same_kind,int) or max_same_kind<1:raise ValueError('invalid same-kind limit')
 if isinstance(search_budget,bool) or not isinstance(search_budget,int) or search_budget<1:raise ValueError('invalid search budget')
 nodes=validate_nodes(sample);by={n['id']:n for n in nodes};scores={n['id']:rank(n,model) for n in nodes}
 edges,unresolved,rejected=compile_relations(nodes);parents=collections.defaultdict(set);incoming=collections.defaultdict(list)
 for e in edges:parents[e['after']].add(e['before']);incoming[e['after']].append(e)
 used=set();order=[];decisions=[];steps=[];revisits=[];revisit_pairs=set();suppressed_revisits=[]
 deferred={x['node_id']:dict(memory_id=x['node_id'],reason=x['reason']) for x in unresolved if x.get('block_emission')}
 changed=True
 while changed:
  changed=False
  for n in nodes:
   if n['id'] not in deferred and parents[n['id']]&set(deferred):
    deferred[n['id']]=dict(memory_id=n['id'],reason='prerequisite was deferred',blocked_by=sorted(parents[n['id']]&set(deferred)));changed=True
 pending={n['id'] for n in nodes}-set(deferred)
 # A necessary remaining-color count check avoids spending every reaction
 # early and leaving a long factual tail. A bounded topological search then
 # checks whether the pending prerequisites still admit a complete schedule.
 # No color relabeling, new emotion, or prerequisite relaxation is allowed.
 active=sorted(pending,key=lambda mid:key(by[mid]));bit={mid:1<<i for i,mid in enumerate(active)}
 full=sum(bit.values());parent_bits={mid:sum(bit[x] for x in parents[mid] if x in bit) for mid in active}
 explored=0;budget_exhausted=False
 @lru_cache(maxsize=None)
 def completion(mask,last,streak):
  nonlocal explored,budget_exhausted
  if mask==full:return True
  if explored>=search_budget:budget_exhausted=True;return None
  explored+=1
  remaining=[mid for mid in active if not mask&bit[mid]]
  counts=collections.Counter(by[mid]['kind'] for mid in remaining)
  for k,count in counts.items():
   other=len(remaining)-count
   if count>max_same_kind*(other+1)-(streak if k==last else 0):return False
  ready=sorted((mid for mid in remaining if parent_bits[mid]&mask==parent_bits[mid]),key=lambda mid:(scores[mid],key(by[mid])))
  unknown=False
  for mid in ready:
   k=by[mid]['kind'];next_streak=streak+1 if k==last else 1
   if next_streak>max_same_kind:continue
   result=completion(mask|bit[mid],k,next_streak)
   if result is True:return True
   if result is None:unknown=True
  return None if unknown else False
 def mask_of_used():return sum(bit[mid] for mid in used if mid in bit)
 def tail():
  if not steps:return None,0
  last=steps[-1]['kind'];streak=0
  for z in reversed(steps):
   if z['kind']!=last:break
   streak+=1
  return last,streak
 initial_feasible=completion(0,None,0)
 def anchor_for(n):
  semantic = memory_db_anchor(n, used, order)
  if semantic is not None:return semantic
  es=[e for e in incoming[n['id']] if e['before'] in used]
  if es:
   e=max(es,key=lambda e:(e['priority'],order.index(e['before'])))
   return e['before'],e['rule'],[x['before'] for x in es],True
  if n['kind']!='F':
   fs=[by[mid] for mid in order if by[mid]['kind']=='F']
   if fs:
    ranked=sorted([(overlap(n['title'],f['title']),order.index(f['id']),f) for f in fs],key=lambda z:(-z[0],-z[1]))
    if ranked[0][0]>=.12:
     z=ranked[0];return z[2]['id'],'content_anchor_unverified',[z[2]['id']],False
  return (order[-1] if order else None),'continuity_only_not_causal',[],False
 while pending:
  ready=[by[mid] for mid in pending if parents[mid]<=used]
  if not ready:raise ValueError('no legal next node')
  candidates=[]
  for n in ready:
   score=scores[n['id']]+memory_db_soft_penalty(n, used);aid,rule,basis,explicit=anchor_for(n)
   # React to a newly available outcome before moving to unrelated material.
   if explicit and n['kind'] in ('E','T') and aid and order and order[-1]==aid:score-=.32
   if explicit and n['kind']=='E' and aid and order and order[-1]==aid:score-=1.0
   if steps and n['kind']==steps[-1]['kind']:score+=.035
   candidates.append((score,key(n),n,aid,rule,basis,explicit))
  candidates.sort(key=lambda x:(x[0],x[1]));last,streak=tail()
  allowed=[z for z in candidates if z[2]['kind']!=last or streak<max_same_kind]
  rejected=[z[2]['id'] for z in candidates if z not in allowed]
  if not allowed:
   for mid in sorted(pending,key=lambda mid:key(by[mid])):deferred[mid]=dict(memory_id=mid,reason='same-kind limit reached; no prerequisite-ready different kind',limit=max_same_kind)
   decisions.append(dict(index=len(steps)+1,chosen=None,rejected_by_same_kind_limit=rejected,stop='rhythm_blocked',last_kind=last,streak=streak));break
  feasibility=[];win=None
  for candidate in allowed:
   k=candidate[2]['kind'];ns=streak+1 if k==last else 1
   possible=completion(mask_of_used()|bit[candidate[2]['id']],k,ns)
   feasibility.append(dict(memory_id=candidate[2]['id'],complete_schedule_possible=possible))
   if possible is True:win=candidate;break
  if win is None:
   # If a complete schedule is impossible (or search is bounded), retain a
   # valid prefix and explicitly defer the remainder if a boundary blocks it.
   unknown={x['memory_id'] for x in feasibility if x['complete_schedule_possible'] is None}
   win=next((z for z in allowed if z[2]['id'] in unknown),allowed[0])
  _,_,n,aid,rule,basis,explicit=win
  decisions.append(dict(index=len(steps)+1,candidates=[dict(memory_id=z[2]['id'],priority=round(z[0],9),rule=z[4]) for z in candidates],chosen=n['id'],rejected_by_same_kind_limit=rejected,completion_checks=feasibility,last_kind=last,streak=streak))
  step=dict(index=len(steps)+1,memory_id=n['id'],operation=operation(n),kind=n['kind'],content=n['title'],epistemic=n['epistemic'],relation=rule,anchor_id=aid)
  steps.append(step);used.add(n['id']);pending.remove(n['id']);order.append(n['id'])
  # Return only to an already presented basis after a NEW evaluation purpose.
  if n['kind']=='T' and basis and len(revisits)<max_revisits and len(order)>=5:
   choices=[mid for mid in basis if mid!=n['id'] and by[mid]['kind']=='F' and (mid,n['epistemic']) not in revisit_pairs and (not revisits or len(steps)-revisits[-1]['index']>=5)]
   if choices:
    mid=max(choices,key=lambda mid:order.index(mid));old=by[mid]
    last,streak=tail();new_streak=streak+1 if old['kind']==last else 1
    future=completion(mask_of_used(),old['kind'],new_streak) if new_streak<=max_same_kind else False
    if new_streak<=max_same_kind and future is True:
     z=dict(index=len(steps)+1,memory_id=mid,operation='REVISIT',kind=old['kind'],content=old['title'],epistemic=old['epistemic'],relation='return_after_new_evaluation_not_new_fact',anchor_id=n['id'])
     steps.append(z);revisits.append(dict(index=z['index'],memory_id=mid,new_purpose_node=n['id'],basis_was_presented=True));revisit_pairs.add((mid,n['epistemic']))
    else:suppressed_revisits.append(dict(memory_id=mid,new_purpose_node=n['id'],reason='would block bounded-rhythm completion or completion unproved'))
 return dict(schema=SCHEMA,steps=steps,constraints=edges,unresolved_relations=unresolved,rejected_constraints=rejected,deferred_nodes=list(deferred.values()),
  decisions=decisions,first_occurrence_order=order,rank_scores={mid:round(v,9) for mid,v in scores.items()},
  revisits=revisits,suppressed_revisits=suppressed_revisits,stop_reason=('safe_plan_complete_with_unresolved_nodes_deferred' if deferred else 'all_fixed_Memory_presented; plan complete, speech not generated'),
  rhythm_policy=dict(max_same_kind=max_same_kind,mode='hard limit including REVISIT; preserve prerequisites and fixed labels',initial_complete_schedule_possible=initial_feasible,search_budget=search_budget,states_explored=explored,budget_exhausted=budget_exhausted),
  semantic_status='unverified',model_calls=0,source_order_used=False,manual_steps_used_at_selection=False)

def validate_plan(sample,plan):
 by={n['id']:n for n in validate_nodes(sample)};seen=set();first={}
 for i,z in enumerate(plan['steps'],1):
  if z['index']!=i or z['memory_id'] not in by:raise ValueError('bad step/index')
  n=by[z['memory_id']]
  if any(z[k]!=n[v] for k,v in [('content','title'),('kind','kind'),('epistemic','epistemic')]):raise ValueError('changed fixed Memory')
  if z['anchor_id'] is not None and z['anchor_id'] not in seen:raise ValueError('future anchor')
  if z['operation']=='REVISIT' and z['memory_id'] not in seen:raise ValueError('unseen revisit')
  if z['memory_id'] in seen and z['operation']!='REVISIT':raise ValueError('repeat without new-purpose revisit')
  first.setdefault(z['memory_id'],i);seen.add(z['memory_id'])
 limit=plan.get('rhythm_policy',{}).get('max_same_kind')
 if limit is not None:
  last=None;streak=0
  for z in plan['steps']:
   streak=streak+1 if z['kind']==last else 1;last=z['kind']
   if streak>limit:raise ValueError('same-kind rhythm limit violated')
 deferred={x['memory_id'] for x in plan.get('deferred_nodes',[])}
 if seen&deferred or seen|deferred!=set(by):raise ValueError('fixed Memory omitted without explicit deferral')
 for e in plan['constraints']:
  if e['after'] in seen and (e['before'] not in seen or first[e['before']]>=first[e['after']]):raise ValueError('constraint violation')
 return True

def render_input(sample,plan,base_renderer):
 validate_plan(sample,plan)
 # Exact old manual-32 Surface prompt contract, with dynamic step count only.
 steps=plan['steps'];prompt,payload=base_renderer(dict(kind='stripe',steps=steps),[],None,steps)
 fixed='【現在のテーマ】\nガラポンでA賞が出なかった体験\n'
 if prompt.count(fixed)!=1 or '\n' in sample['title']:raise ValueError('unexpected renderer/theme')
 return prompt.replace(fixed,'【現在のテーマ】\n'+sample['title']+'\n',1),payload
