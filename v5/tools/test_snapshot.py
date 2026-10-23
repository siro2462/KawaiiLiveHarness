"""CPU regression checks of saved real examples and unchanged Runtime contracts."""
import copy,json,os,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'v5/runtime'
os.environ.setdefault('ZIP_INCREMENTAL_RUN',str(Path(tempfile.gettempdir())/'zipchan-v5-cpu/harness_beta/runs/check'))
sys.path[:0]=[str(SRC),str(ROOT/'_talk/lora_v4_gemma_runtime'),str(ROOT/'_talk/lora_v4_multibase')]
from runtime import Progress,EventStore,facts_for,format_failure,surface_case
from contract_runtime import render
from planner_policy import parse_plan
from flow_apply import plan_order
from request_protocol import request_stream

def read(p):return json.loads(p.read_text(encoding='utf-8'))
FIX=read(SRC/'sources/fixtures_20.json');TURNS=read(ROOT/'v5/evidence/partial_turns.json')['turns']
class SnapshotChecks(unittest.TestCase):
 def memory(self,mid):
  m=copy.deepcopy(next(x for x in FIX if x['id']==mid));m['body']=m['text'];return m
 def test_twenty_synthetic_sources_and_94_facts(self):
  self.assertEqual(len(FIX),20);self.assertEqual(len({m['id'] for m in FIX}),20)
  self.assertTrue(all(m['namespace']=='fixtures' and m['authority']=='synthetic_fixture' for m in FIX))
  self.assertEqual(sum(len(m['beats']) for m in FIX),94)
 def test_all_eight_saved_histories_are_actual_prior_deliveries(self):
  with tempfile.TemporaryDirectory() as t:
   es=EventStore(Path(t)/'events.sqlite')
   for row in TURNS:
    self.assertEqual([x['text'] for x in es.recent()],[x['text'] for x in row['case']['history']])
    self.assertTrue(row['delivered']);es.append('text_delivery_confirmed',dict(text=row['body'],memory_id=row['memory_id']))
   es.close()
 def test_saved_surface_input_is_exact_renderer_result(self):
  for row in TURNS:self.assertEqual(render(row['case']),row['actual_surface_prompt'])
 def test_all14_saved_targets_are_single_presentations(self):
  ids=[f['id'] for row in TURNS for f in row['case']['facts']]
  self.assertEqual(len(ids),14);self.assertEqual(len(set(ids)),14)
 def test_target_presentation_does_not_claim_semantic_coverage(self):
  p=Progress(self.memory('F01'),None);ids=p.focus('C');p.presented(ids);p.finish(ids,'別の表現',1)
  self.assertTrue(all(p.facts[i]['semantic_status']=='unverified' for i in ids))
  self.assertTrue(all(i not in p.pending() for i in ids))
  with self.assertRaises(ValueError):p.presented(ids)
 def test_adopted_saved_plan_never_changes_order_in_evidence(self):
  for row in TURNS:
   if row['mapping'].get('adopted'):self.assertFalse(row['mapping']['changed'])
  self.assertEqual(sum(bool(r['mapping'].get('adopted')) for r in TURNS),3)
 def test_discovery_must_precede_relief_under_explicit_plan(self):
  m=self.memory('F01');p=dict(use_memory=True,memory_id='F01',topic='CPU',flow=['F01-5','F01-4'])
  order,mapping=plan_order(p,facts_for(m));self.assertTrue(mapping['adopted'])
  self.assertLess(order.index('F01-4'),order.index('F01-5'))
 def test_unknown_fact_id_does_not_reorder(self):
  m=self.memory('F01');p=dict(use_memory=True,memory_id='F01',topic='CPU',flow=['F01-99','F01-1'])
  order,mapping=plan_order(p,facts_for(m));self.assertFalse(mapping['adopted']);self.assertEqual(order,[f['id'] for f in facts_for(m)])
 def test_invalid_planner_output_remains_invalid(self):
  q=read(ROOT/'v5/evidence/planner_R0017_failure.json')['record']
  self.assertFalse(q['syntax_valid']);self.assertEqual(q['raw']['stop_reason'],'token_cap');self.assertEqual(q['raw']['output_tokens'],256)
  with self.assertRaises(ValueError):parse_plan(q['raw']['text'],['F08'])
 def test_complete_json_plan_still_uses_four_key_contract(self):
  for row in TURNS:self.assertEqual(parse_plan(row['planner_raw'],[row['memory_id']]),row['plan'])
 def test_done_after_last_allowed_call_terminates(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'requests').mkdir();(p/'requests/R0001.json').write_text('{}',encoding='utf-8');(p/'requests/DONE.json').write_text('{"calls":1}',encoding='utf-8')
   self.assertEqual([n for n,f in request_stream(p,1,request_timeout=.1,done_timeout=.1,poll=.001)],[1])
 def test_format_acceptance_does_not_equal_experiment_completion(self):
  for row in TURNS:self.assertIsNone(format_failure(row['body'],True))
  c=read(ROOT/'v5/evidence/partial_integrity.json')['counts'];self.assertFalse(c['target_met']);self.assertEqual(c['delivered_chars'],429)
if __name__=='__main__':unittest.main()
