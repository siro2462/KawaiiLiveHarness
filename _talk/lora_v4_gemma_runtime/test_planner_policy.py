"""Regression checks use saved Gemma failures; synthetic successes are labelled tests."""
import copy
import json
import unittest
from pathlib import Path
from planner_policy import CONTRACT, SCHEMA_INSTRUCTION, obtain_plan, parse_plan

OLD = Path(__file__).resolve().parent.parent / 'lora_v4_multibase/runs/offload_20261009/gemma4_26b_a4b/runtime_bc_10m'


def first(arm):
    return json.loads((OLD / arm / 'io.jsonl').read_text(encoding='utf-8').splitlines()[0])


def inp(record):
    original = record['planner_attempts'][0]['input_text']
    state = json.loads(original.split('【現在状態】\n', 1)[1].split('\n\n【Memory候補】', 1)[0])
    result = {'recent': record['recent_input_text'], 'current_state': state,
              'memory_candidates': record['candidate'], 'previous_plan': record['active_bundle_before']['plan']}
    assert CONTRACT['planner_prompt'](result) == original
    return result


class Tests(unittest.TestCase):
    def test_saved_failures_gain_different_retry_input_without_fact_mutation(self):
        for arm in ['B_CONTROL', 'BC_IMPROVED']:
            with self.subTest(arm=arm):
                saved = first(arm)
                original = inp(saved)
                before = copy.deepcopy(original)
                calls = []
                def generate(prompt, recent, retry):
                    calls.append(prompt)
                    return {'text': saved['planner_attempts'][0]['text'], 'input_text': prompt}
                result, attempts = obtain_plan(generate, original)
                self.assertIsNone(result)
                self.assertEqual(len(attempts), 2)
                self.assertNotEqual(calls[0], calls[1])
                self.assertIn('memory_id', calls[1])
                self.assertIn('plan_validation_feedback', calls[1])
                self.assertEqual(original, before)
                self.assertTrue(all(a['factual_validation']['status'] == 'not_checked' for a in attempts))

    def test_inner_valid_json_is_rejected_in_broken_outer_or_prefix(self):
        original = inp(first('B_CONTROL'))
        # CPU-authored test object, not an LLM output or quality evaluation.
        good = {'use_memory': True, 'memory_id': 'S2B', 'topic': 'ご飯がなかった時の話',
                'flow': ['出来事を振り返る', 'その時の感想を話す']}
        def generate(prompt, recent, retry):
            self.assertTrue(prompt.startswith(SCHEMA_INSTRUCTION))
            return {'text': '壊れた { ' + json.dumps(good, ensure_ascii=False) + ' trailing'}
        result, attempts = obtain_plan(generate, original)
        self.assertIsNone(result)
        self.assertEqual(len(attempts), 2)
        self.assertTrue(all(a['substring_rescue'] is False for a in attempts))

    def test_missing_id_is_not_inferred_from_single_candidate(self):
        original = inp(first('B_CONTROL'))
        bad = {'use_memory': True, 'topic': 'ご飯の話', 'flow': ['振り返る', '感想を話す']}
        result, attempts = obtain_plan(lambda *args: {'text': json.dumps(bad)}, original)
        self.assertIsNone(result)
        self.assertEqual(len(attempts), 2)

    def test_unknown_id_duplicate_key_and_wrong_type_are_rejected(self):
        original = inp(first('B_CONTROL'))
        bads = [
            '{"use_memory":true,"memory_id":"not-a-candidate","topic":"話","flow":["a","b"]}',
            '{"use_memory":true,"memory_id":"S2B","topic":"話","topic":"別","flow":["a","b"]}',
            '{"use_memory":"true","memory_id":"S2B","topic":"話","flow":["a","b"]}',
        ]
        for raw in bads:
            with self.subTest(raw=raw):
                result, attempts = obtain_plan(lambda *args: {'text': raw}, original)
                self.assertIsNone(result)
                self.assertEqual(len(attempts), 2)

    def test_a_valid_retry_is_adopted_once(self):
        original = inp(first('B_CONTROL'))
        raw = first('B_CONTROL')['planner_attempts'][0]['text']
        good = {'use_memory': False, 'memory_id': None, 'topic': '料理の感想', 'flow': ['感想を話す', '自然につなぐ']}
        prompts = []
        def generate(prompt, recent, retry):
            prompts.append(prompt)
            return {'text': raw if retry == 0 else json.dumps(good)}
        result, attempts = obtain_plan(generate, original)
        self.assertEqual(result, good)
        self.assertEqual(len(attempts), 2)
        self.assertIn('plan_validation_feedback', prompts[1])

    def test_whole_json_only_and_whitespace_is_accepted(self):
        good = {'use_memory': True, 'memory_id': 'S2B', 'topic': '振り返る', 'flow': ['出来事', '感想']}
        raw = json.dumps(good, ensure_ascii=False)
        self.assertEqual(parse_plan(' \n' + raw + '\n ', ['S2B']), good)
        for bad in ['<h1>' + raw + '</h1>', raw + raw, '```json\n' + raw + '\n```']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_plan(bad, ['S2B'])

    def test_use_memory_relation_and_blank_values_are_rejected(self):
        for use, mid, topic in [(True, None, '話'), (False, 'S2B', '話'), (False, None, ' ' )]:
            with self.subTest(use=use,mid=mid,topic=topic), self.assertRaises(ValueError):
                parse_plan(json.dumps({'use_memory':use,'memory_id':mid,'topic':topic,'flow':['a','b']}), ['S2B'])

    def test_fact_failure_does_not_become_a_valid_plan(self):
        original = inp(first('B_CONTROL'))
        good = {'use_memory': True, 'memory_id': 'S2B', 'topic': '経験', 'flow': ['うなぎを食べた', '振り返る']}
        result, attempts = obtain_plan(lambda *args: {'text':json.dumps(good)}, original,
            fact_check=lambda *args: {'accepted':False,'feedback':'元Memoryのうどんを変えない'})
        self.assertIsNone(result)
        self.assertTrue(all(a['schema_valid'] for a in attempts))
        self.assertTrue(all(not a['factual_validation']['accepted'] for a in attempts))


if __name__ == '__main__':
    unittest.main(verbosity=2)
