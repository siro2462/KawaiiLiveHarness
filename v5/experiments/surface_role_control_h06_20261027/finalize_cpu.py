from common import *
import html
FIELDS=['role_following','evaluation_development','fact_preservation','meaningful_repetition','expression_repetition','unsupported_additions','history_connection','literal_tracking_vs_meaning','quotes']

def main():
 verify();a=read(OUT/'technical_audit.json');assert a['status']=='pass';p=read(OUT/'review_packet.json');r=read(OUT/'root_review.json')
 assert r['review_packet_sha256']==sha(OUT/'review_packet.json')==a['review_packet_sha256']
 assert r['root_full_text_read'] is True and r['human_quality_labels']==0 and r['common_first_full_text_read'] is True and r['human_reference_full_text_read'] is True
 ids=[x['row']['call_id'] for x in p['controlled_turns']];assert r['reviewed_call_ids']==ids and len(r['per_turn'])==len(ids)
 assert r['baseline_review'] and r['cross_condition_comparison'] and r['limits']
 for x,y in zip(p['controlled_turns'],r['per_turn']):
  assert y['call_id']==x['row']['call_id'] and all(y.get(k) for k in FIELDS)
  assert y['quotes'] and all(q in x['delivery']['body'] for q in y['quotes'])
 summary=(OUT/'root_final_summary.md').read_text('utf-8-sig');assert summary.strip()
 esc=html.escape
 def pre(s):return '<pre>'+esc(s)+'</pre>'
 def details(x):return '<details><summary>実入力・履歴・テンプレート適用後・RAW・条件全文</summary>'+pre(x['request']['user_prompt'])+pre(x['request']['decoded_input'])+pre(x['output']['raw_output'])+pre(json.dumps(x['request']['context'],ensure_ascii=False,indent=2))+pre(json.dumps(x['output']['generation_config'],ensure_ascii=False,indent=2))+'</details>'
 base=p['baseline'];first=p['common_first'];turns=p['controlled_turns'];delivered=[x for x in turns if x['row']['delivered']]
 body='<h1>H06：役割・角度の観測・終了を制御する比較</h1><p>現行は元contract_runtimeの保存出力。新条件は役割を1つずつ指定し、実発話を次の履歴へ戻す最大2回の制御。LoRA/元Fact/初期履歴/seed/生成条件固定。役割指定と入力の組立・回数/終了の複合変更で、個別寄与は未分離。角度は設計者指定、観測は文字ルールで意味検証ではない。</p>'
 body+='<h2>共通前半（保存済み）</h2>'+pre(first['delivery']['body'])+details(first)
 body+='<div class="grid"><article><h2>現行版・後半</h2>'+pre(base['delivery']['body'])+details(base)+'</article><article><h2>役割制御版・後半の全発話</h2>'
 for x in turns:body+='<h3>'+esc(x['row']['call_id']+' '+x['row']['role_spec']['label'])+'</h3>'+pre(x['delivery']['body'])+pre('履歴採用='+str(x['row']['delivered'])+' / 形式保留='+str(x['row']['format_reason']))+details(x)
 body+='</article></div><h2>役割・角度の文字観測・終了の全記録</h2>'+pre(json.dumps(p['final_control'],ensure_ascii=False,indent=2))
 body+='<h2>全文評価</h2>'+pre(json.dumps(r,ensure_ascii=False,indent=2))+'<h2>結果と限界</h2>'+pre(summary)
 for ref in p['references']:body+='<details><summary>人間原文と既存逆算Memory（生成へ渡さない参照）</summary>'+pre(ref['human_text'])+pre(ref['memory'])+'</details>'
 page='<!doctype html><html lang="ja"><meta charset="utf-8"><title>H06 役割制御比較</title><style>body{font:16px/1.8 system-ui,sans-serif;max-width:1500px;margin:24px auto;padding:20px;background:#f5f7fa;color:#203040}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}article{background:white;border:1px solid #d5dce5;border-radius:10px;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}details{margin:18px 0}summary{cursor:pointer;color:#17568f}@media(max-width:900px){.grid{grid-template-columns:1fr}}</style>'+body+'</html>'
 (OUT/'comparison.html').write_text(page,encoding='utf-8');(OUT/'result.md').write_text(summary,encoding='utf-8')
 text='共通前半（保存）\n'+first['delivery']['body']+'\n\n現行後半（保存）\n'+base['delivery']['body']+'\n\n役割制御版（全候補）\n'+'\n\n'.join(x['row']['call_id']+' '+x['row']['role_spec']['label']+'\n'+x['delivery']['body'] for x in turns)
 (OUT/'full_comparison.txt').write_text(text,encoding='utf-8');(OUT/'speech.txt').write_text('\n\n'.join(x['delivery']['body'] for x in delivered)+'\n',encoding='utf-8')
 for x in [first,base]+turns:
  assert all(esc(s) in page for s in [x['delivery']['body'],x['request']['user_prompt'],x['request']['decoded_input'],x['output']['raw_output']])
 metrics=dict(baseline_chars=sum(not c.isspace() for c in base['delivery']['body']),controlled_delivered_chars=sum(sum(not c.isspace() for c in x['delivery']['body']) for x in delivered),new_surface_calls=len(turns),delivered=len(delivered),stop_reason=p['final_control']['stop_reason'],model_seconds=sum(x['output']['seconds'] for x in turns))
 write(OUT/'report_check.json',dict(status='pass',columns=2,all_actual_text_and_raw_present=True,metrics=metrics))
 write(OUT/'completion.json',dict(status='complete',technical_audit_sha256=sha(OUT/'technical_audit.json'),review_packet_sha256=sha(OUT/'review_packet.json'),root_review_sha256=sha(OUT/'root_review.json'),root_summary_sha256=sha(OUT/'root_final_summary.md'),comparison_sha256=sha(OUT/'comparison.html'),full_text_sha256=sha(OUT/'full_comparison.txt'),metrics=metrics,human_quality_labels=0,known_condition_designer_review=True,semantic_guard_calls=0,training=0,quality_retries=0,real_tts=False,finished_jst=now()))
 print(json.dumps(dict(status='complete',metrics=metrics),ensure_ascii=False))
if __name__=='__main__':main()
