import unittest
from runtime_state import PlanStore, speech_context
from alpha_contract import validate_proposal, resolve_memories


class Tests(unittest.TestCase):
    def test_expiry_and_memory_hash_prevent_stale_fallback(self):
        memory = {'id':'S2B','body':'冷凍うどんにカレーをかけた。'}
        plan = {'use_memory':True,'memory_id':'S2B','topic':'食事の話','flow':['振り返る','感想']}
        store = PlanStore()
        with self.assertRaises(ValueError):
            store.stage(plan, memory, 0, {'accepted':False})
        store.stage(plan, memory, 0, {'accepted':True,'test_only':True})
        self.assertIsNone(store.active)
        store.commit()
        self.assertIsNotNone(store.fallback(1, memory))
        self.assertIsNone(store.fallback(3, memory))
        self.assertIsNone(store.fallback(2, dict(memory,body='別の出来事')))
        store.invalidate('repetition')
        self.assertIsNone(store.fallback(2, memory))

    def test_planless_and_use_memory_false_keep_canonical_facts_recent_three(self):
        memory = {'id':'S2B','body':'冷凍うどんにカレーをかけた。'}
        played = [{'text':str(i)} for i in range(7)]
        for plan in [None, {'use_memory':False,'memory_id':None,'topic':'感想','flow':['感想','連想']}]:
            context = speech_context('開始', played, memory, plan)
            self.assertEqual(context['recent'], '4\n5\n6')
            self.assertIn(memory['body'], context['prompt'])
            self.assertEqual(context['grounding']['id'], 'S2B')
        self.assertIn('【話題】\nなし', speech_context('開始', [], memory)['prompt'])

    def test_alpha_has_source_provenance_and_cannot_script_speech(self):
        bank = {'S2B':'元Memory'}
        proposal = {'version':'alpha.v0.1','decision':'propose',
                    'trigger':{'kind':'external_event','event_id':'event-1'},
                    'memory_ids':['S2B'],'topic_hint':'料理を思い出した'}
        self.assertEqual(resolve_memories(proposal, bank), [{'id':'S2B','body':'元Memory'}])
        for bad in [dict(proposal,flow=['次の台詞']), dict(proposal,memory_ids=['FOREIGN'])]:
            with self.assertRaises(ValueError):
                validate_proposal(bad, bank)
        wait = dict(proposal, decision='wait', memory_ids=[], topic_hint=None)
        self.assertEqual(resolve_memories(wait, bank), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
