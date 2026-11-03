"""End-to-end CPU validation using frozen authored memories, never rewriting them."""
import argparse
import collections
import hashlib
import html
import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import unittest
import zipfile

from .normalize import CATEGORIES, digest, strict_json_loads
from .store import MemoryDB
from .projection import project_episode, alpha_records, resolve_recall
from .selector_adapter import select_episode, validate_plan
from .surface import render_surface


def read(p):
    return strict_json_loads(Path(p).read_text('utf-8-sig'))


def write(p, value):
    Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def prepare_inputs(rows, model_dir):
    import torch
    from transformers import AutoProcessor
    if not torch.__version__.endswith('+cpu') or torch.cuda.is_available():
        raise RuntimeError('CPU-only dependency runtime required')
    proc = AutoProcessor.from_pretrained(str(model_dir), local_files_only=True, trust_remote_code=False)
    for row in rows:
        prompt = row['surface']['user_prompt']
        messages = [dict(role='user', content=[dict(type='text', text=prompt)])]
        kwargs = dict(tokenize=True, return_dict=True, return_tensors='pt', add_generation_prompt=True, enable_thinking=False)
        fields = {k: v.tolist() for k, v in proc.apply_chat_template(messages, **kwargs).items()}
        ids = fields['input_ids'][0];decoded = proc.decode(ids, skip_special_tokens=False)
        if proc.tokenizer.encode(decoded, add_special_tokens=False) != ids or prompt not in decoded:
            raise AssertionError('Official processor roundtrip changed the prompt')
        if len(ids) + 1536 >= 8192:
            raise AssertionError('Input does not fit existing 8192 context + 1536 generation budget')
        row['prepared'] = dict(messages=messages, template_kwargs=kwargs, processor_fields=fields, decoded_input=decoded,
                               input_tokens=len(ids), truncation_tokens=0, official_processor=True, generated=False)
    return dict(torch=torch.__version__, cuda_available=torch.cuda.is_available(), model_dir=str(model_dir),
                tokenizer_only=True, inputs=len(rows), input_tokens_min=min(len(r['prepared']['processor_fields']['input_ids'][0]) for r in rows),
                input_tokens_max=max(len(r['prepared']['processor_fields']['input_ids'][0]) for r in rows))


def build_alpha(snapshot, out, alpha_path):
    module = load(alpha_path, 'memory_db_existing_alpha')
    records = alpha_records(snapshot)
    write(out / 'alpha_records.json', records)
    empty = out / 'empty_reference.zip'
    with zipfile.ZipFile(empty, 'x'):
        pass
    path = out / 'alpha_projection.sqlite'
    if path.exists():
        raise FileExistsError(path)
    a = module.Alpha(path)
    try:
        stats = a.populate(empty, out / 'alpha_records.json', force=False)
        results = []
        allowed = {r['id'] for r in records}
        for rec in records:
            found = a.recall(rec['title'], namespace=rec['namespace'], top_k=8)
            if not found or any(x['id'] not in allowed for x in found):
                raise AssertionError('Recall returned no candidates or leaked another source')
            if any(x['authority'] != 'synthetic_fixture' for x in found):
                raise AssertionError('Authority changed')
            for x in found:
                projected = resolve_recall(snapshot, x)
                assert projected['provenance']['snapshot_id'] == snapshot['snapshot_id']
                saved = a.get(x['id'])
                expected = next(r for r in records if r['id'] == x['id'])
                if saved['body'] != expected['text'] or saved['beats'] != expected['beats']:
                    raise AssertionError('Alpha projection changed source text')
            results.append(dict(query=rec['title'], source_revision=rec['_memory_db']['revision_id'], candidates=found))
        write(out / 'recall.json', results)
        return dict(status='pass', records=len(records), queries=len(results), stats=stats,
                    scope='same frozen validation snapshot, existing TF-IDF proxy; no semantic ranking quality score')
    finally:
        a.close()


