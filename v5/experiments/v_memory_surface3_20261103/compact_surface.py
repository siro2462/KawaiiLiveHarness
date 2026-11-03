"""Presentation adapter: immutable DB payload -> original v2 Fact/Flow sections."""
from common import *
from baseline_compact import parts as source_parts
from prompt_v2 import render as v2_render,TEMPLATE
from contract_runtime import validate
import copy

SECTIONS=[('history','直前の発話'),('operation','今回の会話操作'),('relation_summary','話題の関係'),('facts','今回話す内容'),('flow','話の展開')]
RELATIONS={'continuity_only_not_causal':'話のつながりのみ。因果関係を追加しない','explicit_reaction':'参照内容への反応','explicit_appraisal':'参照内容への評価','explicit_about':'参照内容について考える','return_after_new_evaluation_not_new_fact':'新しい評価を経て既出内容へ戻る。新たな出来事ではない'}

def value_text(v):
 return v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,separators=(',',':'))

def case_for(sample,payload):
 p=source_parts(sample,payload);legend=read(OUT/'meaning_legend.json');qby={q['memory_id']:q for q in p['qualifiers']}
 facts=[];flow=[]
 for op in p['operations']:
  fid=f"{sample['id']}-{op['index']:02}-{op['memory_id']}";q=qby.get(op['memory_id'],{})
  claim=op['content']+'\n確実性：'+legend['EPI'][op['epistemic']]
  for k,v in q.items():
   if k!='memory_id':claim+='\n'+k+'：'+value_text(v)
  kind={'F':'event','E':'emotion','T':'judgment'}[op['kind']]
  if op['epistemic']=='uncertain_memory':kind='uncertain'
  elif op['epistemic']=='counterfactual':kind='hypothetical'
  elif op['epistemic']=='speaker_desire':kind='intent'
  facts.append(dict(id=fid,claim=claim,kind=kind))
  rel=RELATIONS.get(op['relation'],'関係の元分類：'+op['relation'])
  label=legend['OPS'][op['operation']]+'／'+rel
  if op['anchor_id'] is not None:label+='／参照 '+op['anchor_id']
  flow.append(dict(fact_ids=[fid],relation='sequence',label=label))
 theme=p['theme'];lines=['話題：'+value_text(theme['話題']),'場面：'+'、'.join(k+'='+value_text(v) for k,v in theme['場面'].items()),'話の中心：'+value_text(theme['話の中心'])]
 lines+=['世界：'+value_text(x) for x in theme['世界']]
 lines+=['不明：'+value_text(x) for x in p['limits']['不明']]+['禁止：'+value_text(x) for x in p['limits']['禁止']]
 for a in p['anchors']:
  lines.append('既提示参照 '+a['memory_id']+'：'+a['content']+'（'+legend['EPI'][a['epistemic']]+'）。再提示を保証するものではない。')
  for k,v in qby.get(a['memory_id'],{}).items():
   if k!='memory_id':lines.append('参照 '+a['memory_id']+' '+k+'：'+value_text(v))
 lines.append('順序は発話順。出来事の時系列を新たに決めない。参照は接続用で、未検証履歴を新事実の根拠にしない。')
 history=[dict(text=h['text']) for h in payload['history']]
 row=dict(schema='surface-contract-1',pair_id=sample['id']+':G'+str(payload['generation_scope']['unit_index']),facts=facts,history=history,operation='continue' if payload['generation_scope']['unit_index']>1 else 'start',relation=dict(type='sequence' if history else 'none',summary='\n'.join(lines)),flow=flow)
 return validate(row)

def parts(sample,payload):
 row=case_for(sample,payload)
 return dict(history='\n\n'.join(f'[{i+1}] {x["text"]}' for i,x in enumerate(row['history'])) or 'なし',operation='同じ出来事の続きを話す' if row['operation']=='continue' else '話を始める',relation_summary=row['relation']['summary'],facts='\n'.join(f'[{f["id"]}] {f["claim"]}' for f in row['facts']),flow=' → '.join(f'{s["label"]}（{", ".join(s["fact_ids"])}）' for s in row['flow']))

def render(sample,payload,style,instruction):
 # style/instruction are archived baseline inputs, deliberately not appended to v2.
 row=case_for(sample,payload);prompt=v2_render(row);return prompt,parts(sample,payload)

def decoded_parts(text):
 result={}
 for i,(key,label) in enumerate(SECTIONS):
  marker='【'+label+'】\n\n';assert text.count(marker)==1
  value=text.split(marker,1)[1]
  if i+1<len(SECTIONS):value=value.split('【'+SECTIONS[i+1][1]+'】\n\n',1)[0]
  else:value=value.split('<turn|>',1)[0]
  result[key]=value.strip()
 return result
