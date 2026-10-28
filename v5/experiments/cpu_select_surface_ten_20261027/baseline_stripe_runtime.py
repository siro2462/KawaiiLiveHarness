"""Fixed supplied stripes -> Surface prompts. No operation reselection or semantic judge."""
import copy,json,re
from contract_runtime import render as legacy_render
from runtime import surface_case
OPS={'REPORT':'出来事を伝える','EVIDENCE':'説明や根拠となる詳細を伝える','REACT':'与えられた本人の感情・反応を表す','EXPLORE':'本人の考え・期待・疑念を確実性の区別を保って語る','COMPARE':'指定された比較・対比を語る','APPRAISE':'与えられた本人の評価を語る','REVISIT':'提示済みの内容へ戻り、今回の流れで強調する','REPAIR':'不確かな記憶や言い直しを、その不確かさを保って語る'}
EPI={'observed':'体験した出来事の報告','speaker_report':'本人の報告。外部の確認済み保証へ広げない','speaker_reaction':'本人の反応・感情','speaker_desire':'本人の欲求','speaker_evaluation':'本人の評価で、客観的事実の断定ではない','speaker_expectation':'本人がそう感じた期待・予感で、将来の確定結果ではない','uncertain_memory':'記憶が不確か。分からない部分を補って確定しない','unverified_suspicion':'未確認の疑念。仕組みや不正が確認されたと断定しない','counterfactual':'実行していない仮定の比較。実際の購入や確定価格にしない'}

def validate_steps(steps,nodes):
 by={n['id']:n for n in nodes};assert len(steps)==32 and len(by)==29
 for i,s in enumerate(steps,1):
  assert s['index']==i and s['operation'] in OPS and s['epistemic'] in EPI and s['memory_id'] in by
  n=by[s['memory_id']];assert s['content']==n['title'] and s['epistemic']==n['epistemic'] and s['kind']==n['kind']
  if s['anchor_id']:assert s['anchor_id'] in {x['memory_id'] for x in steps[:i-1]}
 assert [s['memory_id'] for s in steps if s['operation']=='REVISIT']==['L25','L10','L08']
 return True

def schedule(steps):
 return [dict(arm='A',groups=[dict(kind='legacy',fact_ids=['H06-1','H06-2']),dict(kind='legacy',fact_ids=['H06-3'])]),dict(arm='B',groups=[dict(kind='stripe',steps=copy.deepcopy(steps))]),dict(arm='C',groups=[dict(kind='stripe',steps=copy.deepcopy(steps[i:i+4])) for i in range(0,32,4)])]

def recent(history):
 keep=[]
 for h in reversed(history):
  if len(keep)==2 or sum(len(x['text']) for x in keep)+len(h['text'])>800:break
  keep.insert(0,copy.deepcopy(h))
 return keep

def render(group,history,memory,all_steps):
 hist=recent(history)
 if group['kind']=='legacy':
  case=surface_case(memory,group['fact_ids'],hist,[],'ガラポンの体験を話し始める。根拠のない別の出来事や因果を追加しない。','stripe-A')
  return legacy_render(case),dict(kind='legacy',case=case)
 steps=group['steps'];prior=all_steps[:steps[0]['index']-1];by={s['memory_id']:s for s in prior};current={s['memory_id'] for s in steps};anchors=[]
 for s in steps:
  aid=s['anchor_id']
  if aid and aid not in current and aid not in {a['memory_id'] for a in anchors}:
   old=by[aid];anchors.append({k:old[k] for k in ['memory_id','content','epistemic']})
 payload=[{k:s[k] for k in ['index','memory_id','operation','kind','content','epistemic','relation','anchor_id']} for s in steps]
 prompt=('雑談配信中の自然な口語で、今回の操作列を並びの順に発話へ変換する。操作の意味と確実性を守る。\n'
 '1操作を1文に固定せず、複数操作をまとめたり短い言い直しを使ってよい。未指定の出来事・理由・感情を足さず、次の未提示操作を先取りしない。\n'
 'REVISITは指定された再言及。反応や疑念を確定した出来事へ変えない。関係は接続の手掛かりで、別の因果事実を作らない。\n'
 '履歴は流れのための未検証文で、新事実の根拠にしない。この区間のたびに要約や締めを付けない。発話本文だけを出し、ID・操作名・色名・見出し・ト書きを出さない。\n\n'
 '【現在のテーマ】\nガラポンでA賞が出なかった体験\n\n【操作の意味】\n'+json.dumps(OPS,ensure_ascii=False)+'\n\n【確実性の意味】\n'+json.dumps(EPI,ensure_ascii=False)+'\n\n【直前の発話】\n'+('\n\n'.join(x['text'] for x in hist) or 'なし')+'\n\n【接続の参照・新たな操作ではない】\n'+json.dumps(anchors,ensure_ascii=False)+'\n\n【今回の操作列】\n'+json.dumps(payload,ensure_ascii=False))
 return prompt,dict(kind='stripe',steps=copy.deepcopy(steps),anchor_context=anchors,history=hist,source_quotes_sent=False,preplanned=True,adaptive_reselection=False)

def format_reason(body,eos):
 if not isinstance(body,str) or not body.strip():return 'empty'
 if not eos:return 'incomplete_stop_or_token_cap'
 if len(body)>6000:return 'excessive_length_over6000'
 if re.search(r'<[^>]+>|^\s*[\[{]|【|^\s*#{1,6}\s|\b(?:REPORT|REACT|EVIDENCE|EXPLORE|REVISIT|REPAIR|APPRAISE|COMPARE|L\d{2})\b',body):return 'markup_or_operation_leak'
 return None

def text_units(body):
 """Fixed punctuation/newline boundaries; all chars preserved. Labels are assigned later."""
 if not body.strip():return []
 stops=[m.end() for m in re.finditer(r'[。！？!?]|\n+',body)]+[len(body)];units=[];start=0
 for end in sorted(set(stops)):
  if end<=start:continue
  text=body[start:end]
  if not text.strip():
   if units:units[-1]['end']=end;units[-1]['text']=body[units[-1]['start']:end];start=end
   continue
  units.append(dict(index=len(units)+1,start=start,end=end,text=text));start=end
 assert ''.join(u['text'] for u in units)==body
 return units
