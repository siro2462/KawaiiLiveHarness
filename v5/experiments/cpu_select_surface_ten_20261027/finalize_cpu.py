from common import *
import html,collections
def main():
 verify();audit=read(OUT/'technical_audit.json');assert audit['status']=='pass';p=read(OUT/'review_packet.json');r=read(OUT/'root_review.json');labels=read(OUT/'output_annotations.json');ph=sha(OUT/'review_packet.json')
 assert ph==audit['review_packet_sha256']==r['review_packet_sha256']==labels['review_packet_sha256']
 assert r['root_full_text_read'] is True and r['human_quality_labels']==labels['human_quality_labels']==0
 ts=p['samples'];assert r['reviewed_call_ids']==[t['row']['call_id'] for t in ts] and len(r['per_sample'])==10
 lm={x['call_id']:x['units'] for x in labels['calls']};oldlm={x['call_id']:x['units'] for x in read(OUT/'reference/baseline/output_annotations.json')['calls']}
 summary=(OUT/'root_final_summary.md').read_text('utf-8-sig');assert summary.strip() and r['limits'];esc=html.escape
 def pre(x):return '<pre>'+esc(x)+'</pre>'
 def coloured(us,ls):
  assert len(us)==len(ls)
  for u,l in zip(us,ls):assert u['text']==l['text'] and u['index']==l['unit_index'] and l['primary'] in 'FET' and l['rationale']
  return ''.join('<span class="'+l['primary']+'" title="'+esc(l['rationale'],quote=True)+'">'+esc(u['text'])+'</span>' for u,l in zip(us,ls))
 page='<h1>前回の手作業32操作 vs CPU選択＋短い直接反応</h1><p>同じLoRA/Memory/生成条件。H06 Engineのbytesは同一。ただし新Memoryには元々関係等がなく、共通の文字一致規則でCPU補助情報を追加。選択方式とfew-shotを同時変更した合成比較。1seed/人間0/実TTS0/独立素材。実発話を受けた適応的再選択ではない。</p>'+pre(summary)
 texts=[];full=[];metrics=[]
 for t,v in zip(ts,r['per_sample']):
  sid=t['sample']['id'];cid=t['row']['call_id'];old=t['baseline'];b=t['delivery']['body'];assert v['sample_id']==sid and v['call_id']==cid
  for k in ['operation_following','fact_preservation','epistemic_preservation','evaluation_development','repetition','naturalness','unsupported_additions','connection','direct_emotion_review','selector_review']:assert v[k]
  assert all(q in b for q in v['quotes']) and (v['quotes'] or not b.strip())
  oldtext=old['delivery']['body'];oldcolor=coloured(old['units'],oldlm[old['row']['call_id']]);newcolor=coloured(t['units'],lm[cid])
  page+='<h2>'+esc(sid+' '+t['sample']['title'])+'</h2><div class="grid"><article><h3>前回：手作業32操作・元prompt</h3><div class="speech">'+oldcolor+'</div></article><article><h3>今回：CPU選択・直接反応few-shot</h3><div class="speech">'+newcolor+'</div></article></div><details><summary>Memory・原文・CPU全候補score/選択・前回/今回の全実入力decoded/RAW・評価</summary>'+pre(json.dumps(t['sample'],ensure_ascii=False,indent=2))+pre(json.dumps(t['selection'],ensure_ascii=False,indent=2))+pre(old['request']['user_prompt'])+pre(old['request']['decoded_input'])+pre(old['output']['raw_output'])+pre(t['request']['user_prompt'])+pre(t['request']['decoded_input'])+pre(t['output']['raw_output'])+pre(json.dumps(v,ensure_ascii=False,indent=2))+'</details>'
  texts.append(sid+' '+t['sample']['title']+'\n'+b);full.append(sid+'\n【前回】\n'+oldtext+'\n【今回】\n'+b)
  seq=[x['primary'] for x in lm[cid]];metrics.append(dict(sample_id=sid,old_chars=sum(not c.isspace() for c in oldtext),chars=sum(not c.isspace() for c in b),operations=len(t['sample']['steps']),unique_nodes=len({x['memory_id'] for x in t['sample']['steps']}),delivered=t['row']['delivered'],eos=t['output']['official_stop_reached'],output_tokens=len(t['output']['output_ids']),model_seconds=t['output']['seconds'],FET_counts=dict(collections.Counter(seq))))
 for t in ts:
  for a in [t,t['baseline']]:assert all(esc(x) in page for x in [a['request']['user_prompt'],a['request']['decoded_input'],a['output']['raw_output'],a['delivery']['body']])
 page='<!doctype html><html lang="ja"><meta charset="utf-8"><title>CPU選択10素材</title><style>body{font:16px/1.8 system-ui;max-width:1500px;margin:20px auto;padding:20px;background:#f6f8fa;color:#203040}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}article{background:white;border:1px solid #ccd;padding:18px;border-radius:10px}pre,.speech{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}.F{background:#a8d5fb}.E{background:#ffe190}.T{background:#c8efa2}details{margin:16px 0}summary{cursor:pointer;color:#17568f}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style>'+page+'</html>'
 (OUT/'comparison.html').write_text(page,encoding='utf-8');(OUT/'result.md').write_text(summary,encoding='utf-8');(OUT/'speech.txt').write_text('\n\n'.join(texts)+'\n',encoding='utf-8');(OUT/'full_comparison.txt').write_text('\n\n'.join(full)+'\n',encoding='utf-8')
 write(OUT/'report_check.json',dict(status='pass',pairs=10,all_old_new_actual_input_RAW_body_present=True,metrics=metrics))
 write(OUT/'completion.json',dict(status='complete',review_packet_sha256=ph,review_sha256=sha(OUT/'root_review.json'),labels_sha256=sha(OUT/'output_annotations.json'),comparison_sha256=sha(OUT/'comparison.html'),technical_audit_sha256=sha(OUT/'technical_audit.json'),finished_jst=now(),metrics=metrics,human_quality_labels=0))
 print(json.dumps(dict(status='complete',metrics=metrics),ensure_ascii=False))
if __name__=='__main__':main()
