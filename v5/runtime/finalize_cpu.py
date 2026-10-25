from common import *
import html

def main():
 cfg=verify();audit=read(OUT/'technical_audit.json');assert audit['status']=='pass'
 packet=read(OUT/'review_packet.json');review=read(OUT/'root_review.json');rr=packet['final_state']
 expected=[r['call_id'] for r in packet['turns']];planids=[r['planner_call_id'] for r in packet['turns']]
 assert review['reviewed_surface_call_ids']==expected and review['reviewed_planner_call_ids']==planids and review['reviewed_selection_indices']==[r['index'] for r in packet['selections']]
 assert review['review_packet_sha256']==sha(OUT/'review_packet.json') and review['human_quality_labels']==0 and review['root_full_text_read'] is True
 assert len(review['per_turn'])==len(expected) and [x['call_id'] for x in review['per_turn']]==expected
 for x in review['per_turn']:
  assert all(k in x for k in ['fact_preservation','naturalness','connection','content_repetition','expression_repetition','planner_effect','quotes'])
 summary=(OUT/'root_final_summary.md').read_text(encoding='utf-8');assert summary.strip()
 def esc(x):return html.escape(str(x))
 blocks=['<!doctype html><html lang="ja"><meta charset="utf-8"><title>現行構成・連続発話</title><style>body{max-width:1100px;margin:32px auto;font:17px/1.8 system-ui;padding:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 monospace}article{border-top:2px solid #ddd;padding:22px 0}.speech{white-space:pre-wrap;font-size:20px}summary{cursor:pointer;color:#165a80}</style><h1>現行構成・連続発話の全文</h1>', '<p>音声未作成／意味未検証の生成履歴／設計者AI評価・人間評価0。全文は無編集。250字/分の仮定で時間換算。</p>', '<p>'+esc(str(audit['delivered_chars']))+'字・推定'+esc(round(rr['estimated_minutes'],2))+'分。終了理由：'+esc(rr['stop_reason'])+'</p>', '<a href="speech.txt">発話本文だけ</a> ／ <a href="result.md">結果</a><pre>'+esc(summary)+'</pre>']
 for row,rv in zip(packet['turns'],review['per_turn']):
  blocks+=['<article><h2>T'+str(row['turn']).zfill(3)+' '+esc(row['memory_id'])+(' 採用' if row['delivered'] else '形式保留')+'</h2><div class="speech">'+esc(row['body'])+'</div><p>'+esc(row['format_reason'] or '')+'</p><details><summary>評価</summary><pre>'+esc(json.dumps(rv,ensure_ascii=False,indent=2))+'</pre></details>']
  for title,key in [('元Fact','source_facts'),('実際の履歴','case'),('Planner実入力','actual_planner_request'),('Planner RAW','actual_planner_output'),('Plan適用','plan_application'),('Surface実入力','actual_surface_request'),('Surface RAW','actual_surface_output'),('進捗','after')]:
   blocks+=['<details><summary>'+title+'</summary><pre>'+esc(json.dumps(row[key],ensure_ascii=False,indent=2))+'</pre></details>']
  blocks+=['<details><summary>Surface RAW文字列</summary><pre>'+esc(row['raw_output'])+'</pre></details></article>']
 blocks+=['<details><summary>記憶α選択ログ全文</summary><pre>'+esc(json.dumps(packet['selections'],ensure_ascii=False,indent=2))+'</pre></details></html>']
 doc='\n'.join(blocks);(OUT/'comparison.html').write_text(doc,encoding='utf-8')
 result='# 現行構成・連続発話\n\n'+summary+'\n\n## 実行記録\n\n'+json.dumps({k:v for k,v in audit.items() if k!='entries'},ensure_ascii=False,indent=2)+'\n\n実測生成時間、文字量からの推定時間、実音声時間は別。音声は未作成。\n'
 (OUT/'result.md').write_text(result,encoding='utf-8')
 assert doc.count('<article>')==len(expected)
 for row in packet['turns']:assert esc(row['body']) in doc and esc(row['raw_output']) in doc
 write(OUT/'report_check.json',dict(status='pass',turns=len(expected),all_bodies_raw_inputs_plans_present=True,review_sha256=sha(OUT/'root_review.json'),html_sha256=sha(OUT/'comparison.html'),speech_sha256=sha(OUT/'speech.txt')))
 write(OUT/'completion.json',dict(status='complete',technical_integrity='pass',full_root_review_done=True,quality_is_not_certified=True,target_met=rr['target_met'],planner_format_fallbacks=rr['planner_format_fallbacks'],actual_tts=False,human_quality_labels=0,finished_jst=now(),report_sha256=sha(OUT/'result.md')))
 print(json.dumps(dict(status='complete',turns=len(expected),chars=audit['delivered_chars'],target_met=rr['target_met']),ensure_ascii=False))
if __name__=='__main__':main()