def report(out, rows, audit):
    esc = html.escape
    txt = lambda x: esc(json.dumps(x, ensure_ascii=False, indent=2))
    page = ['<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>記憶DB・30件CPU検証</title>',
            '<style>body{font:16px/1.7 system-ui;background:#f4f6fa;color:#213148;margin:0}main{max-width:1600px;margin:auto;padding:25px}header,article{background:white;padding:22px;margin:18px 0;border-radius:10px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.F{background:#d5eaff}.E{background:#ffedac}.T{background:#dff2c9}.step{padding:9px;margin:6px 0;border-radius:5px}.muted{color:#506177}.warning{background:#fff2dc;padding:10px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f4f7;padding:12px;font-size:13px}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:7px;border-bottom:1px solid #ddd}a{color:#175aaa}input{font:inherit;padding:8px;width:80%}summary{cursor:pointer}@media(max-width:850px){.grid{display:block}}</style><main>',
            '<header><h1>新しい記憶DB：30件を通したCPU検証</h1><p class="warning">表示は保存された記憶とCPUが選んだ操作です。Surfaceの発話結果ではありません。LLM推論・学習・TTSは0件。色は操作計画の分類で、自然さの採点ではありません。</p>',
            f'<p>取込 {audit["imported"]}件 / 断片 {audit["atoms"]}件 / 明示参照 {audit["links"]}件 / 公式Surface入力 {audit["processor"]["inputs"]}件</p>',
            '<p>元の内容確認状態：確認済み8・修正待ち2・未確認20。30件全体はvalidation専用snapshot。通常の承認済みsnapshotは8件のみ。</p>',
            '<p><a href="result.md">結果と限界</a> / <a href="technical_audit.json">CPU検査結果</a> / <a href="review_packet.json">全データ・操作・実入力</a> / <a href="memory_v2.sqlite">新Memory DB</a></p>',
            '<p><input id="query" aria-label="記憶を検索" placeholder="元ID・題名・内容で検索"></p></header>']
    for row in rows:
        ep = row['revision'];plan = row['plans']['rhythm']
        page.append(f'<article><h2>元ID {row["source_id"]}：{esc(ep["title"])}</h2><p>{esc(row["review_status_label"])} / 版{ep["version"]} / {len(ep["atoms"])}断片 / {len(ep["links"])}参照 / 操作{len(plan["steps"])} / 保留{len(plan["deferred_nodes"])}</p><div class="grid"><section><h3>元記憶と保存した材料</h3>')
        page.append('<pre>' + esc(ep['raw_document'].get('元DB', {}).get('episode', '')) + '</pre>')
        for atom in ep['atoms']:
            kind = row['sample']['nodes'][next(i for i, n in enumerate(row['sample']['nodes']) if n['id'] == atom['atom_id'])]['kind']
            page.append(f'<div class="step {kind}">{esc(atom["local_id"])} / {esc(atom["origin"])}<br>{esc(atom["content"])}<div class="muted">{esc(atom["epistemic"])} / {esc(atom["execution_status"])}</div></div>')
        page.append('<details><summary>元JSON・由来・意味リンク全文</summary><pre>' + txt(ep) + '</pre></details></section><section><h3>新DBからCPUが選んだ操作列</h3>')
        by = {n['id']: n for n in row['sample']['nodes']}
        for step in plan['steps']:
            page.append(f'<div class="step {step["kind"]}">{step["index"]} {esc(step["operation"])} / {esc(by[step["memory_id"]]["local_id"])}<br>{esc(step["content"])}<div class="muted">根拠・接続：{esc(str(step["relation"]))}</div></div>')
        if plan['deferred_nodes']:
            page.append('<h4>明示的な保留</h4><pre>' + txt(plan['deferred_nodes']) + '</pre>')
        page.append('<details><summary>両CPU選択器の全結果</summary><pre>' + txt(row['plans']) + '</pre></details>')
        page.append('<details><summary>Surface実入力・公式Processorで復元した全文</summary><pre>' + esc(row['surface']['user_prompt']) + '</pre><pre>' + esc(row['prepared']['decoded_input']) + '</pre></details></section></div></article>')
    page.append('<script>document.getElementById("query").addEventListener("input",e=>{let q=e.target.value.toLowerCase();document.querySelectorAll("article").forEach(a=>a.hidden=!a.textContent.toLowerCase().includes(q));});</script></main></html>')
    content = ''.join(page)
    (out / 'comparison.html').write_text(content, encoding='utf-8')
    assert content.count('<article>') == len(rows)
    for row in rows:
        assert esc(row['surface']['user_prompt']) in content
        assert esc(row['prepared']['decoded_input']) in content
        for atom in row['revision']['atoms']:
            assert esc(atom['content']) in content
    write(out / 'report_check.json', dict(status='pass', records=len(rows), all_atoms_and_inputs_present=True,
                                        comparison_sha256=sha(out / 'comparison.html')))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cpu-deps', type=Path, required=True)
    parser.add_argument('--alpha-deps', type=Path, required=True)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--summer-json', type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError('Validation output must be a new directory')
    args.output.mkdir(parents=True)
    started = time.perf_counter();out = args.output
    os.environ['HF_HUB_OFFLINE'] = '1';os.environ['TRANSFORMERS_OFFLINE'] = '1';os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    sys.path.insert(0, str(args.cpu_deps))
    sys.path.insert(1, str(args.alpha_deps))
    test_log = io.StringIO()
    test_result = unittest.TextTestRunner(stream=test_log, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromName('v5.memory_db.tests.test_memory_db'))
    (out / 'test_results.txt').write_text(test_log.getvalue(), encoding='utf-8')
    if not test_result.wasSuccessful():
        raise AssertionError('CPU unit tests failed; see test_results.txt')
    manifest = read(args.input_dir / 'manifest.json')
    root = Path(__file__).resolve().parents[1]
    protected = list((root / 'runtime').rglob('*.py')) + [args.input_dir / r['file'] for r in manifest['records']]
    frozen = {str(p): sha(p) for p in protected}
    write(out / 'input_manifest.json', dict(source=str(args.input_dir), manifest_sha256=sha(args.input_dir / 'manifest.json'), frozen_files=frozen,
         scope='new DB + compatibility adapters; validation drafts explicitly included; no generation', generation_calls=0))
    rows, new_imports = [], []
    with MemoryDB(out / 'memory_v2.sqlite') as db:
        for entry in manifest['records']:
            path = args.input_dir / entry['file'];raw = path.read_bytes();doc = strict_json_loads(raw.decode('utf-8-sig'))
            assert sha(path) == entry['sha256']
            row = db.import_document(doc, 'zip_fiction', 'fictional', source_bytes=raw, source_name=str(path))
            assert row['created'];new_imports.append(row)
            status = {'内容確認済み': 'accepted', '修正待ち': 'changes_requested'}.get(entry['review_status'], 'unreviewed')
            if status != 'unreviewed':
                db.review_revision(row['revision_id'], status, 'inherited_frozen_root_review', entry['review_notes'], row['content_sha256'])
            assert db.export_document(row['revision_id']) == doc
            assert not db.import_document(doc, 'zip_fiction', 'fictional', source_bytes=raw)['created']
        approved = db.create_snapshot('zip_fiction')
        validation = db.create_snapshot('zip_fiction', mode='validation')
        assert len(approved['episodes']) == manifest['accepted'] == 8
        assert len(validation['episodes']) == manifest['exported'] == 30
        write(out / 'approved_snapshot.json', approved);write(out / 'validation_snapshot.json', validation)
        assert db.load_snapshot(validation['snapshot_id']) == validation
        for entry, imported in zip(manifest['records'], new_imports):
            revision = db.read_revision(imported['revision_id'])
            sample = project_episode(validation, imported['revision_id'])
            plans = {backend: select_episode(sample, backend) for backend in ('rhythm', 'h06')}
            assert plans['rhythm']['steps'] == select_episode(sample)['steps']
            for plan in plans.values(): validate_plan(sample, plan)
            surface = render_surface(sample, plans['rhythm'])
            seal = db.save_projection(validation['snapshot_id'], 'rhythm:' + imported['revision_id'], dict(sample=sample, plan=plans['rhythm'], surface=surface))
            rows.append(dict(source_id=entry['id'], review_status_label=entry['review_status'], revision=revision,
                             sample=sample, plans=plans, surface=surface, projection_seal=seal))
        summer = None
        if args.summer_json:
            raw = args.summer_json.read_bytes();doc = strict_json_loads(raw.decode('utf-8-sig'))
            imp = db.import_document(doc, 'summer_fixture', 'fictional', source_bytes=raw, source_name=str(args.summer_json))
            ep = db.read_revision(imp['revision_id']);by = {a['local_id']: a for a in ep['atoms']}
            assert len(ep['atoms']) == 44 and len(ep['links']) == 50
            assert by['P1']['execution_status'] == 'completed' and by['P2']['execution_status'] == by['P3']['execution_status'] == 'desired'
            assert any(l['src'] == by['Q1']['atom_id'] and l['dst'] == by['F9']['atom_id'] and l['relation'] == 'answer' for l in ep['links'])
            assert not any(l['relation'] == 'requires_context' for l in ep['links'])
            assert db.export_document(imp['revision_id']) == doc
            summer = dict(atoms=44, links=50, exact_roundtrip=True, future_status_preserved=True, question_answer_not_reversed=True, source_sha256=sha(args.summer_json))
        integrity = db.con.execute('PRAGMA integrity_check').fetchone()[0]
        foreign_keys = db.con.execute('PRAGMA foreign_key_check').fetchall()
        assert integrity == 'ok' and foreign_keys == []
    processor = prepare_inputs(rows, args.model_dir)
    write(out / 'prepared_inputs.json', [dict(source_id=r['source_id'], prepared=r['prepared']) for r in rows])
    alpha = build_alpha(validation, out, root / 'runtime/vendor/alpha.py')
    assert all(sha(p) == expected for p, expected in frozen.items())
    counts = collections.Counter(a['kind'] for r in rows for a in r['revision']['atoms'])
    origins = collections.Counter(a['origin'] for r in rows for a in r['revision']['atoms'])
    rhythmic = [r['plans']['rhythm'] for r in rows]
    maximum = max((len(list(group)) for p in rhythmic for _, group in itertools.groupby(p['steps'], key=lambda s: s['kind'])), default=0)
    audit = dict(status='pass', unit_tests_passed=test_result.testsRun, imported=len(rows), atoms=sum(counts.values()), links=sum(len(r['revision']['links']) for r in rows),
                 kinds=dict(counts), origins=dict(origins), roundtrips=len(rows), idempotent_reimports=len(rows),
                 approved_snapshot_count=len(approved['episodes']), validation_snapshot_count=len(validation['episodes']),
                 rhythm_operations=sum(len(p['steps']) for p in rhythmic), rhythm_deferred=sum(len(p['deferred_nodes']) for p in rhythmic),
                 rhythm_max_same_kind=maximum, h06_operations=sum(len(r['plans']['h06']['steps']) for r in rows),
                 h06_deferred=sum(len(r['plans']['h06']['deferred_nodes']) for r in rows), deterministic_replays=len(rows),
                 processor=processor, alpha=alpha, summer_fixture=summer, database_integrity=integrity, foreign_key_errors=0,
                 source_and_default_runtime_unchanged=True, new_model_calls=0, training=0, tts=0,
                 quality_status='not evaluated; content reviews inherited unchanged; output speech not generated', cpu_seconds=time.perf_counter()-started)
    write(out / 'review_packet.json', rows);write(out / 'technical_audit.json', audit)
    report(out, rows, audit)
    result = f'''# 記憶DB・30件検証結果

新Memory DBと互換アダプターを実装し、凍結した30件をCPUで通した。

- 30件・{audit['atoms']}断片・{audit['links']}参照を取込。全30件のJSON再出力一致、再取込重複0。
- 内容確認済み8件の通常snapshotと、全30件のvalidation専用snapshotを分離。修正待ち2件・未確認20件を勝手に承認していない。
- 新しいリズム選択器：{audit['rhythm_operations']}操作、保留{audit['rhythm_deferred']}断片、同色最大{maximum}連続。旧H06：{audit['h06_operations']}操作、保留{audit['h06_deferred']}断片。
- 既存αへ別DBとして30件投影し、30検索の候補・本文対応を確認。元namespaceと版はsidecarで対応。検索順位の意味品質は未評価。
- 公式CPU Processorで30件の実入力をtoken化・復元し、全文一致・切詰0。入力{processor['input_tokens_min']}〜{processor['input_tokens_max']}token、既存8192枠内に1536生成tokenの余地あり。
- 夏祭りは追加の構造検査素材。44断片・50参照、希望と実行済み、質問と答えの関係を確認した。30件の件数には含めない。
- SQLite整合性ok、外部キー違反0、元資料と既定RuntimeのSHA不変。

## 実装の範囲

別SQLiteへの取込、断片ごとの由来、根拠と参考資料の分離、不変版・対象hash付きreview、namespace分離、固定snapshot、α投影、旧H06と新rhythmへの個別接続、Surface入力まで。

モデル生成・学習・TTS・本番切替は0。表示した色列はCPU操作であって、実際の発話ではない。話し方の改善や、人間のような自然さを今回証明したわけではない。

新rhythm接続は既存の上限3/有効な途中列/明示保留を維持し、意味リンクを弱い候補優先・接続根拠として使う。requires_contextだけを強い順序制約とする。旧日本語による前提推定と調整済み順位重みはこの新経路では使わず、既存の一般priorを使う。既存実験と同じ操作順を再現する比較ではない。

未知の状態は保持または明示保留し、感情や出来事を数合わせで追加しない。参考namespaceはZIP本人の発話対象にしない。連続数上限と前提が両立しない場合は残りを保留する。

実装初回の単体検査は27件中2error（検査側のH06参照パス・一時SQLite接続のclose漏れ）。原因を確認して検査コードを修正し、再実行した。最終ログはtest_results.txtを参照。

30件の統合検査v1は公式Processor確認後、αのscikit-learn参照不足で終了1。v1のDBを保全し、保存済みharness_beta/dependenciesを明示して別runで再検査した。ダウンロード・モデル推論は0。
'''
    (out / 'result.md').write_text(result, encoding='utf-8')
    write(out / 'completion.json', dict(status='cpu_validation_complete', technical_audit_sha256=sha(out / 'technical_audit.json'),
          review_packet_sha256=sha(out / 'review_packet.json'), comparison_sha256=sha(out / 'comparison.html'),
          source_preserved=True, runtime_adopted=False, generated=False))
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == '__main__':
    main()
