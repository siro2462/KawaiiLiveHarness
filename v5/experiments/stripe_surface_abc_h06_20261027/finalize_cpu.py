from common import *
import html,collections

def stats(seq):
 switches=sum(a!=b for a,b in zip(seq,seq[1:]));return dict(units=len(seq),switches=switches,switch_rate=switches/(len(seq)-1) if len(seq)>1 else None,counts={k:seq.count(k) for k in 'FET'})

def main():
 cfg=verify();audit=read(OUT/'technical_audit.json');assert audit['status']=='pass';p=read(OUT/'review_packet.json');review=read(OUT/'root_review.json');labels=read(OUT/'output_annotations.json');op=read(OUT/'operation_review.json');ph=sha(OUT/'review_packet.json')
 assert review['review_packet_sha256']==labels['review_packet_sha256']==op['review_packet_sha256']==ph==audit['review_packet_sha256']
 assert review['root_full_text_read'] is True and review['human_quality_labels']==0 and review['human_reference_full_text_read'] is True
 calls=[t for arm in p['arms'] for t in arm['turns']];ids=[t['row']['call_id'] for t in calls];assert review['reviewed_call_ids']==ids and len(review['per_turn'])==len(ids)
 for t,r in zip(calls,review['per_turn']):
  assert r['call_id']==t['row']['call_id'] and all(r.get(k) for k in ['operation_following','epistemic_preservation','fact_preservation','evaluation_development','repetition','naturalness','connection','quotes'])
  assert all(q in t['delivery']['body'] for q in r['quotes'])
 assert review['legacy_fact_review'] and review['cross_condition_comparison'] and review['limits'] and 'evaluation_updates' in review and 'unsupported_additions' in review
 label_map={r['call_id']:r['units'] for r in labels['calls']};assert set(label_map)==set(ids)
 for t in calls:
  us=t['units'];ls=label_map[t['row']['call_id']];assert len(us)==len(ls)
  for u,l in zip(us,ls):assert l['unit_index']==u['index'] and l['text']==u['text'] and l['primary'] in 'FET' and len(l['primary'])==1 and l['rationale']
 assert len(labels['human_units'])==len(p['human_units'])
 for u,l in zip(p['human_units'],labels['human_units']):assert l['unit_index']==u['index'] and l['text']==u['text'] and l['primary'] in 'FET' and len(l['primary'])==1 and l['rationale']
 operation_metrics={}
 for aid in ['B','C']:
  rs=op['arms'][aid];assert [r['index'] for r in rs]==list(range(1,33))
  arm=next(a for a in p['arms'] if a['arm']==aid);bodies={t['row']['call_id']:t['delivery']['body'] for t in arm['turns']}
  for r in rs:
   assert r['status'] in ['executed','partial','absent','uncertain'] and r['reason'] and r['epistemic_preserved'] in ['yes','no','uncertain'] and r['order_preserved'] in ['yes','no','uncertain'] and isinstance(r['operation_appropriate'],bool)
   if r['status']=='executed':assert r['evidence'] and r['epistemic_preserved']=='yes' and r['order_preserved']=='yes' and r['operation_appropriate']
   for e in r['evidence']:assert e['call_id'] in bodies and e['quote'] and e['quote'] in bodies[e['call_id']]
  counts=collections.Counter(r['status'] for r in rs);operation_metrics[aid]=dict(counts=dict(counts),executed_rate=counts['executed']/32,definition='root known-condition AI annotation; content/operation/order/epistemic all pass. Not independent human labels.')
 all_bodies={t['row']['call_id']:t['delivery']['body'] for t in calls}
 for event in review['evaluation_updates']+review['unsupported_additions']:
  assert event['call_id'] in all_bodies and event['quote'] in all_bodies[event['call_id']] and event['reason']
 summary=(OUT/'root_final_summary.md').read_text('utf-8-sig');assert summary.strip();esc=html.escape
 def pre(s):return '<pre>'+esc(s)+'</pre>'
 def coloured(units,ls):return ''.join('<span class="'+l['primary']+'" title="'+esc(l['rationale'],quote=True)+'">'+esc(u['text'])+'</span>' for u,l in zip(units,ls))
 page='<h1>固定32操作→Surface：A/B/C全文比較</h1><p>A＝従来の圧縮3Factを2回、B＝32操作を一括、C＝4操作ずつ8回。全て新規生成・同一LoRA/seed/1536token上限。B/Cは同じrenderer・同じ32操作。Aとの比較には情報量の差、B/Cには呼出数と実履歴の差がある。人間0・設計者AIの既知条件評価。</p><p>青＝事実F、黄＝感情E、黄緑＝考えT。実出力を句読点/改行で固定分割後、rootが内容からラベル付け。計画の色をコピーしない。1操作と1出力文と人間原文1行は同粒度ではない。</p><h2>予定された32操作</h2><div class="strip">'+''.join('<span class="'+s['kind']+'">'+str(s['index'])+'</span>' for s in p['steps'])+'</div>'+pre(json.dumps(p['steps'],ensure_ascii=False,indent=2))
 page+='<div class="grid"><article><h2>人間H06・参照原文</h2><div class="speech">'+coloured(p['human_units'],labels['human_units'])+'</div><details><summary>原文・元の42行ラベル・新しい単位ラベル全文</summary>'+pre(p['human_text'])+pre(json.dumps(p['human_reference'],ensure_ascii=False,indent=2))+pre(json.dumps(labels['human_units'],ensure_ascii=False,indent=2))+'</details></article>'
 metrics=[];texts=['人間H06\n'+p['human_text']]
 for arm in p['arms']:
  aid=arm['arm'];page+='<article><h2>条件'+aid+'</h2>';colorseq=[];armtexts=[]
  for t in arm['turns']:
   cid=t['row']['call_id'];ls=label_map[cid];colorseq.extend(l['primary'] for l in ls);armtexts.append(cid+'\n'+t['delivery']['body']);page+='<h3>'+esc(cid)+'</h3><div class="speech">'+coloured(t['units'],ls)+'</div>'+pre('採用='+str(t['row']['delivered'])+' / 形式保留='+str(t['row']['format_reason']))
   page+='<details><summary>実入力・履歴・RAW・本文・状態の全文</summary>'+pre(t['request']['user_prompt'])+pre(t['request']['decoded_input'])+pre(t['output']['raw_output'])+pre(t['delivery']['body'])+pre(json.dumps(t['request']['context'],ensure_ascii=False,indent=2))+pre(json.dumps(t['row'],ensure_ascii=False,indent=2))+'</details>'
  page+='</article>';texts.append('条件'+aid+'\n'+'\n\n'.join(armtexts))
  metrics.append(dict(arm=aid,calls=len(arm['turns']),delivered=sum(t['row']['delivered'] for t in arm['turns']),chars=sum(sum(not c.isspace() for c in t['delivery']['body']) for t in arm['turns'] if t['row']['delivered']),EOS=[t['output']['official_stop_reached'] for t in arm['turns']],model_seconds=sum(t['output']['seconds'] for t in arm['turns']),actual_output_stripe=stats(colorseq),operation_execution=operation_metrics.get(aid,'not assigned the32 operations'),evaluation_updates=sum(e['arm']==aid and e['counts_as_update'] for e in review['evaluation_updates']),unsupported_additions=sum(e['arm']==aid for e in review['unsupported_additions']),stop_reason=arm['stop_reason'],unattempted_groups=arm['unattempted_groups']))
 page+='</div><h2>計画・人間・実出力の指標</h2>'+pre(json.dumps(dict(plan=stats([s['kind'] for s in p['steps']]),human_original42=stats([h['dominant_color'] for h in p['human_reference']]),human_common_rule_units=stats([u['primary'] for u in labels['human_units']]),actual=metrics),ensure_ascii=False,indent=2))+'<h2>全操作の実行レビュー</h2>'+pre(json.dumps(op,ensure_ascii=False,indent=2))+'<h2>評価と限界</h2>'+pre(summary)+pre(json.dumps(review,ensure_ascii=False,indent=2))+'<details><summary>入力Memoryの全根拠と出典（評価用・原文引用はSurfaceへ未入力）</summary>'+pre(json.dumps(p['memory'],ensure_ascii=False,indent=2))+pre(json.dumps(p['legacy_memory'],ensure_ascii=False,indent=2))+'</details>'
 page='<!doctype html><html lang="ja"><meta charset="utf-8"><title>32操作 Surface A/B/C</title><style>body{font:16px/1.8 system-ui;max-width:1900px;margin:20px auto;padding:20px;background:#f6f8fa;color:#203040}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}article{background:white;border:1px solid #ccd6df;border-radius:10px;padding:16px}pre,.speech{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}.F{background:#a8d5fb}.E{background:#ffe190}.T{background:#c8efa2}.strip{display:flex;gap:3px;flex-wrap:wrap}.strip span{min-width:24px;text-align:center}details{margin:15px 0}summary{cursor:pointer;color:#17568f}@media(max-width:1200px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.grid{grid-template-columns:1fr}}</style>'+page+'</html>'
 for t in calls:assert all(esc(s) in page for s in [t['request']['user_prompt'],t['request']['decoded_input'],t['output']['raw_output'],t['delivery']['body']])
 for n,s in [('comparison.html',page),('result.md',summary),('full_comparison.txt','\n\n'.join(texts)+'\n')]: (OUT/n).write_text(s,encoding='utf-8')
 write(OUT/'report_check.json',dict(status='pass',conditions=3,human_reference=True,all_actual_input_RAW_body_present=True,metrics=metrics))
 write(OUT/'completion.json',dict(status='complete',technical_audit_sha256=sha(OUT/'technical_audit.json'),review_packet_sha256=ph,root_review_sha256=sha(OUT/'root_review.json'),annotations_sha256=sha(OUT/'output_annotations.json'),operation_review_sha256=sha(OUT/'operation_review.json'),comparison_sha256=sha(OUT/'comparison.html'),root_summary_sha256=sha(OUT/'root_final_summary.md'),metrics=metrics,human_quality_labels=0,designer_known_condition=True,finished_jst=now()))
 print(json.dumps(dict(status='complete',metrics=metrics),ensure_ascii=False))
if __name__=='__main__':main()
