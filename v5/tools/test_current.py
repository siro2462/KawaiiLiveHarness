"""CPU checks for current continuation policy and saved complete results; no models."""
import copy,html,json,os,re,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'v5/runtime'
os.environ.setdefault('ZIP_INCREMENTAL_RUN',str(Path(tempfile.gettempdir())/'zipchan-current-cpu/harness_beta/runs/check'))
sys.path[:0]=[str(SRC),str(ROOT/'_talk/lora_v4_gemma_runtime'),str(ROOT/'_talk/lora_v4_multibase')]
from runtime import Progress,EventStore,facts_for
from contract_runtime import render
from planner_delivery import resolve
import run_cpu

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
LONG=ROOT/'v5/evidence/continuous10_20261024'
HUMAN=ROOT/'v5/evidence/human_memory_compare_20261024'
FIX=read(SRC/'sources/fixtures_20.json')
PACKETS={LONG:read(LONG/'review_packet.json'),HUMAN:read(HUMAN/'review_packet.json')}
class CurrentChecks(unittest.TestCase):
 def memory(self,mid):
  m=copy.deepcopy(next(m for m in FIX if m['id']==mid));m['body']=m['text'];return m
 def test_actual_unterminated_plan_is_discarded_without_quality_retry(self):
  old=read(ROOT/'v5/evidence/planner_R0017_failure.json')['record']['raw']
  z=resolve(old['text'],['F08']);self.assertIsNone(z['plan']);self.assertTrue(z['format_fallback']);self.assertFalse(z['syntax_valid'])
  self.assertEqual(z['fallback_policy'],'discard_invalid_plan_use_fixed_source_fact_order_no_retry');self.assertEqual(old['output_tokens'],256)
 def test_unknown_candidate_duplicate_key_and_extra_key_discard_plan(self):
  cases=['{"use_memory":true,"memory_id":"OTHER","topic":"x","flow":["a","b"]}', '{"use_memory":false,"memory_id":null,"topic":"x","flow":["a","b"],"extra":1}', '{"use_memory":false,"memory_id":null,"topic":"x","topic":"y","flow":["a","b"]}']
  for raw in cases:
   with self.subTest(raw=raw):self.assertTrue(resolve(raw,['F08'])['format_fallback'])
 def test_valid_abstention_is_distinct_from_parse_failure(self):
  z=resolve('{"use_memory":false,"memory_id":null,"topic":"continue","flow":["a","b"]}',['F08'])
  self.assertTrue(z['syntax_valid']);self.assertFalse(z['format_fallback']);self.assertIsNotNone(z['plan'])
 def test_schema_valid_degenerate_plan_is_not_semantic_certification(self):
  t=PACKETS[HUMAN]['turns'][1];self.assertEqual(t['plan']['topic'],'{');self.assertTrue(t['planner_syntax_valid'])
  self.assertEqual(resolve(t['actual_planner_output']['text'],['H05'])['plan'],t['plan']);self.assertFalse(t['before']['mapping']['adopted'])
 def test_runtime_really_continues_after_bad_plan_and_delivers_history(self):
  m=self.memory('F08');old=read(ROOT/'v5/evidence/planner_R0017_failure.json')['record']['raw']['text']
  class MockDriver:
   def __init__(self):self.n=0;self.cases=[]
   def call(self,role,prompt,seed,context):
    self.n+=1;cid=f'R{self.n:04}';assert self.n<=6
    if role=='planner':
     text=old if self.n==1 else '{"use_memory":false,"memory_id":null,"topic":"CPU only","flow":["a","b"]}'
     return cid,dict(text=text,raw_output=text)
    assert render(context['case'])==prompt
    self.cases.append(copy.deepcopy(context['case']));body=''.join(f['claim'] for f in context['case']['facts'])
    return cid,dict(body=body,raw_output=body+'<turn|>',official_stop_reached=True)
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp)
   for x in ['plans','selections','turns']:(folder/x).mkdir()
   es=EventStore(folder/'events.sqlite');d=MockDriver()
   cfg=dict(eligible_memory_ids=['F08'],target_chars=10000,max_surface_calls=3,seeds=[20260925],prefix_reuse=[],chars_per_minute_assumption=250)
   # This checks the real rollout/adoption/progress path; alpha and Planner input assembly are CPU test doubles.
   # Actual Planner/Surface rendered inputs are checked separately against every saved delivery.
   def request_stub(memory,recent,previous,progress):
    return dict(prompt='CPU-only request stub',recent=recent,candidate_ids=[memory['id']]),dict(planner_input={})
   try:
    with patch.object(run_cpu,'OUT',folder),patch.object(run_cpu,'choose',return_value=(m,[])),patch.object(run_cpu,'observe_alpha'),patch.object(run_cpu,'make_planner_request',side_effect=request_stub):
     out=run_cpu.rollout(None,d,cfg,es,dict(calls_completed=0))
   finally:es.close()
   self.assertEqual(len(out['records']),3);self.assertEqual(out['planner_format_fallbacks'],1);self.assertEqual(out['stop_reason'],'all_eligible_source_presented')
   self.assertTrue(all(t['delivered'] for t in out['records']));self.assertIsNone(out['records'][0]['plan'])
   self.assertEqual(d.cases[0]['history'],[]);self.assertEqual(d.cases[1]['history'][0]['text'],out['records'][0]['body'])
   ids=[f['id'] for c in d.cases for f in c['facts']];self.assertEqual(ids,[f['id'] for f in facts_for(m)])
 def test_all56_saved_histories_are_actual_prior_deliveries(self):
  for root,p in PACKETS.items():
   with self.subTest(root=root),tempfile.TemporaryDirectory() as tmp:
    es=EventStore(Path(tmp)/'events.sqlite')
    for t in p['turns']:
     self.assertEqual([x['text'] for x in t['case']['history']],[x['text'] for x in es.recent()])
     self.assertEqual(t['actual_planner_request']['recent'],'\n'.join(x['text'] for x in es.recent()))
     if t['delivered']:es.append('text_delivery_confirmed',dict(text=t['body'],memory_id=t['memory_id']))
    es.close()
 def test_all_saved_surface_inputs_match_fixed_contract(self):
  for p in PACKETS.values():
   for t in p['turns']:self.assertEqual(render(t['case']),t['actual_surface_request']['user_prompt'])
 def test_source_targets_once_and_semantics_still_unverified(self):
  for root,p in PACKETS.items():
   ids=[f['id'] for t in p['turns'] for f in t['case']['facts']]
   self.assertEqual(len(ids),len(set(ids)));self.assertEqual(len(ids),88 if root==LONG else 9)
   self.assertTrue(all(v['semantic_status']=='unverified' for t in p['turns'] for v in t['after']['facts'].values()))
 def test_completed_long_run_counts_do_not_relabel_failed_prefix(self):
  a=read(LONG/'technical_audit.json');self.assertEqual((a['surface_candidates'],a['delivered_chars'],a['calls']),(51,2503,102))
  self.assertEqual((a['prefix_reused_calls'],a['new_model_calls'],a['planner_format_fallbacks']),(17,85,5));self.assertTrue(a['previous_source_exit1_preserved'])
  self.assertTrue(read(LONG/'completion.json')['target_met']);self.assertEqual(read(ROOT/'v5/evidence/partial_integrity.json')['counts']['delivered_chars'],429)
 def test_completed_run_receipts_are_exit_zero(self):
  for root in PACKETS:
   for name in ['controller.python_outcome.json','gpu.python_outcome.json']:self.assertEqual(read(root/name)['exit_code'],0)
 def test_human_exhaustion_is_valid_even_when_shorter(self):
  a=read(HUMAN/'technical_audit.json');c=read(HUMAN/'completion.json');self.assertEqual(a['stop_reason'],'all_eligible_source_presented');self.assertFalse(a['target_met'])
  self.assertEqual(c['status'],'complete');self.assertTrue(c['all_source_targets_presented']);self.assertEqual(a['delivered_chars'],730)
 def test_existing_memory_projection_and_no_reference_history(self):
  refs=read(HUMAN/'reference/source_pairs.json');fixtures=read(ROOT/'v5/experiments/human_memory_compare/sources/fixtures_20.json')
  self.assertEqual(len(refs),4);self.assertEqual(sum(len(m['beats']) for m in fixtures),9)
  for ref,m in zip(refs,fixtures):self.assertEqual(''.join(f['claim'] for f in facts_for(m)),ref['memory'])
  for t in PACKETS[HUMAN]['turns']:
   req=t['actual_surface_request'];self.assertFalse(any(ref['human_text'] in req['user_prompt'] for ref in refs))
   self.assertEqual(t['actual_planner_request']['context']['planner_input']['memory_candidates'][0]['body'],next(x['memory'] for x in refs if x['memory_id']==t['memory_id']))
 def test_human_plan_application_is_zero_not_planner_success(self):
  ts=PACKETS[HUMAN]['turns'];self.assertEqual(sum(t['plan']['use_memory'] for t in ts),1);self.assertFalse(any(t['before']['mapping']['adopted'] for t in ts))
  self.assertEqual(ts[-1]['before']['mapping']['reason'],'No audited source contract; fixed source order')
 def test_saved_speech_order_and_complete_html_texts(self):
  for root,p in PACKETS.items():
   self.assertEqual((root/'speech.txt').read_text(encoding='utf-8'),'\n\n'.join(t['body'] for t in p['turns'] if t['delivered'])+'\n')
   doc=(root/'comparison.html').read_text(encoding='utf-8')
   for t in p['turns']:self.assertIn(html.escape(t['body']),doc)
  doc=(HUMAN/'comparison.html').read_text(encoding='utf-8')
  for ref in read(HUMAN/'reference/source_pairs.json'):self.assertIn(html.escape(ref['human_text']),doc);self.assertIn(html.escape(ref['memory']),doc)
 def test_documented_runtime_policies_and_no_new_model_artifacts(self):
  cfg=read(ROOT/'v5/PROTOCOL.json');self.assertFalse(cfg['stop_on_invalid_plan']);self.assertFalse(cfg['semantic_guard']);self.assertEqual(cfg['quality_retries'],0)
  self.assertTrue((ROOT/'v5/progress/checkpoint.json').exists());self.assertFalse(read(ROOT/'v5/progress/checkpoint.json')['human_quality_labels'])
if __name__=='__main__':unittest.main()
