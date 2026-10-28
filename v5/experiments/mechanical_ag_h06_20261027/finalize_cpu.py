from common import *
import html
FIELDS=['role_following','evaluation_development','fact_preservation','meaningful_repetition','expression_repetition','unsupported_additions','history_connection','mechanical_vs_semantic','quotes']

def main():
 cfg=verify();a=read(OUT/'technical_audit.json');assert a['status']=='pass';p=read(OUT/'review_packet.json');r=read(OUT/'root_review.json')
 assert r['review_packet_sha256']==sha(OUT/'review_packet.json')==a['review_packet_sha256']
 assert r['root_full_text_read'] is True and r['human_quality_labels']==0 and r['human_reference_full_text_read'] is True
 items=[t for arm in p['arms'] for t in arm['turns']];ids=[x['row']['call_id'] for x in items]
 assert r['reviewed_call_ids']==ids and len(r['per_turn'])==len(ids) and r['reviewed_arms']==list('ABCDEFG')
 assert r['baseline_review'] and r['cross_condition_comparison'] and r['limits'] and r['feature_activation_review']
 for x,y in zip(items,r['per_turn']):
  assert y['call_id']==x['row']['call_id'] and all(y.get(k) for k in FIELDS)
  assert all(q in x['delivery']['body'] for q in y['quotes'])
 summary=(OUT/'root_final_summary.md').read_text('utf-8-sig');assert summary.strip();esc=html.escape
 def pre(s):return '<pre>'+esc(s)+'</pre>'
 def details(x):return '<details><summary>実入力・履歴・RAW・状態の全文</summary>'+pre(x['request']['user_prompt'])+pre(x['request']['decoded_input'])+pre(x['output']['raw_output'])+pre(json.dumps(x['request']['context'],ensure_ascii=False,indent=2))+pre(json.dumps(x['row'],ensure_ascii=False,indent=2))+'</details>'
 page='<h1>H06：機械制御A〜G・全文比較</h1><p>同じ元Fact・同じ初期履歴・同じLoRA/seed/384token条件。A〜Gは機能を順に足す階段式比較。単独効果ではなく、設計者メタデータと実履歴の下流効果を含む。人間評価0・意味状態未検証。</p><div class="grid"><article><h2>現行版・保存済み2発話</h2>'
 baseline='\n\n'.join(x['delivery']['body'] for x in p['baseline']);full=['現行版（保存2件）\n'+baseline];page+=pre(baseline)
 for x in p['baseline']:
  page+='<details><summary>現行の実入力・RAW</summary>'+pre(x['request']['user_prompt'])+pre(x['request']['decoded_input'])+pre(x['output']['raw_output'])+'</details>'
 page+='</article>'
 metrics=[]
 for arm in p['arms']:
  spec=arm['arm'];page+='<article><h2>'+esc(spec['id']+' '+spec['label'])+'</h2>'+pre('追加済み機能：'+''.join(spec['features']));texts=[]
  for x in arm['turns']:
   label=x['row']['call_id']+' '+x['row']['choice']['view']['label'];page+='<h3>'+esc(label)+'</h3>'+pre(x['delivery']['body'])+pre('採用='+str(x['row']['delivered'])+' / 保留='+str(x['row']['format_reason']))+details(x);texts.append(label+'\n'+x['delivery']['body'])
  page+='<details><summary>最終状態と終了理由</summary>'+pre(json.dumps(arm['final_control'],ensure_ascii=False,indent=2))+'</details></article>';full.append(spec['id']+' '+spec['label']+'\n'+'\n\n'.join(texts))
  metrics.append(dict(arm=spec['id'],calls=len(arm['turns']),delivered=sum(x['row']['delivered'] for x in arm['turns']),chars=sum(sum(not c.isspace() for c in x['delivery']['body']) for x in arm['turns'] if x['row']['delivered']),stop_reason=arm['final_control']['stop_reason']))
 page+='</div><h2>評価と限界</h2>'+pre(summary)+pre(json.dumps(r,ensure_ascii=False,indent=2))
 for ref in p['references']:page+='<details><summary>人間原文・逆算Memory（評価用）</summary>'+pre(ref['human_text'])+pre(ref['memory'])+'</details>'
 page='<!doctype html><html lang="ja"><meta charset="utf-8"><title>H06機械制御A-G</title><style>body{font:16px/1.8 system-ui;max-width:1800px;margin:24px auto;padding:20px;background:#f5f7fa;color:#203040}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}article{background:white;border:1px solid #ccd6e2;border-radius:8px;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}summary{cursor:pointer;color:#17568f}@media(max-width:900px){.grid{grid-template-columns:1fr}}</style>'+page+'</html>'
 for x in items+p['baseline']:
  assert all(esc(s) in page for s in [x['delivery']['body'],x['request']['user_prompt'],x['request']['decoded_input'],x['output']['raw_output']])
 (OUT/'comparison.html').write_text(page,encoding='utf-8');(OUT/'result.md').write_text(summary,encoding='utf-8');(OUT/'full_comparison.txt').write_text('\n\n'.join(full)+'\n',encoding='utf-8')
 write(OUT/'report_check.json',dict(status='pass',conditions=8,all_actual_text_and_raw_present=True,metrics=metrics))
 write(OUT/'completion.json',dict(status='complete',technical_audit_sha256=sha(OUT/'technical_audit.json'),review_packet_sha256=sha(OUT/'review_packet.json'),root_review_sha256=sha(OUT/'root_review.json'),root_summary_sha256=sha(OUT/'root_final_summary.md'),comparison_sha256=sha(OUT/'comparison.html'),metrics=metrics,human_quality_labels=0,known_condition_designer_review=True,semantic_guard_calls=0,training=0,quality_retries=0,real_tts=False,finished_jst=now()))
 print(json.dumps(dict(status='complete',metrics=metrics),ensure_ascii=False))
if __name__=='__main__':main()
