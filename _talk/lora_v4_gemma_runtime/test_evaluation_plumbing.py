"""CPU checks of evaluation-only branching, with no Gemma calls."""
import tempfile
import unittest
from pathlib import Path
from evaluation_cases import heldout_cases,challenge_cases
from run_real_evaluation import diagnostic_plan,single_speech
from test_review_integration import FakeModels,FakeEmbed,A,PLAN,FREE,UTTERANCES


class Tests(unittest.TestCase):
    def test_unused_material_has_six_independent_episodes_and_three_conditions(self):
        cases=heldout_cases()
        self.assertEqual(len(cases),18);self.assertEqual(len({c['id'] for c in cases}),18)
        for offset in range(0,18,3):
            related,none,unrelated=cases[offset:offset+3]
            self.assertEqual(related['candidate'],[related['oracle_memory']])
            self.assertEqual(none['candidate'],[])
            self.assertNotEqual(unrelated['candidate'][0],unrelated['oracle_memory'])
            self.assertEqual(len({c['recent'] for c in [related,none,unrelated]}),1)
        self.assertEqual(len(challenge_cases()),18)

    def test_schema_success_is_not_Memory_selection_success(self):
        case={'id':'cpu:REL','condition':'REL','recent':'始まりの雑談だよ。','candidate':[A],'expected_use_memory':True}
        result=diagnostic_plan(FakeModels(plans=[FREE]),case)
        self.assertTrue(result['schema_success']);self.assertFalse(result['selection_correct'])
        self.assertEqual(result['attempts'][0]['factual_validation']['status'],'not_checked')

    def test_context_policies_do_not_use_hidden_validation_sources(self):
        case={'id':'cpu:policy','recent':'始まりの雑談だよ。','candidate':[A]}
        with tempfile.TemporaryDirectory() as temp:
            rows=[]
            for policy in ['CURRENT_ALWAYS','DECLARED_ONLY']:
                rows.append(single_speech(FakeModels(talks=['そういうこともあるよね。']),FakeEmbed(),case,FREE,policy,20260925,Path(temp)/policy))
            always,declared=rows
            self.assertEqual(always['speech_context_after_retry']['grounding']['id'],A['id'])
            self.assertIsNone(declared['speech_context_after_retry']['grounding'])
            self.assertEqual(declared['plan_validation_against_actual_Talk_sources']['source_references'],[])

    def test_omitted_grounding_requires_revalidating_cached_false_Plan(self):
        case={'id':'cpu:policy','recent':'始まりの雑談だよ。','candidate':[A]}
        raw={**PLAN,'use_memory':False,'memory_id':None}
        with tempfile.TemporaryDirectory() as temp:
            row=single_speech(FakeModels(talks=['そういうこともあるよね。']),FakeEmbed(),case,raw,'DECLARED_ONLY',20260925,Path(temp)/'declared')
            self.assertIsNone(row['plan_adopted_for_first_attempt'])
            self.assertFalse(row['plan_validation_against_actual_Talk_sources']['accepted'])
            self.assertEqual(row['Event_Store_integrity'],'pass')

    def test_seed_diagnostic_uses_given_seed_and_same_frozen_context(self):
        case={'id':'cpu:seed','recent':'始まりの雑談だよ。','candidate':[A]}
        with tempfile.TemporaryDirectory() as temp:
            first=FakeModels(talks=[UTTERANCES[0]]);second=FakeModels(talks=[UTTERANCES[0]])
            single_speech(first,FakeEmbed(),case,PLAN,'CURRENT_ALWAYS',20260925,Path(temp)/'first')
            single_speech(second,FakeEmbed(),case,PLAN,'CURRENT_ALWAYS',20260926,Path(temp)/'second')
            self.assertEqual(first.talk_calls[0]['context'],second.talk_calls[0]['context'])
            self.assertEqual(second.talk_calls[0]['seed']-first.talk_calls[0]['seed'],1)


if __name__=='__main__':unittest.main(verbosity=2)
