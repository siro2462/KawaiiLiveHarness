"""CPU report and blinded review packet; no automatic quality scores."""
import argparse
import hashlib
import html
import json
from pathlib import Path
from quality_eval import read, rows
from quality_metrics import AXES, preference_summary


def build(out):
    out = Path(out)
    pairs = rows(out / 'comparisons.jsonl') if (out / 'comparisons.jsonl').exists() else []
    baseline = read(out / 'baseline_audit.json')
    key, packet = {}, []
    for pair in pairs:
        flip = hashlib.sha256(('quality-blind-v1:' + pair['pair_id']).encode()).digest()[0] % 2
        left, right = ('B', 'A') if flip else ('A', 'B')
        opaque_id = hashlib.sha256(pair['pair_id'].encode()).hexdigest()[:20]
        key[opaque_id] = {'left': left, 'right': right, 'experiment': pair['experiment'],
                          'case_id': pair['case_id'], 'cluster_id': pair['cluster_id'],
                          'pair_id': pair['pair_id']}
        packet.append({'pair_id': opaque_id, 'left': pair[left + '_text'], 'right': pair[right + '_text'],
                       'recent': pair['context_recent'], 'memory': pair['source_grounding'],
                       'scope': 'one candidate; long-topic axes may be N/A'})
    packet.sort(key=lambda r: r['pair_id'])
    (out / 'blind_key.private.json').write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding='utf8')
    (out / 'blind_packet.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding='utf8')
    labels = rows(out / 'human_review.jsonl') if (out / 'human_review.jsonl').exists() else []
    summary = preference_summary(labels, key)
    (out / 'quality_metrics.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
    content = ['# Harness v5 品質評価 Step 1〜3', '',
               '通常Runtime・モデル・LoRAは固定。模擬比較のみで、通常Event Storeや実TTSへ出力しない。', '',
               '## 保存済みベースライン', '', '```json', json.dumps(baseline, ensure_ascii=False, indent=2), '```', '',
               '## 新規AB', '', 'A/B: stop=2文/停止なし（両方96token）。fallback=Plan破棄/保持（共通の保存済み拒否事象から1retry）。', '',
               f'完了比較組数: {len(pairs)} / 102。人間評価: {summary["status"]}。品質合格とは判定しない。', '',
               '固定入力は既に観測したdevelopment資料。seed・評価者を独立した新しいepisodeとして数えない。', '',
               '## 出力全文', '', '| 組 | A | B | 停止理由 A / B | tokens A / B | CPU fact flag A / B |',
               '|---|---|---|---|---|---|']
    def cell(text):
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\n', '<br>')
    for pair in pairs:
        content.append(f'| {cell(pair["pair_id"])} | {cell(pair["A_text"])} | {cell(pair["B_text"])} | '
                       f'{pair["A_stop"]} / {pair["B_stop"]} | {pair["A_tokens"]} / {pair["B_tokens"]} | '
                       f'{pair["A_fact_flag"]} / {pair["B_fact_flag"]} |')
    content += ['', '## 解釈の制約', '',
                '- CPU fact flagは捏造の正解ラベルではない。未検出を正しいとしない。',
                '- fallbackは4拒否事象に条件付けた再試行診断。セッション全体の改善率ではない。',
                '- 単発の選好率は長尺での発展・自然な終了の合格を意味しない。',
                '- 人間ラベル未提出なら、選好率・事実正確率・誤拒否率は未測定。',
                '- 保存候補の原本、全実入力/出力はall_calls.jsonl、検索29回はretrieval29.jsonl。',
                '- 保存済みGold/Generated/Planなしの3発話はsaved_fixed36.jsonl。', '']
    (out / 'quality_report.md').write_text('\n'.join(content), encoding='utf8')
    table = ['<h1>発話全文比較</h1><p>CPU flagは正誤の正解ではありません。人間評価は別途収集します。</p>',
             '<p><a href="blind_review.html">匿名比較の採点</a> / <a href="quality_report.md">評価状況</a></p>']
    for pair in pairs:
        table.append('<h2>' + html.escape(pair['pair_id']) + '</h2><div class="pair"><pre>' +
                     html.escape(pair['A_text']) + '</pre><pre>' + html.escape(pair['B_text']) + '</pre></div>')
    style = '<style>body{font-family:system-ui;margin:2rem;max-width:1500px}pre{white-space:pre-wrap;line-height:1.7;background:#f4f5f7;padding:1rem}.pair{display:grid;grid-template-columns:1fr 1fr;gap:1rem}label{margin-right:1rem}select{margin:.4rem}section{border-top:1px solid #aaa;padding:1rem}textarea{width:90%;height:4rem}</style>'
    (out / 'full_output_table.html').write_text('<!doctype html><meta charset="utf-8">' + style + ''.join(table), encoding='utf8')
    # No condition names, tokens, flags or the randomization key in the blind HTML.
    payload = json.dumps(packet, ensure_ascii=False).replace('<', '\\u003c')
    axes = json.dumps(AXES)
    page = r'''<!doctype html><meta charset="utf-8"><title>匿名発話比較</title>STYLE
<h1>匿名発話比較</h1><p>一度の発話候補を比較します。観察できない軸・件数は未評価のままにしてください。左右は条件名ではありません。</p>
<label>評価者ID <input id="rater" required></label><label>評価者区分 <select id="kind"><option value="human">人間</option><option value="AI_root">AI root</option></select></label>
<button id="download">入力済み評価をJSONL保存</button><div id="items"></div>
<script>
const packet=PAYLOAD, axes=AXES;
const escape=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const scores=side=>axes.map(a=>`<label>${side} ${a}<select data-side="${side}" data-axis="${a}"><option value="">N/A・未評価</option>${[0,1,2,3,4].map(n=>`<option>${n}</option>`).join('')}</select></label>`).join('');
document.querySelector('#items').innerHTML=packet.map(p=>`<section data-id="${p.pair_id}"><h2>${p.pair_id}</h2><details><summary>開始文・直前の文脈と元Memory</summary><pre>${escape(p.recent)}</pre><pre>${escape(p.memory?.body??'Memoryなし')}</pre></details><div class="pair"><pre>左\n${escape(p.left)}</pre><pre>右\n${escape(p.right)}</pre></div><label>選好<select data-winner><option value="">未評価</option><option value="left">左</option><option value="right">右</option><option value="tie">同等</option><option value="abstain">判断保留</option></select></label><div>${scores('left')}${scores('right')}</div>${['unsupported_claims','contradictions'].map(k=>`<div>${k}: ${['left','right'].map(s=>`<label>${s}<input type="number" min="0" data-count="${k}" data-side="${s}" placeholder="未評価"></label>`).join('')}</div>`).join('')}<textarea data-notes placeholder="引用、根拠、判定の迷い"></textarea></section>`).join('');
document.querySelector('#download').onclick=()=>{const rater=document.querySelector('#rater').value.trim();if(!rater){alert('評価者IDを入力してください');return}const result=[];for(const e of document.querySelectorAll('section')){const winner=e.querySelector('[data-winner]').value;if(!winner)continue;const row={pair_id:e.dataset.id,rater_id:rater,reviewer_kind:document.querySelector('#kind').value,winner,scores:{left:{},right:{}},unsupported_claims:{},contradictions:{},notes:e.querySelector('[data-notes]').value};for(const s of e.querySelectorAll('[data-axis]'))row.scores[s.dataset.side][s.dataset.axis]=s.value===''?null:Number(s.value);for(const i of e.querySelectorAll('[data-count]'))row[i.dataset.count][i.dataset.side]=i.value===''?null:Number(i.value);result.push(row)}const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([result.map(x=>JSON.stringify(x)).join('\n')+'\n'],{type:'application/x-ndjson'}));a.download='human_review.jsonl';a.click();URL.revokeObjectURL(a.href)};
</script>'''
    page = page.replace('STYLE', style).replace('PAYLOAD', payload).replace('AXES;', axes + ';')
    (out / 'blind_review.html').write_text(page, encoding='utf8')
    return {'pairs': len(pairs), 'human_review_status': summary['status']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True)
    print(json.dumps(build(p.parse_args().out), ensure_ascii=False))
