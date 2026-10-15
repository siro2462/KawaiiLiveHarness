"""CPU factual rejection and permissiveness regressions; no model samples fabricated."""
import ast
import json
import unittest
from pathlib import Path
from fact_gate import check_text, check_plan, numeric

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / 'lora_v4_multibase/runs/offload_20261009/gemma4_26b_a4b'
BANK = json.loads((ROOT.parent / 'lora_v4_runtime_bc/runs/bc_consistency_10m_20261008/protocol.json').read_text(encoding='utf8'))['memory_bank']
BYID = {m['id']:m for m in BANK}


class Tests(unittest.TestCase):
    def assertAllowed(self, text, mid='S2B'):
        check = check_text(text, [BYID[mid]])
        self.assertTrue(check['accepted'], (text,check['issues']))

    def assertRejected(self, text, code, mid='S2B'):
        check = check_text(text, [BYID[mid]])
        self.assertFalse(check['accepted'], text)
        self.assertIn(code, {i['code'] for i in check['issues']}, check['issues'])

    def test_all_original_memories_are_self_consistent(self):
        for memory in BANK:
            with self.subTest(id=memory['id']):
                check = check_text(memory['body'], [memory])
                self.assertTrue(check['accepted'], check['issues'])

    def test_saved_eel_plans_rejected_even_when_use_memory_false(self):
        rows = [json.loads(s) for s in (OLD/'runtime_bc_10m/BC/io.jsonl').read_text(encoding='utf8').splitlines()]
        for turn in [3,5,6,22]:
            with self.subTest(log_turn=turn):
                check = check_plan(rows[turn]['plan'], rows[turn]['candidate'])
                self.assertFalse(check['accepted'], rows[turn]['plan'])

    def test_embedded_question_does_not_exempt_later_experience(self):
        self.assertRejected('合うのかなと思って、うなぎをカレーにかけて食べてみた。', 'unsupported_experience_entity')

    def test_source_entities_and_compound_phrases_are_permitted(self):
        for text in ['カレーを作った。','冷凍うどんにカレーをかけて食べた。',
                     'カレーうどんを食べたんだよね。','炊飯器のスイッチを押すのを忘れた。']:
            with self.subTest(text=text): self.assertAllowed(text)

    def test_opinion_questions_wishes_and_jokes_are_permitted(self):
        for text in ['甘めだったかな？','うなぎとカレーって合うのかな？',
                     'うなぎを食べたらどうなるんだろう？','うなぎを食べたいね。',
                     'うなぎを食べたかったんだよね。','冗談だけど宇宙でうなぎを食べた。']:
            with self.subTest(text=text): self.assertAllowed(text)

    def test_clear_now_absence_and_application_conflicts_rejected(self):
        self.assertRejected('今カレーを作っている。','past_event_recast_as_now')
        self.assertRejected('ご飯はちゃんとあった。','absence_reversed')
        self.assertRejected('うどんをカレーにかけて食べた。','source_application_reversed')

    def test_intention_not_promoted_to_complete(self):
        self.assertRejected('青い屋根の家を撮影した。','intention_became_completed','S3B')
        self.assertAllowed('青い屋根の家を撮影しようとした。','S3B')

    def test_numeric_units_and_kanji_normalization(self):
        self.assertEqual(numeric('1万2016'),12016)
        self.assertEqual(numeric('十'),10)
        self.assertAllowed('同じ看板の写真を10枚消した。','S3B')
        self.assertRejected('1万2016枚。えっ？','unsupported_concrete_quantity','S3B')
        self.assertRejected('三人にカレーを作ってあげた。','unsupported_concrete_quantity')

    def test_directions_bound_to_event(self):
        self.assertAllowed('東口に出てしまった。','S1A')
        self.assertRejected('西口に出てしまった。','event_location_changed','S1A')

    def test_swap_and_taste_conflicts(self):
        self.assertAllowed('砂糖を入れたつもりだったけど、塩だった。','S2A')
        self.assertAllowed('塩を入れたからしょっぱかった。','S2A')
        self.assertRejected('砂糖を入れた。','intended_object_as_actual','S2A')
        self.assertRejected('卵焼きは甘かった。','source_taste_reversed','S2A')

    def test_gold_plans_are_not_overblocked(self):
        tree = ast.parse((ROOT.parent/'lora_v4_planner_talk/evaluate.py').read_text(encoding='utf8'))
        gold = ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and
                                    any(isinstance(t,ast.Name) and t.id=='GOLD' for t in n.targets)))
        for mid,plan in gold.items():
            with self.subTest(mid=mid):
                check = check_plan(plan,[BYID[mid]])
                self.assertTrue(check['accepted'],check['issues'])

    def test_new_bath_experience_rejected_but_general_association_allowed(self):
        self.assertRejected('そのあと風呂に入った。','unsupported_experience_entity')
        self.assertAllowed('湯気を見るとお風呂みたいだよね。')

    def test_generic_application_and_color_in_independent_cpu_memories(self):
        memory={'id':'cpu:stew','body':'シチューを作った。パンにかけて食べた。'}
        self.assertFalse(check_text('パンをシチューにかけて食べた。',[memory])['accepted'])
        self.assertTrue(check_text('シチューをパンにかけて食べた。',[memory])['accepted'])
        memory={'id':'cpu:socks','body':'緑の靴下を買った。'}
        check=check_text('赤い靴下を買った。',[memory])
        self.assertIn('source_color_changed',{i['code'] for i in check['issues']})

    def test_explicit_causal_reversal(self):
        memory={'id':'cpu:causal','body':'写真が多かったので、同じ写真を十枚消した。'}
        self.assertTrue(check_text(memory['body'],[memory])['accepted'])
        check=check_text('同じ写真を十枚消したので、写真が多かった。',[memory])
        self.assertIn('source_cause_effect_reversed',{i['code'] for i in check['issues']})

    def test_total_quantity_inference_is_explicit_and_not_arbitrary(self):
        self.assertAllowed('合わせて三本になったね。','S4B')
        self.assertRejected('合わせて四本になったね。','unsupported_concrete_quantity','S4B')

    def test_wish_quantity_is_not_asserted_experience(self):
        self.assertAllowed('三人にカレーを作ってあげたかった。')


if __name__ == '__main__':
    unittest.main(verbosity=2)
