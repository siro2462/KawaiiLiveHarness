import copy
import json
import tempfile
import unittest
from pathlib import Path
from quality_eval import analyze_retrieval, cluster, health, source_context
from quality_metrics import AXES, preference_summary, validate_label
from build_quality_report import build


class Tests(unittest.TestCase):
    def test_health_rejects_only_known_corruption_not_semantic_progress(self):
        good = {'topic': 'カレーの話', 'flow': ['出来事を振り返る', '感想を話す']}
        self.assertTrue(health(good)['accepted'])
        for plan in [dict(good, topic='{'), dict(good, flow=['{', '{']),
                     dict(good, topic='<h2>話'), dict(good, flow=['同じ', '同じ'])]:
            self.assertFalse(health(plan)['accepted'])
        self.assertTrue(health(dict(good, flow=['カレーを食べた', 'カレーが美味しかった']))['accepted'])
        self.assertTrue(health(dict(good, topic='「{」という記号の話'))['accepted'])

    def test_source_context_requires_exact_recent_and_no_hidden_cut(self):
        call = {'input_text': 'abREcentcd', 'recent': 'REcent', 'recent_span': [2, 8],
                'original_grounding': None, 'context_cut_tokens': 0}
        self.assertEqual(source_context(call)['prompt'], call['input_text'])
        with self.assertRaises(AssertionError):source_context(dict(call, recent='other'))
        with self.assertRaises(AssertionError):source_context(dict(call, context_cut_tokens=1))

    def test_retrieval_preserves_query_and_scores_without_claiming_causality(self):
        row = {'turn': 0, 'retrieval': {'ranked': [{'id': 'A', 'score': .9}, {'id': 'B', 'score': .8}],
               'top_id': 'A', 'query_text': 'q', 'threshold': .6, 'excluded_id': None}}
        result = analyze_retrieval([row])[0]
        self.assertEqual(result['display_turn'], 1)
        self.assertAlmostEqual(result['best_second_gap'], .1)
        self.assertTrue(result['alternative_above_threshold'])
        self.assertEqual(cluster('S1A'), cluster('S1N'))
        self.assertEqual(cluster('H01-REL'), cluster('H01-NONE'))

    def label(self, pair='p', kind='human', winner='right'):
        return {'pair_id': pair, 'rater_id': 'rater-1', 'reviewer_kind': kind, 'winner': winner,
                'scores': {s: {a: None for a in AXES} for s in ['left', 'right']},
                'unsupported_claims': {'left': None, 'right': None},
                'contradictions': {'left': None, 'right': None}, 'notes': ''}

    def test_missing_human_ratings_stay_pending_and_AI_is_separate(self):
        key = {'p': {'experiment': 'stop', 'case_id': 'c', 'cluster_id': 'g', 'left': 'A', 'right': 'B'}}
        summary = preference_summary([self.label(kind='AI_root')], key)
        self.assertEqual(summary['status'], 'human ratings pending')
        self.assertEqual(summary['experiments'], {})
        self.assertEqual(summary['AI_root_rows'], 1)

    def test_duplicate_or_unmapped_labels_fail(self):
        key = {'p': {'experiment': 'stop', 'case_id': 'c', 'cluster_id': 'g', 'left': 'A', 'right': 'B'}}
        with self.assertRaises(ValueError):preference_summary([self.label(), self.label()], key)
        with self.assertRaises(ValueError):validate_label(self.label('unknown'), key)
        bad = self.label(); bad['scores']['left']['naturalness'] = True
        with self.assertRaises(ValueError):validate_label(bad, key)

    def test_seeds_and_raters_do_not_inflate_case_or_cluster_counts(self):
        key = {}; labels = []
        for i in range(6):
            name = str(i)
            key[name] = {'experiment': 'stop', 'case_id': 'case' + str(i // 3),
                         'cluster_id': 'scene', 'left': 'A', 'right': 'B'}
            labels.append(self.label(name))
        summary = preference_summary(labels, key, bootstrap_samples=30)['experiments']['stop']
        self.assertEqual(summary['cases'], 2)
        self.assertEqual(summary['clusters'], 1)
        self.assertIsNone(summary['cluster_CI95'])
        self.assertEqual(summary['B_preference'], 1)

    def test_report_keeps_full_text_escapes_HTML_and_blind_hides_condition_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / 'baseline_audit.json').write_text('{}', encoding='utf8')
            pair = {'pair_id': 'stop:c:1', 'experiment': 'stop', 'case_id': 'c', 'cluster_id': 'g',
                    'A_text': '<h2>original</h2>', 'B_text': '続き。', 'context_recent': '前の話。',
                    'source_grounding': {'body': '元Memory'}, 'A_stop': 'SENTINEL_STOP', 'B_stop': 'token_cap',
                    'A_tokens': 12, 'B_tokens': 20, 'A_fact_flag': False, 'B_fact_flag': True}
            (out / 'comparisons.jsonl').write_text(json.dumps(pair, ensure_ascii=False) + '\n', encoding='utf8')
            self.assertEqual(build(out)['pairs'], 1)
            page = (out / 'blind_review.html').read_text(encoding='utf8')
            self.assertNotIn('SENTINEL_STOP', page)
            self.assertNotIn('A_fact_flag', page)
            self.assertIn('\\u003ch2>', page)
            self.assertIn('&lt;h2&gt;original&lt;/h2&gt;', (out / 'full_output_table.html').read_text(encoding='utf8'))
            self.assertEqual(json.loads((out / 'quality_metrics.json').read_text())['experiments'], {})


if __name__ == '__main__':unittest.main()
