"""Verify published H06 angle evidence against real saved requests; no model imports."""
import hashlib,html,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'v5/experiments/surface_viewpoint_h06_20261026'
E=ROOT/'v5/evidence/surface_viewpoint_h06_20261026'
sys.path.insert(0,str(SRC))
from viewpoint_runtime import render
from contract_runtime import render as original

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
P=read(E/'review_packet.json')
H=read(ROOT/'v5/evidence/human_memory_compare_20261024/review_packet.json')

class ViewpointEvidenceChecks(unittest.TestCase):
 def test_completion_and_root_review_hashes(self):
  c=read(E/'completion.json');r=read(E/'root_review.json')
  self.assertEqual(c['status'],'complete');self.assertEqual(read(E/'technical_audit.json')['status'],'pass')
  for key,name in [('review_packet_sha256','review_packet.json'),('root_review_sha256','root_review.json'),('comparison_sha256','comparison.html'),('full_text_sha256','full_comparison.txt')]:self.assertEqual(c[key],sha(E/name))
  self.assertEqual(r['review_packet_sha256'],sha(E/'review_packet.json'))
  self.assertEqual(r['reviewed_pair_ids'],['G01','G02']);self.assertTrue(r['root_full_text_read'])
  self.assertTrue(r['common_first_full_text_read']);self.assertTrue(r['human_reference_full_text_read']);self.assertEqual(r['human_quality_labels'],0)
 def test_actual_prompt_and_official_saved_text_wrapper(self):
  for pair in P['pairs']:
   case=pair['pair']['case'];angle=pair['pair']['viewpoint']
   for arm,expected in [('A',original(case)),('B',render(case,angle))]:
    req=pair[arm]['request']
    self.assertEqual(req['user_prompt'],expected);self.assertEqual(req['context']['case'],case)
    self.assertEqual(req['messages'],[{'role':'user','content':[{'type':'text','text':expected}]}])
    self.assertEqual(req['decoded_input'],'<bos><|turn>user\n'+expected.strip()+'<turn|>\n<|turn>model\n<|channel>thought\n<channel|>')
 def test_fixed_case_and_generation_with_angle_only_between_new_conditions(self):
  a,b=P['pairs'];self.assertEqual(a['pair']['case'],b['pair']['case']);self.assertEqual(a['A'],b['A'])
  va,vb=a['pair']['viewpoint'],b['pair']['viewpoint']
  self.assertEqual(va['schema'],vb['schema']);self.assertEqual(va['basis'],vb['basis']);self.assertNotEqual(va['instruction'],vb['instruction'])
  cfg=a['A']['output']['generation_config']
  for pair in P['pairs']:
   for arm in ['A','B']:
    x=pair[arm];self.assertEqual(x['output']['generation_config'],cfg);self.assertEqual(x['output']['seed'],20260925)
    self.assertFalse(x['output']['adapter_disabled']);self.assertFalse(x['request']['template_kwargs']['enable_thinking'])
   self.assertEqual(pair['B']['row']['applied_viewpoint']['case'],pair['pair']['case'])
 def test_exact_reference_to_original_human_comparison(self):
  by_call={t['call_id']:t for t in H['turns']}
  for x in [P['pairs'][0]['A'],P['common_first']]:
   t=by_call[x['request']['call_id']]
   self.assertEqual(x['request'],t['actual_surface_request']);self.assertEqual(x['output'],t['actual_surface_output'])
   self.assertEqual(x['delivery']['body'],t['body']);self.assertEqual(x['delivery']['raw_output'],t['raw_output'])
 def test_default_runtime_and_shared_generation_core_unchanged(self):
  for name in ['contract_runtime.py','runtime.py','flow_apply.py','driver_cpu.py','gpu_worker.py']:
   self.assertEqual((SRC/name).read_bytes(),(ROOT/'v5/runtime'/name).read_bytes())
  self.assertNotIn('viewpoint_runtime',(ROOT/'v5/runtime/run_cpu.py').read_text(encoding='utf-8'))
  for pair in P['pairs']:
   row=pair['B']['row'];self.assertFalse(row['history_updated']);self.assertFalse(row['semantic_guard_used']);self.assertEqual(row['semantic_status'],'unverified')
  self.assertTrue(all(x['semantic_status']=='unverified' for x in P['angle_attempts']))
 def test_counts_eos_and_no_new_planner_or_quality_retries(self):
  audit=read(E/'technical_audit.json');self.assertEqual(audit['new_surface_calls'],2)
  for key in ['planner_calls','guard_calls','training','quality_retries']:self.assertEqual(audit[key],0)
  for name in ['controller.python_outcome.json','gpu.python_outcome.json']:self.assertEqual(read(E/name)['exit_code'],0)
  self.assertEqual(read(E/'report_check.json')['status'],'pass')
  texts=[P['pairs'][0]['A']['delivery']['body']]+[x['B']['delivery']['body'] for x in P['pairs']]
  self.assertEqual([sum(not c.isspace() for c in t) for t in texts],[99,92,110])
  for x in P['pairs']:
   o=x['B']['output'];self.assertTrue(o['official_stop_reached']);self.assertLess(len(o['output_ids']),384)
  self.assertEqual(read(E/'monitoring_completion.json')['delete_status'],'deleted')
 def test_all_full_text_raw_prompts_and_review_quotes_published(self):
  doc=(E/'comparison.html').read_text(encoding='utf-8');plain=(E/'full_comparison.txt').read_text(encoding='utf-8')
  r=read(E/'root_review.json')
  for pair,review in zip(P['pairs'],r['per_pair']):
   for arm in ['A','B']:
    x=pair[arm]
    for t in [x['request']['user_prompt'],x['request']['decoded_input'],x['output']['raw_output'],x['delivery']['body']]:self.assertIn(html.escape(t),doc)
    self.assertIn(x['delivery']['body'],plain)
    for q in review['quotes'][arm]:self.assertIn(q,x['delivery']['body'])
  c=P['common_first']
  for t in [c['request']['user_prompt'],c['request']['decoded_input'],c['output']['raw_output'],c['delivery']['body']]:self.assertIn(html.escape(t),doc)

if __name__=='__main__':unittest.main()
