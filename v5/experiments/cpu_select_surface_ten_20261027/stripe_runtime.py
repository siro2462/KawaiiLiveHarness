import copy,json,re
from common import OUT
from baseline_stripe_runtime import OPS as BASE_OPS,EPI,text_units
OPS=dict(BASE_OPS,SPECULATE='指定された期待・疑念を未確認のまま語る',REAPPRAISE='与えられた根拠で評価し直す',GENERALIZE='与えられた範囲の考えを述べる',REENACT='指定された場面だけを再現する',ASSOCIATE='根拠のある連想を述べる')
def validate_sample(s):
 assert s['initial_history']==[] and len(s['nodes'])==29 and 1<=len(s['steps'])<=45
 by={n['id']:n for n in s['nodes']};seen=set()
 for i,x in enumerate(s['steps'],1):
  assert x['index']==i and x['operation'] in OPS and x['epistemic'] in EPI
  n=by[x['memory_id']];assert (x['content'],x['kind'],x['epistemic'])==(n['title'],n['kind'],n['epistemic'])
  if x['anchor_id']:assert x['anchor_id'] in seen
  if x['operation']=='REVISIT':assert x['memory_id'] in seen
  seen.add(x['memory_id'])
 return True
def render_sample(s,style=True):
 validate_sample(s)
 prompt=('雑談配信中の自然な口語で、今回の操作列を並びの順に発話へ変換する。操作の意味と確実性を守る。\n'
 '1操作を1文に固定せず、複数操作をまとめたり短い言い直しを使ってよい。未指定の出来事・理由・感情を足さず、未提示の内容を先取りしない。\n'
 'REVISITは指定された再言及。反応や疑念を確定した出来事へ変えない。関係は接続の手掛かりで、別の因果事実を作らない。\n'
 '発話本文だけを出し、ID・操作名・色名・見出し・ト書きを出さない。\n\n')
 if style:prompt+=(OUT/'reaction_style.txt').read_text('utf-8')+'\n'
 prompt+='【現在のテーマ】\n'+s['title']+'\n\n【操作の意味】\n'+json.dumps(OPS,ensure_ascii=False)+'\n\n【確実性の意味】\n'+json.dumps(EPI,ensure_ascii=False)+'\n\n【直前の発話】\nなし\n\n【今回の操作列】\n'+json.dumps(s['steps'],ensure_ascii=False)
 return prompt,dict(kind='stripe',steps=copy.deepcopy(s['steps']),history=[],source_quotes_sent=False,cpu_selected=True,preselected_before_surface=True,adaptive_reselection=False,style_fewshot=style)
def format_reason(body,eos):
 if not isinstance(body,str) or not body.strip():return 'empty'
 if not eos:return 'incomplete_stop_or_token_cap'
 if len(body)>6000:return 'excessive_length_over6000'
 if re.search(r'<[^>]+>|^\s*[\[{]|【|^\s*#{1,6}\s|\b(?:'+ '|'.join(OPS)+r'|L\d{2})\b',body):return 'markup_or_operation_leak'
 return None
