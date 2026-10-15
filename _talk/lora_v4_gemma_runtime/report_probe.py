"""CPU-only complete-output report for the four-case v5 format probe."""
import argparse
import hashlib
import html
import json
from pathlib import Path
from planner_policy import parse_plan


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def cell(text):
    return html.escape(str(text)).replace('|', '&#124;').replace('\n', '<br>')


def main():
    parser = argparse.ArgumentParser();parser.add_argument('run', type=Path)
    run = parser.parse_args().run.resolve()
    result = read(run / 'results.json')
    state = read(run / 'manifest.json')
    receipt = read(run / 'python_outcome.json')
    assert result['status'] == 'complete' and state['status'] == 'outputs_ready'
    assert receipt['exit_code'] == 0 and receipt['pid'] == state['pid']
    records = result['records']
    assert len(records) == 4
    body = ['# Harness v5 — Planner形式の固定4入力検証', '',
            '**Plannerのみ。Talk/長尺は未実行。形式成功は事実性・雑談品質の合格ではない。**', '',
            '| 入力 | 保存済み旧出力の形式 | v5出力の形式 | 呼出数 |', '|---|---|---|---|']
    audits = []
    for record in records:
        attempts = record['attempts']
        ids = [m['id'] for m in record['input']['memory_candidates']]
        success = record['plan'] is not None
        if success:
            assert parse_plan(attempts[-1]['text'], ids) == record['plan']
        assert len(attempts) <= 2 and all(a['substring_rescue'] is False for a in attempts)
        assert all(a['constraint']['enabled'] and len(a['constraint']['steps']) == a['output_tokens'] for a in attempts)
        try:
            parse_plan(next(c for c in read(run / 'cases.json') if c['id'] == record['case_id'])['baseline_first_call']['text'], ids)
            old_valid = True
        except ValueError:
            old_valid = False
        body.append('| ' + record['case_id'] + ' | ' + ('valid' if old_valid else 'invalid') +
                    ' | ' + ('valid' if success else 'invalid') + ' | ' + str(len(attempts)) + ' |')
        audits.append({'case_id': record['case_id'], 'strict_valid': success,
                       'all_output_ids_logged': True, 'token_mask_steps': sum(len(a['constraint']['steps']) for a in attempts)})
    body += ['', '## 全文の旧出力／v5出力', '', '| 入力 | 保存済み旧Planner出力 | v5全attempt出力 |', '|---|---|---|']
    cases = {c['id']: c for c in read(run / 'cases.json')}
    for record in records:
        body.append('| ' + record['case_id'] + ' | ' + cell(cases[record['case_id']]['baseline_first_call']['text']) +
                    ' | ' + cell('\n\n'.join('attempt ' + str(i+1) + ':\n' + a['text'] for i,a in enumerate(record['attempts']))) + ' |')
    body += ['', '## 実入力・全出力', '']
    for record in records:
        body += ['### ' + record['case_id'], '']
        for i, attempt in enumerate(record['attempts']):
            body += ['#### attempt ' + str(i+1), '', '**実際にモデルへ渡った入力**', '',
                     '```text', attempt['decoded_input'], '```', '', '**生成した全文**', '',
                     '```text', attempt['text'], '```', '',
                     f"{attempt['input_tokens']} input token / {attempt['output_tokens']} output token / {attempt['seconds']} 秒。",
                     '']
    body += ['## 比較の範囲', '',
             '同じGemma Planner adapterと4入力のpayloadを使用。schemaの短い指示、token mask、採用方法を変更した。旧保存出力との比較で、自然さ・事実保持の効果を独立には評価していない。', '',
             'Memoryとの整合性はrootレビューと次の事実検査で確認する。PlanなしFallback/期限/α契約はCPU部品検査であり、このPlanner-only実生成にはまだ接続していない。', '']
    review = read(run / 'root_review.json') if (run / 'root_review.json').exists() else None
    if review:
        body += ['## rootが全文を読んで確認した残課題', '',
                 '**全4件がuse_memory=false。MemoryありRELも旧true/mem:15からfalse/nullになった。形式成功とMemory選択の改善は別。**', '',
                 '| 入力 | 実出力・観測 | 確認内容 |', '|---|---|---|']
        for issue in review['issues']:
            body.append('| '+issue['case']+' | '+cell(issue.get('quote','旧true/mem:15 → 新false/null'))+
                        ' | '+cell(issue['assessment'])+' |')
        body += ['', '自然さ・話題接続・反復の評価はTalk/長尺を実行してから行う。うなぎ問題を防げたという判定はまだしていない。', '']
    text = '\n'.join(body)
    (run / 'comparison.md').write_text(text, encoding='utf-8')
    rows = []
    details = []
    for record in records:
        old = cases[record['case_id']]['baseline_first_call']['text']
        new = '\n\n'.join('attempt '+str(i+1)+':\n'+a['text'] for i,a in enumerate(record['attempts']))
        rows.append('<tr><th>'+html.escape(record['case_id'])+'</th><td><pre>'+html.escape(old)+
                    '</pre></td><td><pre>'+html.escape(new)+'</pre></td></tr>')
        details.append('<h2>'+html.escape(record['case_id'])+'</h2>')
        for i,a in enumerate(record['attempts']):
            details.append('<h3>attempt '+str(i+1)+'</h3><h4>実入力</h4><pre>'+html.escape(a['decoded_input'])+
                           '</pre><h4>全出力</h4><pre>'+html.escape(a['text'])+'</pre>')
    document = ('<h1>Harness v5 — Planner形式の固定4入力検証</h1><p>Plannerのみ。Talkと長尺は未実行。'
                '形式成功は事実性・雑談品質の合格ではない。</p><table><tr><th>入力</th><th>保存済み旧出力</th>'
                '<th>v5全出力</th></tr>'+''.join(rows)+'</table>'+''.join(details))
    if review:
        document += '<h2>rootレビュー・残課題</h2><p>全4件use_memory=false。MemoryありRELも旧true/mem:15からfalse/nullになった。品質合格ではない。</p><ul>'
        document += ''.join('<li>'+html.escape(issue['case']+': '+issue.get('quote','Memory IDの保持')+' — '+issue['assessment'])+'</li>' for issue in review['issues'])+'</ul>'
    (run / 'comparison.html').write_text('<!doctype html><meta charset="utf-8"><title>Harness v5 Planner</title>'
        '<style>body{font-family:system-ui;line-height:1.6;margin:30px}table{border-collapse:collapse;width:100%;table-layout:fixed}'
        'td,th{border:1px solid #bbb;padding:10px;vertical-align:top;overflow-wrap:anywhere}pre{white-space:pre-wrap;background:#f5f5f5;padding:12px}</style>'+document,
        encoding='utf-8')
    audit = {'status':'pass','exit_scope':'Python outcome receipt; child_guard invokes os._exit with that code',
             'actual_pid':state['pid'],'python_exit_code':receipt['exit_code'],'independently_observed_OS_exit_code':None,
             'calls':sum(len(r['attempts']) for r in records),
             'schema_valid_cases':sum(r['plan'] is not None for r in records),'quality_pass':False,'records':audits,
             'comparison_md_sha256':hashlib.sha256(text.encode('utf8')).hexdigest()}
    (run / 'report_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(audit,ensure_ascii=False))


if __name__ == '__main__':
    main()
