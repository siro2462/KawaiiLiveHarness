from common import *
import html

TURN_FIELDS=['listener_address','self_question','direct_reaction','emotion_explanation','live_rhythm','operation_following','history_use','fact_preservation','epistemic_preservation','temporal_preservation','repetition','naturalness','unsupported_additions']
SAMPLE_FIELDS=TURN_FIELDS+['discourse','source_vs_generation','unselected_or_deferred','unit_length']


def main():
 verify();audit=read(OUT/'technical_audit.json');assert audit['status']=='pass'
 packet=read(OUT/'review_packet.json');review=read(OUT/'root_review.json');ann=read(OUT/'output_annotations.json')
 turns=[t for s in packet['samples'] for t in s['turns']];ids=[t['row']['call_id'] for t in turns]
 assert len(turns)==read(OUT/'protocol.json')['max_calls']
 assert review['review_packet_sha256']==sha(OUT/'review_packet.json') and review['root_full_text_read'] is True and review['human_quality_labels']==0 and review['limits']
 assert review['reviewed_call_ids']==ids and len(review['per_turn'])==len(turns) and len(review['per_sample'])==len(packet['samples'])==3
 annotations={x['call_id']:x for x in ann['samples']};assert set(annotations)==set(ids)
 reviews={x['call_id']:x for x in review['per_turn']};assert set(reviews)==set(ids)
 summary=(OUT/'root_final_summary.md').read_text('utf-8-sig');assert summary.strip()
 esc=html.escape
 def pre(x):return '<pre>'+esc(x if isinstance(x,str) else json.dumps(x,ensure_ascii=False,indent=2))+'</pre>'
 def colored(body,a):
  assert ''.join(x['text'] for x in a['spans'])==body and all(x['kind'] in ['F','E','T','N'] for x in a['spans'])
  return '<div class="speech">'+''.join(esc(x['text']) if x['kind']=='N' else '<span class="'+x['kind']+'">'+esc(x['text'])+'</span>' for x in a['spans'])+'</div>'
 page='<h1>新しい創作記憶3件：元記憶・CPU操作列・実Surface出力</h1><p>記憶はroot AIが手動作成した創作設定。操作と順番は既存CPU rhythm選択器が決定し、そのまま最大4操作ずつv2全文・短いFact/Flowへ渡した。採用した実本文を次のlast2/800履歴へ返す。列は生成前に固定し、意味を読んで再選択はしない。予定色と実本文色は別。実本文はrootの内容による手動分類で、真偽の保証ではない。</p>'+pre(summary)
 speech=[];full=[];metrics=[]
 for s,rv in zip(packet['samples'],review['per_sample']):
  sid=s['sample']['id'];assert rv['sample_id']==sid
  for field in SAMPLE_FIELDS:assert rv[field]
  all_body='\n'.join(t['delivery']['body'] for t in s['turns']);assert all(q in all_body for q in rv['quotes']) and (rv['quotes'] or not all_body.strip())
  source=pre(s['sample']['revision']['sources'])+pre(s['sample']['revision']['raw_document'])
  plan=pre(s['selection'])
  actual=''
  for t in s['turns']:
   row=t['row'];cid=row['call_id'];body=t['delivery']['body'];v=reviews[cid]
   assert (v['sample_id'],v['unit_index'])==(sid,row['unit_index'])
   for field in TURN_FIELDS:assert v[field]
   assert all(q in body for q in v['quotes']) and (v['quotes'] or not body.strip())
   actual+='<div class="turn"><p class="meta">'+esc(cid+' / 操作'+','.join(map(str,row['source_step_indices']))+' / '+str(row['format_reason'] or '形式採用・意味は別評価'))+'</p>'+colored(body,annotations[cid])+'</div>'
  page+='<section><h2>'+esc(sid+' '+s['sample']['title'])+'</h2><div class="grid"><article><h3>元の創作仕様・全記憶断片</h3>'+source+'</article><article><h3>CPU選択列・保留（全文）</h3>'+plan+'</article><article><h3>実出力・全試行</h3>'+actual+'</article></div>'
  page+='<details><summary>全投影データ・実入力・decoded・RAW・履歴・状態・引用評価</summary>'+pre(s['sample']['db_sample'])
  for t in s['turns']:
   page+=pre(t['request']['user_prompt'])+pre(t['request']['decoded_input'])+pre(t['output']['raw_output'])+pre(t['row'])+pre(reviews[t['row']['call_id']])
  page+=pre(rv)+'</details></section>'
  speech.append(sid+' '+s['sample']['title']+'\n【形式採用順の実本文】\n'+s['full_text'])
  full.append(speech[-1]+'\n【全試行・保留を含む】\n'+'\n'.join(t['row']['call_id']+' '+t['delivery']['body'] for t in s['turns'])+'\n【元記憶】\n'+json.dumps(s['sample']['revision']['raw_document'],ensure_ascii=False,indent=2)+'\n【創作仕様】\n'+json.dumps(s['sample']['revision']['sources'],ensure_ascii=False,indent=2)+'\n【CPU操作と保留】\n'+json.dumps(s['selection'],ensure_ascii=False,indent=2))
  metrics.append(dict(sample_id=sid,calls=len(s['turns']),operations=len(s['selection']['steps']),deferred=len(s['selection']['deferred_nodes']),body_chars=sum(not c.isspace() for c in s['full_text']),delivered=sum(t['row']['delivered'] for t in s['turns']),eos=sum(t['output']['official_stop_reached'] for t in s['turns']),output_tokens=sum(len(t['output']['output_ids']) for t in s['turns']),model_seconds=sum(t['output']['seconds'] for t in s['turns'])))
 page='<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>創作記憶3件のCPU選択と発話</title><style>body{font:16px/1.9 system-ui;max-width:1900px;margin:20px auto;padding:18px;background:#f4f6fa;color:#203040}.grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}article{min-width:0;background:white;border:1px solid #ccd7e5;border-radius:8px;padding:18px}pre,.speech{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}pre{font-size:13px}.speech{line-height:2.15}.F{background:#cde7ff}.E{background:#ffeaac}.T{background:#d6eebd}.speech span{box-decoration-break:clone;-webkit-box-decoration-break:clone;padding-block:2px}.turn{border-bottom:1px solid #e0e5ee;padding-bottom:12px;margin-bottom:12px}.meta{font-size:.82rem;color:#647185}details{margin:15px 0}summary{cursor:pointer}section{margin:35px 0}@media(max-width:1050px){.grid{grid-template-columns:1fr}}</style>'+page+'</html>'
 (OUT/'comparison.html').write_text(page,encoding='utf-8');(OUT/'result.md').write_text(summary,encoding='utf-8')
 (OUT/'speech.txt').write_text('\n\n'.join(speech)+'\n',encoding='utf-8');(OUT/'full_comparison.txt').write_text('\n\n'.join(full)+'\n',encoding='utf-8')
 from report_presence import check_report
 presence=check_report(OUT)
 write(OUT/'report_check.json',dict(status='pass',samples=3,all_bodies_colored_exact=len(turns),all_Memory_operations_inputs_RAW_present=True,metrics=metrics))
 write(OUT/'completion.json',dict(status='complete',review_packet_sha256=sha(OUT/'review_packet.json'),root_review_sha256=sha(OUT/'root_review.json'),annotations_sha256=sha(OUT/'output_annotations.json'),comparison_sha256=sha(OUT/'comparison.html'),report_check_sha256=sha(OUT/'report_check.json'),human_quality_labels=0,metrics=metrics,finished_jst=now()))
 print(json.dumps(dict(status='complete',samples=3,new_calls=len(turns)),ensure_ascii=False))
if __name__=='__main__':main()
