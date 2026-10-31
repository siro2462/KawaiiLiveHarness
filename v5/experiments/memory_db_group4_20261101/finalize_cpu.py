from common import *
import html

def main():
 verify();assert read(OUT/'technical_audit.json')['status']=='pass'
 packet=read(OUT/'review_packet.json');review=read(OUT/'root_review.json');ann=read(OUT/'output_annotations.json');oldann=read(OUT/'baseline_annotations.json')
 oldturns=[t for s in packet['samples'] for t in s['baseline']['turns']]
 newturns=[t for s in packet['samples'] for t in s['turns']]
 assert len(oldturns)==40 and len(newturns)==11
 assert review['review_packet_sha256']==sha(OUT/'review_packet.json') and review['root_full_text_read'] is True and review['human_quality_labels']==0 and review['limits']
 assert review['reviewed_call_ids']==[t['row']['call_id'] for t in newturns] and review['reviewed_baseline_call_ids']==[t['row']['call_id'] for t in oldturns]
 assert len(review['per_turn'])==11 and len(review['per_sample'])==3
 newmap={x['call_id']:x for x in ann['samples']};oldmap={x['call_id']:x for x in oldann['samples']}
 assert len(newmap)==11 and len(oldmap)==40
 summary=(OUT/'root_final_summary.md').read_text('utf-8-sig');assert summary.strip()
 esc=html.escape
 def pre(x):return '<pre>'+esc(x if isinstance(x,str) else json.dumps(x,ensure_ascii=False,indent=2))+'</pre>'
 def colored(body,a):
  assert ''.join(x['text'] for x in a['spans'])==body and all(x['kind'] in ['F','E','T','N'] for x in a['spans'])
  return '<div class="speech">'+''.join(esc(x['text']) if x['kind']=='N' else '<span class="'+x['kind']+'">'+esc(x['text'])+'</span>' for x in a['spans'])+'</div>'
 page='<h1>同じCPU40操作：1操作ずつ vs 4操作ずつ</h1><p>同一LoRA・Memory・CPU順序・口語few-shot・初期空履歴・seed・1536token等の生成条件。Aは保存40call、Bだけ新規11call。残り2操作は2操作で生成。固定列の分割実現で、意味による操作再選択ではない。</p><p><span class="F">青：事実としての説明</span> <span class="E">黄：感情・反応・好み・願い</span> <span class="T">黄緑：考え・評価・疑問・方針</span>。実本文から手動分類、青は真偽の保証ではない。人間0/実TTS0。</p>'+pre(summary)
 reviews={v['call_id']:v for v in review['per_turn']};speech=[];full=[];metrics=[]
 for s,v in zip(packet['samples'],review['per_sample']):
  sid=s['sample']['id'];assert v['sample_id']==sid
  for field in ['unit_length','oral_style','repetition','fact_preservation','epistemic_preservation','operation_following','discourse','naturalness','unsupported_additions']:assert v[field]
  base_text=s['baseline']['full_text']
  assert v['quotes_baseline'] and all(q in base_text for q in v['quotes_baseline'])
  sides=[]
  for turns,mapping,is_new in [(s['baseline']['turns'],oldmap,False),(s['turns'],newmap,True)]:
   side=''
   for t in turns:
    row=t['row'];cid=row['call_id'];body=t['delivery']['body']
    side+='<div class="turn"><p class="meta">'+esc(cid+' / '+('操作'+','.join(map(str,row['source_step_indices'])) if is_new else '操作'+str(row['unit_index'])))+' / '+esc(str(row['format_reason'] or '形式採用・意味未確認'))+'</p>'+colored(body,mapping[cid])+'</div>'
    if is_new:
     rv=reviews[cid];assert (rv['sample_id'],rv['unit_index'])==(sid,row['unit_index'])
     for field in ['operation_following','history_use','fact_preservation','epistemic_preservation','repetition','naturalness','unsupported_additions']:assert rv[field]
     assert all(q in body for q in rv['quotes']) and (rv['quotes'] or not body.strip())
   sides.append(side)
  page+='<section><h2>'+esc(sid+' '+s['sample']['title'])+'</h2><div class="grid"><article><h3>前回：1操作ずつ</h3>'+sides[0]+'</article><article><h3>今回：4操作ずつ（区切りが1call）</h3>'+sides[1]+'</article></div><details><summary>元Memory・全操作・保留・旧新全実入力RAW・状態・引用評価</summary>'+pre(s['sample']['revision']['raw_document'])+pre(s['selection'])
  for label,turns in [('A saved one-operation',s['baseline']['turns']),('B new group4',s['turns'])]:
   page+='<h3>'+label+'</h3>'
   for t in turns:page+=pre(t['request']['user_prompt'])+pre(t['request']['decoded_input'])+pre(t['output']['raw_output'])+pre(t['row'])
  for t in s['turns']:page+=pre(reviews[t['row']['call_id']])
  page+=pre(v)+'</details></section>'
  speech.append(sid+' '+s['sample']['title']+'\n【前回：1操作ずつ】\n'+base_text+'\n【今回：4操作ずつ・採用順全文】\n'+s['full_text'])
  full.append(speech[-1]+'\n【今回全試行：保留も含む】\n'+'\n'.join(t['row']['call_id']+' '+t['delivery']['body'] for t in s['turns'])+'\n【元Memory】\n'+json.dumps(s['sample']['revision']['raw_document'],ensure_ascii=False,indent=2)+'\n【CPU操作と保留】\n'+json.dumps(s['selection'],ensure_ascii=False,indent=2))
  metrics.append(dict(sample_id=sid,baseline_calls=len(s['baseline']['turns']),new_calls=len(s['turns']),baseline_chars=sum(not c.isspace() for c in base_text),new_chars=sum(not c.isspace() for c in s['full_text']),delivered=sum(t['row']['delivered'] for t in s['turns']),eos=sum(t['output']['official_stop_reached'] for t in s['turns']),output_tokens=sum(len(t['output']['output_ids']) for t in s['turns']),model_seconds=sum(t['output']['seconds'] for t in s['turns'])))
 page='<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>4操作ずつの発話・3件比較</title><style>body{font:16px/1.9 system-ui;max-width:1650px;margin:20px auto;padding:18px;background:#f4f6fa;color:#203040}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}article{min-width:0;background:white;border:1px solid #ccd7e5;border-radius:8px;padding:20px}pre,.speech{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}.speech{line-height:2.15}.F{background:#cde7ff}.E{background:#ffeaac}.T{background:#d6eebd}.speech span{box-decoration-break:clone;-webkit-box-decoration-break:clone;padding-block:2px}.turn{border-bottom:1px solid #e0e5ee;padding-bottom:12px;margin-bottom:12px}.meta{font-size:.82rem;color:#647185}details{margin:15px 0}summary{cursor:pointer}section{margin:35px 0}@media(max-width:950px){.grid{grid-template-columns:1fr}}</style>'+page+'</html>'
 for s in packet['samples']:
  for t in s['baseline']['turns']+s['turns']:assert all(esc(x) in page for x in [t['request']['user_prompt'],t['request']['decoded_input'],t['output']['raw_output']])
 (OUT/'comparison.html').write_text(page,encoding='utf-8');(OUT/'result.md').write_text(summary,encoding='utf-8')
 (OUT/'speech.txt').write_text('\n\n'.join(speech)+'\n',encoding='utf-8');(OUT/'full_comparison.txt').write_text('\n\n'.join(full)+'\n',encoding='utf-8')
 write(OUT/'report_check.json',dict(status='pass',pairs=3,all51_bodies_colored_exact=True,all_Memory_operations_inputs_RAW_present=True,metrics=metrics))
 write(OUT/'completion.json',dict(status='complete',review_packet_sha256=sha(OUT/'review_packet.json'),root_review_sha256=sha(OUT/'root_review.json'),annotations_sha256=sha(OUT/'output_annotations.json'),comparison_sha256=sha(OUT/'comparison.html'),report_check_sha256=sha(OUT/'report_check.json'),human_quality_labels=0,metrics=metrics,finished_jst=now()))
 print(json.dumps(dict(status='complete',pairs=3,new_calls=11,saved_calls=40),ensure_ascii=False))
if __name__=='__main__':main()
