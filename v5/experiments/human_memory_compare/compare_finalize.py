from common import *
import html,shutil

def main():
 import finalize_cpu
 finalize_cpu.main()
 shutil.copyfile(OUT/'comparison.html',OUT/'runtime_details.html');shutil.copyfile(OUT/'result.md',OUT/'runtime_result.md');shutil.copyfile(OUT/'report_check.json',OUT/'runtime_report_check.json')
 packet=read(OUT/'review_packet.json');refs=read(OUT/'reference/source_pairs.json');audit=read(OUT/'technical_audit.json');summary=(OUT/'root_final_summary.md').read_text(encoding='utf-8');esc=html.escape
 parts=['<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>人間・逆算記憶・現行ハーネス</title><style>body{font:16px/1.8 system-ui;margin:24px;color:#203040}pre{white-space:pre-wrap;overflow-wrap:anywhere}.cols{display:grid;grid-template-columns:1fr 0.8fr 1fr;gap:18px}article{border-top:2px solid #ccd5df;padding:16px 0}section{padding:14px;background:#f3f6fa}h2{font-size:21px}@media(max-width:900px){.cols{grid-template-columns:1fr}}</style><h1>人間原文・既存逆算Memory・現行ハーネス</h1><p>元音声・実分数は未確認。AIには人間の原文・style・Flow・履歴を渡さず、既存の圧縮Memoryだけを使用。元配信者の能力全体との公平な優劣試験ではない。</p><p><a href="reference/human.txt">人間原文全文</a> ／ <a href="speech.txt">AI実生成順の全文</a> ／ <a href="runtime_details.html">全実入力・RAW・Planner・αログ</a> ／ <a href="result.md">結果</a></p><pre>'+esc(summary)+'</pre>']
 order=[s['selected_memory']['id'] for s in packet['selections'] if s['selected_memory']];parts+=['<p>AIの実選択順：'+esc(' → '.join(order))+'。下の各行は内容対応を見やすくするため人間側の資料順。AI全文の実順序は上記リンクで保全。</p>']
 for r in refs:
  turns=[x for x in packet['turns'] if x['memory_id']==r['memory_id']]
  text='\n\n'.join('T'+str(x['turn'])+' '+x['body']+(' [形式保留]' if not x['delivered'] else '') for x in turns) or '未生成・未選択'
  parts+=['<article><h2>'+r['memory_id']+'</h2><div class="cols"><section><h3>人間原文・無編集</h3><pre>'+esc(r['human_text'])+'</pre></section><section><h3>入力した既存逆算Memory・無編集</h3><pre>'+esc(r['memory'])+'</pre></section><section><h3>AI実生成・無編集</h3><pre>'+esc(text)+'</pre></section></div></article>']
 doc='\n'.join(parts)+'</html>';(OUT/'comparison.html').write_text(doc,encoding='utf-8');(OUT/'result.md').write_text('# 人間原文と逆算Memoryによる現行比較\n\n'+summary+'\n\n## 元Memory時点の制限\n\n'+json.dumps(read(OUT/'source_input_audit.json'),ensure_ascii=False,indent=2),encoding='utf-8')
 for r in refs:assert esc(r['human_text']) in doc and esc(r['memory']) in doc
 for t in packet['turns']:assert esc(t['body']) in doc
 write(OUT/'report_check.json',dict(status='pass',human_reference_topics=4,ai_turns=len(packet['turns']),all_reference_memory_ai_text_present=True,runtime_inputs_raw_report='runtime_details.html',html_sha256=sha(OUT/'comparison.html'),speech_sha256=sha(OUT/'speech.txt'),human_sha256=sha(OUT/'reference/human.txt')))
 done=read(OUT/'completion.json');done.update(goal='human-vs-memory-derived diagnostic comparison, not length matching',all_source_targets_presented=audit['no_repeated_source_fact_targets'] and sum(len(t['actual_surface_request']['context']['target_ids']) for t in packet['turns'])==9,report_sha256=sha(OUT/'result.md'));write(OUT/'completion.json',done)
 print(json.dumps(dict(status='complete',reference_topics=4,ai_turns=len(packet['turns'])),ensure_ascii=False))
if __name__=='__main__':main()
