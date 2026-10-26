from common import *
import html
FIELDS=['narrative_focus','evaluation_development','fact_preservation','emotional_strength','thought_development','meaningful_repetition','expression_repetition','listener_address','naturalness','unsupported_additions','history_connection','quotes']
def main():
 verify();audit=read(OUT/'technical_audit.json');assert audit['status']=='pass'
 packet=read(OUT/'review_packet.json');review=read(OUT/'root_review.json')
 assert review['review_packet_sha256']==sha(OUT/'review_packet.json')==audit['review_packet_sha256']
 assert review['root_full_text_read'] is True and review['human_quality_labels']==0
 assert review['reviewed_pair_ids']==[x['pair']['pair_id'] for x in packet['pairs']]==['G01','G02']
 assert review['common_first_full_text_read'] is True and review['human_reference_full_text_read'] is True
 assert len(review['per_pair'])==2 and review['cross_angle_comparison'] and review['limits']
 for entry,p in zip(review['per_pair'],packet['pairs']):
  assert entry['pair_id']==p['pair']['pair_id'] and all(entry.get(k) for k in FIELDS)
  assert set(entry['quotes'])=={'A','B'}
  for arm,quotes in entry['quotes'].items():assert quotes and all(q in p[arm]['delivery']['body'] for q in quotes)
 summary=(OUT/'root_final_summary.md').read_text('utf-8-sig');assert summary.strip()
 e=html.escape
 def pre(t):return '<pre>'+e(t)+'</pre>'
 def detail(x):return '<details><summary>実入力・テンプレート適用後・RAW・生成条件の全文</summary>'+pre(x['request']['user_prompt'])+pre(x['request']['decoded_input'])+pre(x['output']['raw_output'])+pre(json.dumps(x['output']['generation_config'],ensure_ascii=False,indent=2))+'</details>'
 p0,p1=packet['pairs'];first=packet['common_first']
 columns=[('現行版（保存出力）',p0['A']),('景品の多さと当たらない結果',p0['B']),('9000円と普通に買う場合',p1['B'])]
 content='<h1>H06：同じFactを、2つの見る角度で語る</h1><p>現行版は元のcontract_runtime。v2/v3への変更なし。後半だけ2本新規生成。LoRA・Fact・元の履歴・生成条件固定。角度は設計者指定で、自律的な判断の試験ではありません。</p><p>新しい2条件は見る角度だけが異なります。現行版との比較には角度欄と共通説明の追加も含まれます。前半は保存された同じ出力で、新規生成でも3回分の実験でもありません。新しい後半を次へ渡す閉ループではありません。</p>'
 content+='<h2>共通の前半（保存原文）</h2>'+pre(first['delivery']['body'])+detail(first)
 content+='<h2>今回の後半で固定したFact</h2>'+pre('\n'.join(f['id']+' '+f['claim'] for f in p0['pair']['case']['facts']))+'<details><summary>元Memory・直前2発話・会話操作・関係・Flow</summary>'+pre(json.dumps(p0['pair'],ensure_ascii=False,indent=2))+'</details><div class="grid">'
 metrics=[]
 for label,x in columns:
  body=x['delivery']['body'];out=x['output'];chars=sum(not c.isspace() for c in body);cap=not out['official_stop_reached'] and len(out['output_ids'])>=384
  metrics.append(dict(label=label,chars=chars,output_tokens=len(out['output_ids']),official_stop_reached=out['official_stop_reached'],hit_token_cap=cap,seconds=out['seconds']))
  content+='<article><h2>'+e(label)+'</h2><p>'+e(f'{chars}字 / {len(out["output_ids"])} token / EOS={out["official_stop_reached"]} / 上限到達={cap}')+'</p>'+pre(body)+detail(x)+'</article>'
 content+='</div><h2>渡した角度と、その適用記録</h2>'
 for p in packet['pairs']:content+=pre(json.dumps(p['B']['request']['context'],ensure_ascii=False,indent=2))
 content+='<h2>設計者AIによる全文評価</h2>'+pre(json.dumps(review,ensure_ascii=False,indent=2))+'<h2>結果と限界</h2>'+pre(summary)
 for ref in packet['references']:content+='<details><summary>H06人間原文と既存逆算Memory（参照のみ）</summary>'+pre(ref['human_text'])+pre(ref['memory'])+'</details>'
 page='<!doctype html><html lang="ja"><meta charset="utf-8"><title>H06 見る角度の比較</title><style>body{font:16px/1.8 system-ui,sans-serif;max-width:1550px;margin:24px auto;padding:20px;background:#f5f7fa;color:#203040}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}article{background:white;border:1px solid #d5dce5;border-radius:10px;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}summary{cursor:pointer;color:#17568f}details{margin:20px 0}@media(max-width:1000px){.grid{grid-template-columns:1fr}}</style>'+content+'</html>'
 (OUT/'comparison.html').write_text(page,encoding='utf-8');(OUT/'result.md').write_text(summary,encoding='utf-8')
 text='H06 共通前半（保存原文）\n'+first['delivery']['body']+'\n\n'+'\n\n'.join(label+'\n'+x['delivery']['body'] for label,x in columns)
 (OUT/'full_comparison.txt').write_text(text,encoding='utf-8')
 for x in [first]+[x for _,x in columns]:
  assert all(e(v) in page for v in [x['delivery']['body'],x['request']['user_prompt'],x['request']['decoded_input'],x['output']['raw_output']])
 write(OUT/'report_check.json',dict(status='pass',columns=3,unique_later_outputs=3,common_first_saved=1,unique_inputs_and_raws=4,all_full_text_present=True,metrics=metrics))
 write(OUT/'completion.json',dict(status='complete',technical_audit_sha256=sha(OUT/'technical_audit.json'),review_packet_sha256=sha(OUT/'review_packet.json'),root_review_sha256=sha(OUT/'root_review.json'),root_summary_sha256=sha(OUT/'root_final_summary.md'),comparison_sha256=sha(OUT/'comparison.html'),full_text_sha256=sha(OUT/'full_comparison.txt'),human_quality_labels=0,known_condition_designer_review=True,new_surface_calls=2,baseline_saved_calls=1,common_first_saved_calls=1,planner_calls=0,guard_calls=0,quality_retries=0,training=0,real_tts=False,finished_jst=now()))
 print(json.dumps(dict(status='complete',comparison=str(OUT/'comparison.html'),metrics=metrics),ensure_ascii=False))
if __name__=='__main__':main()
