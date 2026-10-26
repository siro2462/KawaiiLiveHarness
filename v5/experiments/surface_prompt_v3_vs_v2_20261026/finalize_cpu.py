from common import *
import html
FIELDS=['narrative_focus','evaluation_development','fact_preservation','emotional_strength','thought_development','meaningful_repetition','expression_repetition','listener_address','naturalness','unsupported_additions','history_connection','quotes']
def main():
 verify();audit=read(OUT/'technical_audit.json');assert audit['status']=='pass'
 packet=read(OUT/'review_packet.json');review=read(OUT/'root_review.json')
 assert review['review_packet_sha256']==sha(OUT/'review_packet.json')==audit['review_packet_sha256']
 assert review['root_full_text_read'] is True and review['human_quality_labels']==0
 assert review['reviewed_pair_ids']==[x['pair']['pair_id'] for x in packet['pairs']]
 assert len(review['per_pair'])==4
 for entry,p in zip(review['per_pair'],packet['pairs']):
  assert entry['pair_id']==p['pair']['pair_id'] and all(k in entry and entry[k] for k in FIELDS)
  assert isinstance(entry['quotes'],dict) and set(entry['quotes'])=={'A','B'}
  for arm,quotes in entry['quotes'].items():assert quotes and all(q in p[arm]['delivery']['body'] for q in quotes)
 summary=(OUT/'root_final_summary.md').read_text(encoding='utf-8');assert summary.strip()
 e=html.escape
 def pre(text):return '<pre>'+e(text)+'</pre>'
 content='<h1>SurfaceプロンプトA/B：H04・H06・H07</h1><p>A：保存済みv2出力 / B：3点を加えたv3。3話題・4固定履歴プローブ。新規Surface4call、Planner/Guard/学習0。1seed、設計者AI既知条件、人間評価0、実TTSなし。</p><p>H06は2発話。両条件の履歴は前回と同じ元の現行版本文に固定。v2本文もv3本文も後続へ入れていない。B同士をつないだ連続実験ではない。初回relationの不整合と384token上限は両条件で維持。プロンプト全体の一括変更で各条項の効果は未分離。</p>'
 check=[]
 for obj,judgment in zip(packet['pairs'],review['per_pair']):
  p=obj['pair'];pid=p['pair_id'];content+='<section><h2>'+e(pid+' '+p['memory_id']+'（元'+p['source_call_id']+'）')+'</h2><h3>今回のFact</h3>'+pre('\n'.join(f['id']+' '+f['claim'] for f in p['case']['facts']))+'<details><summary>固定した直前履歴・会話操作・関係・Flow</summary>'+pre(json.dumps(p['case'],ensure_ascii=False,indent=2))+'</details><div class="grid">'
  row={}
  for arm in ['A','B']:
   x=obj[arm];body=x['delivery']['body'];out=x['output'];chars=sum(not c.isspace() for c in body);cap=not out['official_stop_reached'] and len(out['output_ids'])>=384
   text=f'{chars}字 / {len(out["output_ids"])} token / EOS={out["official_stop_reached"]} / 上限到達={cap}'
   content+='<article><h3>'+arm+(' v2（保存出力）' if arm=='A' else ' v3（新規生成）')+'</h3><p>'+e(text)+'</p>'+pre(body)+'<details><summary>実入力全文・公式テンプレート適用後・RAW・条件</summary>'+pre(x['request']['user_prompt'])+pre(x['request']['decoded_input'])+pre(out['raw_output'])+pre(json.dumps(out['generation_config'],ensure_ascii=False,indent=2))+'</details></article>'
   row[arm]=dict(chars=chars,tokens=len(out['output_ids']),official_stop_reached=out['official_stop_reached'],hit_token_cap=cap)
  content+='</div><details open><summary>設計者AIの評価（人間評価ではない）</summary>'+pre(json.dumps(judgment,ensure_ascii=False,indent=2))+'</details></section>';check.append(dict(pair_id=pid,**row))
 content+='<h2>結果・限界</h2>'+pre(summary)+'<h2>人間原文と元Memory（参照のみ・生成側へ未入力）</h2>'
 for ref in packet['references']:
  if ref['memory_id'] in ['H04','H06','H07']:content+='<details><summary>'+e(ref['memory_id'])+'</summary><h3>原文</h3>'+pre(ref['human_text'])+'<h3>既存逆算Memory</h3>'+pre(ref['memory'])+'</details>'
 page='<!doctype html><html lang="ja"><meta charset="utf-8"><title>Surface v3 vs v2</title><style>body{font:16px/1.8 system-ui,sans-serif;max-width:1400px;margin:30px auto;padding:20px;background:#f5f7fa;color:#203040}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}section,article{background:white;border:1px solid #d5dce5;border-radius:10px;padding:20px;margin:18px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}summary{cursor:pointer;color:#17568f}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style>'+content+'</html>'
 (OUT/'comparison.html').write_text(page,encoding='utf-8');(OUT/'result.md').write_text(summary,encoding='utf-8')
 for p in packet['pairs']:
  for arm in ['A','B']:
   x=p[arm];assert e(x['delivery']['body']) in page and e(x['request']['user_prompt']) in page and e(x['output']['raw_output']) in page
 write(OUT/'report_check.json',dict(status='pass',pairs=4,outputs=8,actual_inputs=8,raw_outputs=8,all_bodies_and_inputs_present=True,metrics=check))
 write(OUT/'completion.json',dict(status='complete',technical_audit_sha256=sha(OUT/'technical_audit.json'),review_packet_sha256=sha(OUT/'review_packet.json'),root_review_sha256=sha(OUT/'root_review.json'),root_summary_sha256=sha(OUT/'root_final_summary.md'),comparison_sha256=sha(OUT/'comparison.html'),human_quality_labels=0,known_condition_designer_review=True,new_surface_calls=4,baseline_saved_calls=4,planner_calls=0,guard_calls=0,quality_retries=0,training=0,real_tts=False,finished_jst=now()))
 print(json.dumps(dict(status='complete',comparison=str(OUT/'comparison.html'),metrics=check),ensure_ascii=False))
if __name__=='__main__':main()
