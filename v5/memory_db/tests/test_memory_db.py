"""Behavioral checks at storage, revision, namespace and rendering boundaries."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from v5.memory_db import MemoryDB, SchemaError, ValidationError, strict_json_loads
from v5.memory_db.projection import project_episode, alpha_records, resolve_recall
from v5.memory_db.selector_adapter import select_episode, validate_plan, load_module
from v5.memory_db.surface import render_surface
from v5.memory_db.events import EventLog


def fixture():
    return {"形式": "talk_memory_input_draft.v1", "記憶": {
        "記憶ID": "test", "題名": "お祭り", "話の中心": "挑戦と希望", "素材区分": "創作",
        "場面": {"いつ": "不明"}, "不明なこと": ["年"], "補ってはいけないこと": ["再訪を実行済みにしない"],
        "出来事": [{"ID": "F1", "内容": "輪投げを3回して失敗した。", "原文根拠": []}],
        "望み・期待": [{"ID": "W1", "内容": "成功したい。", "原文根拠": []}],
        "反応": [{"ID": "R1", "内容": "悔しかった。", "対応ID": ["F1", "W1"], "短い言葉": "あーっ。", "原文根拠": []}],
        "考え・評価": [{"ID": "T1", "内容": "失敗も友達となら楽しいと思った。", "根拠ID": ["F1"], "原文根拠": []}],
        "疑問・推測": [{"ID": "Q1", "内容": "成功できるだろうかと思った。", "対応ID": ["F1"], "答えになる情報ID": ["F1"], "原文根拠": []}],
        "その後・今後": [{"ID": "P1", "内容": "来年も行きたい。", "状態": "希望。未実行", "原文根拠": []}]}}


class DBCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'memory.sqlite'
        self.db = MemoryDB(self.path)

    def tearDown(self):
        self.db.close();self.tmp.cleanup()

    def add(self, doc=None, namespace='zip', world='fictional'):
        return self.db.import_document(doc or fixture(), namespace, world)

    def accept(self, row):
        return self.db.review_revision(row['revision_id'], 'accepted', 'test_root', 'Test review', row['content_sha256'])


class StoreChecks(DBCase):
    def test_malformed_reference_rejected_before_writing(self):
        doc = fixture();doc['記憶']['反応'][0]['対応ID'] = [{'bad':'nested'}]
        with self.assertRaises(ValidationError):
            self.add(doc)
        self.assertEqual(self.db.con.execute('SELECT count(*) FROM episodes').fetchone()[0], 0)

    def test_unknown_projection_version_refused(self):
        row = self.add();snapshot = self.db.create_snapshot('zip', mode='validation', projection_version='future')
        with self.assertRaises(ValueError):
            project_episode(snapshot, row['revision_id'])

    def test_exact_roundtrip(self):
        doc = fixture();row = self.add(doc)
        self.assertEqual(self.db.export_document(row['revision_id']), doc)

    def test_reimport_is_noop_and_review_unchanged(self):
        row = self.add();self.accept(row)
        again = self.add()
        self.assertFalse(again['created']);self.assertEqual(row['revision_id'], again['revision_id'])
        self.assertEqual(self.db.read_revision(row['revision_id'])['review_status'], 'accepted')

    def test_revision_does_not_inherit_approval(self):
        old = self.add();self.accept(old)
        doc = fixture();doc['記憶']['出来事'][0]['内容'] = '輪投げを4回して失敗した。'
        new = self.add(doc)
        self.assertNotEqual(new['revision_id'], old['revision_id'])
        self.assertEqual(self.db.read_revision(new['revision_id'])['review_status'], 'unreviewed')
        self.assertEqual(self.db.create_snapshot('zip')['episodes'], [])

    def test_old_snapshot_survives_edit_and_review(self):
        row = self.add();self.accept(row);snapshot = self.db.create_snapshot('zip')
        doc = fixture();doc['記憶']['題名'] = '新しい版';self.add(doc)
        self.db.review_revision(row['revision_id'], 'changes_requested', 'root', 'later decision', row['content_sha256'])
        self.assertEqual(self.db.load_snapshot(snapshot['snapshot_id']), snapshot)

    def test_no_silent_initial_approval(self):
        with self.assertRaises(ValidationError):
            self.db.import_document(fixture(), 'zip', 'fictional', review_status='accepted')

    def test_review_hash_required(self):
        row = self.add()
        with self.assertRaises(ValidationError):
            self.db.review_revision(row['revision_id'], 'accepted', 'root', 'note', 'wrong')

    def test_existing_legacy_database_refused_without_change(self):
        path = Path(self.tmp.name) / 'legacy.sqlite'
        with sqlite3.connect(path) as c:
            c.execute('CREATE TABLE memory(id INTEGER)');c.commit()
        c.close()
        before = path.read_bytes()
        with self.assertRaises(SchemaError):
            MemoryDB(path)
        self.assertEqual(path.read_bytes(), before)

    def test_transaction_rolls_back_late_failure(self):
        self.db.con.execute("CREATE TRIGGER force_fail BEFORE INSERT ON atom_links BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.add()
        for table in ('episodes', 'revisions', 'atoms', 'sources', 'atom_evidence', 'atom_links'):
            self.assertEqual(self.db.con.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)

    def test_namespace_external_id_does_not_collide(self):
        a = self.add();b = self.add(namespace='reference', world='reference')
        self.assertNotEqual(a['episode_id'], b['episode_id'])
        with self.assertRaises(ValidationError):
            self.db.create_snapshot('zip', [a['revision_id'], b['revision_id']], mode='validation')

    def test_world_cannot_change_in_place(self):
        self.add()
        with self.assertRaises(ValidationError):
            self.add(world='reference')

    def test_cross_revision_link_rejected_by_db(self):
        a = self.add();b = self.add(namespace='reference', world='reference')
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.con.execute("INSERT INTO atom_links(revision_id,src,dst,relation,origin,review_status,evidence_json) VALUES(?,?,?,?,?,?,?)", (a['revision_id'], a['revision_id'] + ':F1', b['revision_id'] + ':R1', 'reaction', 'test', 'explicit_validated_unreviewed', '{}'))

    def test_immutable_content(self):
        row = self.add()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.con.execute("UPDATE atoms SET content='changed' WHERE revision_id=?", (row['revision_id'],))

    def test_bad_json_and_unknown_codes_rejected(self):
        for txt in ('{"x":1,"x":2}', '{"x":NaN}'):
            with self.assertRaises(ValidationError): strict_json_loads(txt)
        doc = fixture();doc['記憶']['出来事'][0]['epistemic'] = 'definitely_real'
        with self.assertRaises(ValidationError): self.add(doc)

    def test_dangling_duplicate_cycle_rejected(self):
        doc = fixture();doc['記憶']['反応'][0]['対応ID'] = ['absent']
        with self.assertRaises(ValidationError): self.add(doc)
        doc = fixture();doc['記憶']['反応'][0]['ID'] = 'F1'
        with self.assertRaises(ValidationError): self.add(doc)
        doc = fixture();doc['記憶']['関係'] = [{'起点ID': 'F1', '終点ID': 'R1', '関係': 'requires_context'}, {'起点ID': 'R1', '終点ID': 'F1', '関係': 'requires_context'}]
        with self.assertRaises(ValidationError): self.add(doc)

    def test_source_bytes_must_match(self):
        with self.assertRaises(ValidationError):
            self.db.import_document(fixture(), 'zip', 'fictional', source_bytes=b'{}')

    def test_source_evidence_and_style_separated(self):
        doc = fixture();text = doc['記憶']['出来事'][0]['内容']
        doc['元DB'] = {'id': 1, 'episode': text, 'episode_sha256': hashlib.sha256(text.encode()).hexdigest()}
        doc['参考'] = {'path': 'ref.yaml', '短い引用': ['参考の話し方']}
        doc['記憶']['出来事'][0].update(由来='元記憶', 原文根拠=[text])
        row = self.add(doc);rev = self.db.read_revision(row['revision_id'])
        self.assertEqual(len(rev['atoms'][0]['evidence']), 1)
        self.assertEqual(rev['atoms'][0]['evidence'][0]['role'], 'original_evidence')
        self.assertIn('style_reference', {s['role'] for s in rev['sources']})

    def test_explicit_validation_needed_for_drafts(self):
        self.add()
        self.assertEqual(len(self.db.create_snapshot('zip')['episodes']), 0)
        self.assertEqual(len(self.db.create_snapshot('zip', mode='validation')['episodes']), 1)

    def test_reopen_and_projection_cache(self):
        self.add();snap = self.db.create_snapshot('zip', mode='validation')
        p = self.db.save_projection(snap['snapshot_id'], 'test', {'value': 1})
        self.assertEqual(p, self.db.save_projection(snap['snapshot_id'], 'test', {'value': 1}))
        with MemoryDB(self.path, create=False) as second:
            self.assertEqual(second.load_snapshot(snap['snapshot_id']), snap)


class AdapterChecks(DBCase):
    def test_recall_candidate_is_pinned_to_snapshot(self):
        row = self.add();snap = self.db.create_snapshot('zip',mode='validation')
        record = alpha_records(snap)[0]
        candidate = dict(id=record['id'],authority=record['authority'])
        self.assertEqual(resolve_recall(snap,candidate)['provenance']['revision_id'],row['revision_id'])
        self.accept(row);approved = self.db.create_snapshot('zip')
        with self.assertRaises(ValueError):
            resolve_recall(approved,candidate)
        candidate['authority']='reference_transcript_unverified'
        with self.assertRaises(ValueError):
            resolve_recall(snap,candidate)

    def test_empty_plan_cannot_request_surface(self):
        row = self.add(namespace='reference', world='reference')
        sample = project_episode(self.db.create_snapshot('reference',mode='validation'), row['revision_id'])
        with self.assertRaises(ValueError):
            render_surface(sample, select_episode(sample))

    def test_event_log_reopen_and_history_without_memory_promotion(self):
        row = self.add();snapshot = self.db.create_snapshot('zip',mode='validation')
        sample = project_episode(snapshot,row['revision_id']);plan = select_episode(sample)
        path = Path(self.tmp.name)/'events.sqlite'
        before = self.db.export_document(row['revision_id'])
        with EventLog(path,snapshot) as log:
            seq, surface = log.record_input(row['revision_id'],plan)
            self.assertEqual(surface['payload']['history'],[])
            log.record_output(seq,'CPU検査用の模擬本文。',delivered=True)
            with self.assertRaises(ValueError):
                log.record_output(seq,'二重登録。',delivered=True)
        with EventLog(path,snapshot) as log:
            seq2, surface2 = log.record_input(row['revision_id'],plan)
            self.assertEqual(surface2['payload']['history'][0]['text'],'CPU検査用の模擬本文。')
            self.assertFalse(surface2['payload']['history'][0]['memory_promotion'])
            log.record_output(seq2,'保留された検査用本文。',delivered=False)
            self.assertEqual(len(log.recent()),1)
        self.assertEqual(self.db.export_document(row['revision_id']),before)
        self.assertEqual(self.db.con.execute('SELECT count(*) FROM revisions').fetchone()[0],1)
        wrong = copy.deepcopy(snapshot);wrong['namespace']='wrong'
        with self.assertRaises(ValueError):
            EventLog(path,wrong)

    def test_event_log_does_not_modify_legacy_file(self):
        path=Path(self.tmp.name)/'old_events.sqlite'
        c=sqlite3.connect(path);c.execute('CREATE TABLE events(seq INTEGER,kind TEXT,payload TEXT)');c.commit();c.close()
        before=path.read_bytes();row=self.add();snapshot=self.db.create_snapshot('zip',mode='validation')
        with self.assertRaises(ValueError):
            EventLog(path,snapshot)
        self.assertEqual(path.read_bytes(),before)

    def test_vendor_source_hashes(self):
        root=Path(__file__).resolve().parents[1]/'vendor'
        manifest=json.loads((root/'manifest.json').read_text('utf-8'))
        # The original vendor stays exact; the hook variant is explicitly separate.
        self.assertEqual(hashlib.sha256((root/'selector.py').read_bytes()).hexdigest(),manifest['upstream_sha256'])
        self.assertEqual(hashlib.sha256((root/'adapted_selector.py').read_bytes()).hexdigest(),manifest['adapted_sha256'])

    def prepared(self, doc=None, namespace='zip', world='fictional'):
        row = self.add(doc, namespace, world)
        snap = self.db.create_snapshot(namespace, mode='validation')
        return snap, project_episode(snap, row['revision_id'])

    def test_no_fact_required_for_desire_episode(self):
        doc = fixture();m = doc['記憶']
        for key in ('出来事', '反応', '考え・評価', '疑問・推測', 'その後・今後'):m[key] = []
        _, sample = self.prepared(doc)
        for backend in ('rhythm', 'h06'):
            self.assertEqual(len(select_episode(sample, backend)['steps']), 1)

    def test_answer_relation_not_reversed_into_requirement(self):
        _, sample = self.prepared()
        by = {n['local_id']: n for n in sample['nodes']}
        self.assertTrue(any(e['src'] == by['Q1']['id'] and e['dst'] == by['F1']['id'] and e['relation'] == 'answer' for e in sample['edges']))
        self.assertEqual(by['Q1']['requires'], [])
        plan = select_episode(sample)
        self.assertFalse(any(c['after'] == by['Q1']['id'] and c['before'] == by['F1']['id'] for c in plan['constraints']))

    def test_unknown_status_retained_and_deferred(self):
        doc = fixture();doc['記憶']['その後・今後'][0]['状態'] = '判別できない記述'
        _, sample = self.prepared(doc);plan = select_episode(sample)
        mid = next(n['id'] for n in sample['nodes'] if n['local_id'] == 'P1')
        self.assertIn(mid, {d['memory_id'] for d in plan['deferred_nodes']})
        self.assertNotIn(mid, {s['memory_id'] for s in plan['steps']})

    def test_reference_is_not_zip_speech(self):
        snap, sample = self.prepared(namespace='reference', world='reference')
        self.assertEqual(select_episode(sample)['steps'], [])
        self.assertEqual(alpha_records(snap)[0]['namespace'], 'reference')

    def test_surface_keeps_plan_status_origin_and_hint(self):
        _, sample = self.prepared();plan = select_episode(sample);out = render_surface(sample, plan)
        text = json.loads(out['user_prompt'].split('【記憶と操作の入力】\n')[1])
        self.assertEqual(text, out['payload'])
        p = next(n for n in sample['nodes'] if n['local_id'] == 'P1')
        emitted = next(x for x in text['operations'] if x['memory_id'] == p['id'])
        self.assertEqual(emitted['execution_status'], 'desired');self.assertNotEqual(emitted['kind'], 'F')
        self.assertTrue(all(x['world_scope'] == 'fictional' for x in text['operations']))
        self.assertTrue(any(x['utterance_hint'] == 'あーっ。' for x in text['operations']))

    def test_semantic_fields_cannot_be_changed_after_selection(self):
        _, sample = self.prepared();plan = select_episode(sample)
        plan['steps'][0]['content'] = '勝手な追加'
        with self.assertRaises(ValueError): render_surface(sample, plan)

    def test_independent_sessions_and_array_order(self):
        _, a = self.prepared();p = select_episode(a)
        b = copy.deepcopy(a);b['nodes'].reverse();b['edges'].reverse()
        self.assertEqual(select_episode(b)['steps'], p['steps'])
        select_episode(a, 'h06')
        self.assertEqual(select_episode(a)['steps'], p['steps'])

    def test_missing_rhythm_capacity_defers_without_invention(self):
        doc = fixture();m = doc['記憶']
        for key in ('望み・期待', '反応', '考え・評価', '疑問・推測', 'その後・今後'):m[key] = []
        m['出来事'] = [{'ID': f'F{i}', '内容': f'{i}枚の写真があった。', '原文根拠': []} for i in range(5)]
        _, sample = self.prepared(doc);plan = select_episode(sample)
        self.assertEqual(len(plan['steps']), 3);self.assertEqual(len(plan['deferred_nodes']), 2)

    def test_h06_original32_replay(self):
        root = Path(__file__).resolve().parents[2]
        evidence = root / 'evidence/stripe_surface_abc_h06_20261027'
        module = load_module(evidence / 'reference/stripe_engine/engine.py')
        actual = module.Engine(seed=17, mode='state', allow_cross=False).run('H06')
        expected = json.loads((evidence / 'steps32.json').read_text('utf-8-sig'))
        self.assertEqual([(s['node_id'], s['operation']) for s in actual], [(s['memory_id'], s['operation']) for s in expected])


if __name__ == '__main__':
    unittest.main()
