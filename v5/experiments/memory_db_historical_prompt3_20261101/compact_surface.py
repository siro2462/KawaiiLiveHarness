"""Model-facing presentation only. Source content/order and DB remain immutable."""
from common import *
import copy

HEADINGS=[('theme','現在のテーマ',True),('operations_legend','操作の意味',True),('epistemic_legend','確実性の意味',True),('history_text','直前の発話',False),('anchors','接続の参照・新たな操作ではない',True),('qualifiers','時点・確かさ・実行の区別',True),('limits','不明・守る範囲',True),('operations','今回の操作列',True)]
PREFIX=(OUT/'historical_prefix.txt').read_text('utf-8')

def short_id(value,by):
 if value is None:return None
 return by[value]['sidecar']['local_id']

def parts(sample,payload):
 by={n['id']:n for n in sample['db_sample']['nodes']}
 assert len({n['sidecar']['local_id'] for n in by.values()})==len(by)
 legend=read(OUT/'meaning_legend.json')
 ops=[]
 for op in payload['operations']:
  assert op['operation'] in legend['OPS'] and op['epistemic'] in legend['EPI']
  card={k:copy.deepcopy(op[k]) for k in ['index','memory_id','operation','kind','content','epistemic','relation','anchor_id']}
  card['memory_id']=short_id(op['memory_id'],by);card['anchor_id']=short_id(op['anchor_id'],by)
  assert card['content']==by[op['memory_id']]['content']
  ops.append(card)
 anchors=[dict(memory_id=short_id(r['memory_id'],by),content=r['content'],epistemic=r['epistemic']) for r in payload['previously_presented_reference']]
 ids=list(dict.fromkeys([o['memory_id'] for o in payload['operations']]+[r['memory_id'] for r in payload['previously_presented_reference']]))
 qualifiers=[]
 for mid in ids:
  node=by[mid];side=node['sidecar'];a=side['attributes'];q={'memory_id':short_id(mid,by)}
  for key in ['いつの望み・期待か','確かさ','状態']:
   if key in a:q[key]=copy.deepcopy(a[key])
  status=side['execution_status']
  if status=='desired':q['実行の区別']='本人の希望・期待。記載された時点の望みで、実行した出来事や実行中の状態にはしない。'
  elif status=='planned':q['実行の区別']='本人の方針・案。実行済みにはしない。'
  elif status not in ['unknown',None]:q['実行状態の元分類']=status
  if side['utterance_hint'] is not None:q['短い言い方の候補']=side['utterance_hint']
  if len(q)>1:qualifiers.append(q)
 worlds=sorted({by[mid]['sidecar']['world_scope'] for mid in ids})
 world={'fictional':'創作設定内の発話。現実の実体験という保証ではない。','real':'現実に関する資料。記憶に書かれた確実性の範囲を守る。'}
 return dict(theme=dict(話題=payload['title'],場面=payload['context'],話の中心=payload['central_theme'],世界=[world.get(w,'世界の区分は不明。新しく設定しない。') for w in worlds]),operations_legend=legend['OPS'],epistemic_legend=legend['EPI'],history_text='\n\n'.join(r['text'] for r in payload['history']) or 'なし',anchors=anchors,qualifiers=qualifiers,limits=dict(不明=payload['unknowns'],禁止=payload['prohibitions']),operations=ops)

def render(sample,payload):
 p=parts(sample,payload)
 prompt=PREFIX
 for i,(key,label,is_json) in enumerate(HEADINGS):
  value=json.dumps(p[key],ensure_ascii=False,separators=(',',':')) if is_json else p[key]
  prompt+=('' if i==0 else '\n')+'【'+label+'】\n'+value+'\n'
 assert all(x not in prompt for x in ['snapshot_','rev_','history_authority','generation_scope','source_inputs_sha256'])
 return prompt,p

def decoded_parts(text):
 result={}
 for i,(key,label,is_json) in enumerate(HEADINGS):
  marker='【'+label+'】\n'
  assert text.count(marker)==1
  value=text.split(marker,1)[1]
  if i+1<len(HEADINGS):value=value.split('【'+HEADINGS[i+1][1]+'】\n',1)[0]
  else:value=value.split('<turn|>',1)[0]
  result[key]=json.loads(value.strip()) if is_json else value.strip()
 return result
