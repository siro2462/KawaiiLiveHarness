"""CPU fake-model E2E; these authored utterances are not model quality results."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alpha_contract import resolve_memories, validate_proposal
from context_runtime import MemoryStore, GroundedPlanStore, speech_context, protected_ids, shrink_recent_context
from fact_gate import check_plan, check_text
from generation_errors import ConstraintGenerationError, ContextBudgetError
from original_runtime import Runtime
from planner_policy import CONTRACT, obtain_plan
from runtime_engine import Arm

A={'id':'cpu:A','body':'カレーを作った。冷凍うどんにかけて食べた。'}
B={'id':'cpu:B','body':'赤い靴下を買った。'}
PLAN={'use_memory':True,'memory_id':A['id'],'topic':'カレーを作った話','flow':['カレーを作った','その時の感想']}
FREE={'use_memory':False,'memory_id':None,'topic':'思ったこと','flow':['感想','自然な連想']}
UTTERANCES=['カレーを作ったんだよね。','冷凍うどんにかけて食べた。','ちょっと慌てちゃったんだよ。','そういうこともあるよね。','のんびりするのも好きだなあ。']


def write(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


class FakeModels:
    def __init__(self, plans=None, talks=None, default_plan=PLAN, default_talk='そういうこともあるよね。'):
        self.plans=list(plans or []);self.talks=list(talks or [])
        self.default_plan=default_plan;self.default_talk=default_talk
        self.planner_calls=[];self.talk_calls=[]

    def planner(self,prompt,recent,ids,retry):
        self.planner_calls.append({'prompt':prompt,'recent':recent,'ids':list(ids),'retry':retry})
        value=self.plans.pop(0) if self.plans else self.default_plan
        if isinstance(value,Exception):raise value
        return {'text':json.dumps(value,ensure_ascii=False) if isinstance(value,dict) else value,
                'input_text':prompt,'decoded_input':prompt,'fake_model':True}

    def talk(self,context,seed,retry_note):
        self.talk_calls.append({'context':copy.deepcopy(context),'seed':seed,'retry_note':retry_note})
        value=self.talks.pop(0) if self.talks else self.default_talk
        if isinstance(value,Exception):raise value
        return {'text':value,'input_text':retry_note+context['prompt'],'fake_model':True}


class FakeEmbed:
    def embed(self,kind,texts):
        # Test-only passage vectors; no E5 accuracy or semantic quality claim.
        return [[1.0 if i==hashlib.sha256(text.encode()).digest()[0]%128 else 0.0 for i in range(128)] for text in texts]


class Integration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def arm(self,name='GUARDED',fixed=A['id'],target=2700):
        arm=Arm(name,Path(self.tmp.name)/('arm'+str(len(list(Path(self.tmp.name).iterdir())))),
                '始まりの雑談だよ。',[A,B],write,fixed_id=fixed,target=target)
        self.addCleanup(lambda:arm.log.close() if not arm.log.closed else None)
        self.addCleanup(arm.rt.close)
        return arm

    def step(self,arm,models):return arm.step(models,FakeEmbed(),[A,B],[[1.,0.],[0.,1.]])

    def test_search_miss_clears_selection_without_deleting_available_memory(self):
        arm=self.arm(fixed=None);models=FakeModels(plans=[PLAN,FREE],talks=UTTERANCES[:1]+['のんびりするのも好きだなあ。'])
        with patch('runtime_engine.ranked_candidate',side_effect=[([A],{'top_id':A['id']}),([],{'top_id':None})]):
            self.step(arm,models);arm.refresh_reason='test_new_lookup'
            record=self.step(arm,models)
        self.assertIsNone(arm.memory.current);self.assertIn(A['id'],arm.memory.bank)
        self.assertEqual(record['factual_source_references'],[])
        self.assertIsNone(record['speech_context']['grounding'])
        self.assertNotIn(A['body'],record['speech_context']['prompt'])
        self.assertFalse(record['last_valid_fallback'])

    def test_active_plan_continuation_does_not_trigger_a_search_miss(self):
        arm=self.arm(fixed=None);models=FakeModels(talks=UTTERANCES[:2])
        with patch('runtime_engine.ranked_candidate',return_value=([A],{'top_id':A['id']})) as search:
            self.step(arm,models);self.step(arm,models)
        self.assertEqual(search.call_count,1);self.assertEqual(arm.memory.current['id'],A['id'])

    def test_archived_source_cannot_validate_plan_for_different_Talk_memory(self):
        arm=self.arm();models=FakeModels(plans=[PLAN,dict(PLAN,use_memory=False,memory_id=None),dict(PLAN,use_memory=False,memory_id=None)],
                                      talks=[UTTERANCES[0],B['body']])
        self.step(arm,models);arm.fixed_id=B['id'];arm.refresh_reason='test_source_change'
        record=self.step(arm,models)
        self.assertIsNone(record['plan']);self.assertFalse(record['last_valid_fallback'])
        self.assertEqual([r['id'] for r in record['factual_source_references']],[B['id']])
        self.assertTrue(all(not p['factual_validation']['accepted'] for p in record['planner_attempts']))
        self.assertNotIn(A['body'],record['speech_context']['prompt'])

    def test_fact_bundle_requires_exact_source_set(self):
        store=GroundedPlanStore();free=copy.deepcopy(FREE)
        with self.assertRaises(ValueError):store.stage(free,B,0,check_plan(free,[A,B]))
        store.stage(free,B,0,check_plan(free,[B]));self.assertEqual(store.commit()['grounding']['id'],B['id'])

    def test_false_flag_is_logged_separately_from_grounding_and_selection_quality(self):
        arm=self.arm();models=FakeModels(plans=[FREE],talks=[UTTERANCES[0]])
        record=self.step(arm,models)
        self.assertFalse(record['memory_selection_observation']['declared_use_memory'])
        self.assertEqual(record['memory_selection_observation']['Talk_grounding_ids'],[A['id']])
        self.assertIn('unreviewed',record['memory_selection_observation']['selection_correctness'])

    def test_initial_schema_failure_still_calls_grounded_planless_Talk(self):
        arm=self.arm();models=FakeModels(plans=['broken','broken'],talks=[UTTERANCES[0]])
        record=self.step(arm,models)
        self.assertEqual(len(models.planner_calls),2);self.assertEqual(len(models.talk_calls),1)
        self.assertEqual(record['speech_context']['mode'],'grounded_planless')
        self.assertEqual(record['played_text'],UTTERANCES[0])

    def test_bounded_constraint_failure_falls_back_without_inventing_a_plan(self):
        arm=self.arm();models=FakeModels(plans=[ConstraintGenerationError('empty'),ConstraintGenerationError('empty')],talks=[UTTERANCES[0]])
        record=self.step(arm,models)
        self.assertEqual(len(models.planner_calls),2);self.assertIsNone(record['plan'])
        self.assertEqual(record['planner_attempts'][0]['generation_error']['code'],'schema_constraint_failure')
        self.assertTrue(record['played_text'])

    def test_length_retry_removes_only_left_recent_and_preserves_memory(self):
        arm=self.arm();models=FakeModels(plans=[ValueError('maximum context length exceeded'),PLAN],talks=[UTTERANCES[0]])
        self.step(arm,models)
        first,second=models.planner_calls
        self.assertLess(len(second['recent']),len(first['recent']))
        self.assertIn(A['body'],first['prompt']);self.assertIn(A['body'],second['prompt'])
        self.assertEqual(first['ids'],second['ids'])

    def test_protected_context_error_does_not_delete_memory_or_repeat_Planner(self):
        arm=self.arm();models=FakeModels(plans=[ContextBudgetError('protected source too large')],talks=[UTTERANCES[0]])
        record=self.step(arm,models)
        self.assertEqual(len(models.planner_calls),1)
        self.assertEqual(record['speech_context']['grounding']['body'],A['body'])
        self.assertEqual(record['speech_context']['mode'],'grounded_planless')

    def test_model_device_failure_halts_without_Talk_or_retry(self):
        arm=self.arm();models=FakeModels(plans=[RuntimeError('HIP error: device-side assert')])
        record=self.step(arm,models)
        self.assertEqual(arm.status,'halted_generation_error');self.assertEqual(len(models.planner_calls),1)
        self.assertEqual(len(models.talk_calls),0);self.assertEqual(record['played_chars'],0)
        with self.assertRaises(ValueError):self.step(arm,models)

    def test_unexpected_programming_exception_is_audited_and_reraised(self):
        arm=self.arm();models=FakeModels(plans=[TypeError('implementation bug')])
        with self.assertRaises(TypeError):self.step(arm,models)
        self.assertEqual(arm.status,'failed_implementation')
        row=json.loads((arm.dir/'io.jsonl').read_text(encoding='utf8').splitlines()[-1])
        self.assertEqual(row['fatal_error']['code'],'unexpected_implementation_error')
        self.assertIn('implementation bug',row['planner_attempts'][0]['generation_error']['message'])

    def test_fallback_keeps_original_expiry_and_never_resurrects_after_it(self):
        arm=self.arm();models=FakeModels(plans=[PLAN,'bad','bad','bad','bad'],talks=UTTERANCES[:4])
        self.step(arm,models);arm.refresh_reason='test_refresh'
        record=self.step(arm,models)
        self.assertTrue(record['last_valid_fallback']);self.assertEqual(arm.store.active['expires_before_turn'],3)
        self.step(arm,models);record=self.step(arm,models)
        self.assertFalse(record['last_valid_fallback']);self.assertIsNone(record['plan'])

    def test_Talk_fact_rejection_invalidates_plan_before_single_planless_retry(self):
        arm=self.arm();models=FakeModels(talks=['うなぎも美味しかったなあ。',UTTERANCES[0]])
        record=self.step(arm,models)
        self.assertEqual(len(models.talk_calls),2);self.assertIsNone(arm.store.last_valid)
        self.assertEqual(models.talk_calls[1]['context']['mode'],'grounded_planless')
        self.assertFalse(record['speech_attempts'][0]['playback_committed'])
        saved=[json.loads(x[0])['played_text'] for x in arm.rt.db.execute("SELECT body FROM events WHERE kind='played_speech'")]
        self.assertEqual(saved,[UTTERANCES[0]])

    def test_all_rejected_candidates_never_commit_or_keep_a_fallback_plan(self):
        arm=self.arm();models=FakeModels(talks=['<h1>bad</h1>','<h1>bad</h1>'])
        record=self.step(arm,models)
        self.assertEqual(len(record['speech_attempts']),2);self.assertIsNone(arm.store.last_valid)
        self.assertEqual(arm.rt.db.execute('SELECT COUNT(*) FROM events').fetchone()[0],0)

    def test_loop_discards_full_candidate_and_clears_all_plan_slots(self):
        arm=self.arm();models=FakeModels(talks=[UTTERANCES[0],UTTERANCES[0]])
        self.step(arm,models);record=self.step(arm,models)
        self.assertEqual(record['failure'],'repetition');self.assertEqual(len(arm.played),1)
        self.assertIsNone(arm.store.active);self.assertIsNone(arm.store.pending);self.assertIsNone(arm.store.last_valid)
        self.assertEqual(arm.blocked,A['id'])

    def test_recent_three_and_SQLite_retain_all_simulated_playback(self):
        arm=self.arm();models=FakeModels(talks=UTTERANCES)
        records=[self.step(arm,models) for _ in range(5)]
        self.assertEqual(records[-1]['speech_context']['recent'],'\n'.join(UTTERANCES[1:4]))
        self.assertEqual(arm.rt.db.execute('SELECT COUNT(*) FROM memory').fetchone()[0],5)
        self.assertTrue(all(json.loads(x[0])['facts_verified'] is False for x in arm.rt.db.execute('SELECT body FROM memory')))

    def test_simulated_partial_prefix_only_survives_database_reopen(self):
        arm=self.arm(target=5);models=FakeModels(talks=[UTTERANCES[0]])
        record=self.step(arm,models);self.assertEqual(record['played_text'],UTTERANCES[0][:5])
        self.assertIsNone(arm.store.last_valid)
        db=Runtime(arm.dir/'events.sqlite')
        try:
            rows=db.db.execute("SELECT body FROM events WHERE kind='played_speech'").fetchall()
            value=json.loads(rows[0][0]);self.assertEqual(value['playback'],'simulated')
            self.assertFalse(value['complete']);self.assertEqual(value['played_text'],UTTERANCES[0][:5])
        finally:db.close()

    def test_zero_playback_stops_at_original_limit_without_automatic_restart(self):
        arm=self.arm();models=FakeModels(default_talk='')
        for _ in range(30):self.step(arm,models)
        self.assertEqual(arm.status,'stalled_zero_playback');self.assertEqual(len(models.talk_calls),60)
        self.assertEqual(arm.total,0);self.assertIsNone(arm.store.last_valid)
        with self.assertRaises(ValueError):self.step(arm,models)

    def test_alpha_single_source_is_accepted_by_Planner_and_multi_is_rejected(self):
        bank={A['id']:A['body'],B['id']:B['body']}
        proposal={'version':'alpha.v0.1','decision':'propose','trigger':{'kind':'external_event','event_id':'cpu:test'},
                  'memory_ids':[A['id']],'topic_hint':'自由な思い出し'}
        sources=resolve_memories(proposal,bank)
        CONTRACT['validate_input']({'recent':'開始','current_state':{},'memory_candidates':sources,'previous_plan':None})
        with self.assertRaises(ValueError):validate_proposal(dict(proposal,memory_ids=list(bank)),bank)
        self.assertEqual(resolve_memories(dict(proposal,decision='wait',memory_ids=[],topic_hint=None),bank),[])

    def test_rule_pass_is_explicitly_unverified(self):
        result=check_text('うなぎの思い出だね。',[A])
        self.assertEqual(result['semantic_verdict'],'unverified')
        self.assertEqual(result['rule_verdict'],'no_conflict_detected')
        self.assertTrue(result['known_blind_spots'])

    def test_explicit_time_and_same_event_negation_with_positive_controls(self):
        for text in ['七時にカレーを作った。','昨日の朝にカレーを作った。','カレーを作らなかった。','うなぎも美味しかったなあ。']:
            with self.subTest(text=text):self.assertFalse(check_text(text,[A])['accepted'])
        dated={'id':'cpu:time','body':'七時にカレーを作った。'}
        self.assertTrue(check_text('7時にカレーを作った。',[dated])['accepted'])
        self.assertTrue(check_text('甘めだったかな？',[A])['accepted'])
        self.assertTrue(check_text('ご飯は炊かなかった。',[dict(A,body=A['body']+'ご飯がなかった。')])['accepted'])

    def test_Talk_device_failure_halts_without_retry_or_commit(self):
        arm=self.arm();models=FakeModels(talks=[RuntimeError('CUDA error: illegal memory access')])
        record=self.step(arm,models)
        self.assertEqual(arm.status,'halted_generation_error');self.assertEqual(len(models.talk_calls),1)
        self.assertEqual(record['played_chars'],0);self.assertIsNone(arm.store.last_valid)

    def test_Talk_length_retry_keeps_exact_grounding_and_plan(self):
        arm=self.arm();models=FakeModels(talks=[ValueError('input sequence length exceeds maximum'),UTTERANCES[0]])
        self.step(arm,models)
        first,second=[r['context'] for r in models.talk_calls]
        self.assertLess(len(second['recent']),len(first['recent']))
        self.assertEqual(first['grounding'],second['grounding'])
        self.assertEqual(first['prompt'][:first['recent_span'][0]],second['prompt'][:second['recent_span'][0]])

    def test_protected_token_cut_uses_explicit_recent_section_with_duplicate_text(self):
        from tokenizers import Tokenizer
        tokenizer_path=Path(__file__).resolve().parent.parent/'lora_v4_multibase/models/gemma4_26b_a4b/tokenizer.json'
        if not tokenizer_path.exists():self.skipTest('Real Gemma tokenizer is an external asset, not shipped in source ZIP')
        tokenizer=Tokenizer.from_file(str(tokenizer_path))
        played=[{'turn':0,'text':A['body']}]
        context=speech_context('開始',played,A,PLAN)
        full=tokenizer.encode(context['prompt'],add_special_tokens=False).ids
        ids,audit=protected_ids(tokenizer,context['prompt'],context['recent'],context['recent_span'],len(full)-2)
        self.assertEqual(audit['context_cut_tokens'],2)
        decoded=tokenizer.decode(ids,skip_special_tokens=False)
        self.assertIn('【記憶】\n'+A['body'],decoded)
        self.assertIn('【話題】\n'+PLAN['topic'],decoded)
        with self.assertRaises(ContextBudgetError):protected_ids(tokenizer,context['prompt'],context['recent'],context['recent_span'],1)


if __name__=='__main__':unittest.main(verbosity=2)
