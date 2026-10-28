from common import *
import html,collections

def main():
 cfg=verify();audit=read(OUT/'technical_audit.json');assert audit['status']=='pass';packet=read(OUT/'review_packet.json');review=read(OUT/'root_review.json');labels=read(OUT/'output_annotations.json');ph=sha(OUT/'review_packet.json')
 assert review['review_packet_sha256']==labels['review_packet_sha256']==ph==audit['review_packet_sha256']
 assert review['root_full_text_read'] is True and review['human_quality_labels']==labels['human_quality_labels']==0
 ps=packet['samples'];ids=[t['row']['call_id'] for t in ps];assert review['reviewed_call_ids']==ids and len(review['per_sample'])==10
 labelmap={x['call_id']:x['units'] for x in labels['calls']};assert set(labelmap)==set(ids)
 summary=(OUT/'root_final_summary.md').read_text('utf-8-sig');assert summary.strip() and review['limits']
 esc=html.escape
 def pre(s):return '<pre>'+esc(s)+'</pre>'
 page='<h1>32操作→Surface・10素材</h1><p>VTuber保存編集原文5件（同じ配信者）＋設計者AIの創作Memory5件。各32操作を一括、同一LoRA/seed/1536token、全10件独立の空履歴。操作列は手作業固定で、記憶/操作の自動選択能力は未評価。人間品質ラベル0、実TTSなし。</p><p>実出力だけをrootが内容からF青/E黄/T黄緑へ分類。計画色の転写ではない。混在文の主分類であり率だけで自然さを判定しない。</p>'+pre(summary)
 metrics=[];texts=[]
 for t,r in zip(ps,review['per_sample']):
  s=t['sample'];cid=t['row']['call_id'];body=t['delivery']['body'];assert r['call_id']==cid and r['sample_id']==s['id']
  for key in ['operation_following','fact_preservation','epistemic_preservation','evaluation_development','repetition','naturalness','unsupported_additions','connection']:assert r.get(key)
  assert r['quotes'] or not body.strip();assert all(q in body for q in r['quotes'])
  us=t['units'];ls=labelmap[cid];assert len(us)==len(ls)
  for u,l in zip(us,ls):assert l['unit_index']==u['index'] and l['text']==u['text'] and l['primary'] in ['F','E','T'] and l['rationale']
  coloured=''.join('<span class="'+l['primary']+'" title="'+esc(l['rationale'],quote=True)+'">'+esc(u['text'])+'</span>' for u,l in zip(us,ls))
  page+='<h2>'+esc(s['id']+' '+s['title'])+'</h2><div class="grid"><article><h3>'+('保存編集原文' if s['id'].startswith('V') else '設計者作成の架空Memory・人間発話ではない')+'</h3>'+pre(s['provenance']['source_text'])+'</article><article><h3>実モデル出力 '+cid+'</h3><div class="speech">'+coloured+'</div>'+pre(json.dumps(dict(delivered=t['row']['delivered'],format_reason=t['row']['format_reason']),ensure_ascii=False))+'</article></div><details><summary>32操作と根拠・実入力decoded/RAW・全文評価</summary>'+pre(json.dumps(s,ensure_ascii=False,indent=2))+pre(t['request']['user_prompt'])+pre(t['request']['decoded_input'])+pre(t['output']['raw_output'])+pre(json.dumps(t['row'],ensure_ascii=False,indent=2))+pre(json.dumps(r,ensure_ascii=False,indent=2))+'</details>'
  texts.append(s['id']+' '+s['title']+'\n'+body)
  seq=[l['primary'] for l in ls];metrics.append(dict(sample_id=s['id'],call_id=cid,delivered=t['row']['delivered'],chars=sum(not c.isspace() for c in body),output_tokens=len(t['output']['output_ids']),eos=t['output']['official_stop_reached'],model_seconds=t['output']['seconds'],FET_counts=dict(collections.Counter(seq)),units=len(seq),switches=sum(a!=b for a,b in zip(seq,seq[1:]))))
 page='<!doctype html><html lang="ja"><meta charset="utf-8"><title>Surface10素材</title><style>body{font:16px/1.8 system-ui;max-width:1500px;margin:20px auto;padding:20px;background:#f6f8fa;color:#203040}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}article{background:white;border:1px solid #ccd;padding:18px;border-radius:10px}pre,.speech{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}.F{background:#a8d5fb}.E{background:#ffe190}.T{background:#c8efa2}details{margin:16px 0}summary{cursor:pointer;color:#17568f}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style>'+page+'</html>'
 for t in ps:assert all(esc(x) in page for x in [t['request']['user_prompt'],t['request']['decoded_input'],t['output']['raw_output'],t['delivery']['body']])
 (OUT/'comparison.html').write_text(page,encoding='utf-8');(OUT/'result.md').write_text(summary,encoding='utf-8');(OUT/'speech.txt').write_text('\n\n'.join(texts)+'\n',encoding='utf-8')
 write(OUT/'report_check.json',dict(status='pass',samples=10,all_source_input_RAW_body_present=True,actual_FET_labels=True,metrics=metrics))
 write(OUT/'completion.json',dict(status='complete',review_packet_sha256=ph,technical_audit_sha256=sha(OUT/'technical_audit.json'),review_sha256=sha(OUT/'root_review.json'),labels_sha256=sha(OUT/'output_annotations.json'),summary_sha256=sha(OUT/'root_final_summary.md'),comparison_sha256=sha(OUT/'comparison.html'),metrics=metrics,human_quality_labels=0,finished_jst=now()))
 print(json.dumps(dict(status='complete',metrics=metrics),ensure_ascii=False))
if __name__=='__main__':main()
