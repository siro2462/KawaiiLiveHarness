"""Read saved evidence and replay CPU selection only. No models, training or network."""
from pathlib import Path
import collections, copy, hashlib, html, importlib.util, json, sys, types, unittest

ROOT=Path(__file__).resolve().parents[2]
E=ROOT/'v5/evidence'
SLUGS=['surface_role_control_h06_20261027','mechanical_ag_h06_20261027','stripe_surface_abc_h06_20261027','stripe_surface_ten_20261027','cpu_select_surface_ten_20261027']
def read(p):return json.loads(p.read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
CPU=E/SLUGS[-1];TEN=E/SLUGS[-2];H06=E/SLUGS[2]
P=read(CPU/'review_packet.json')

class StripeEvidenceChecks(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  # Inject a read-only publication data root, without importing the process driver.
  cls.prior_common=sys.modules.get('common')
  common=types.ModuleType('common');common.OUT=CPU;common.read=read;sys.modules['common']=common
  spec=importlib.util.spec_from_file_location('published_cpu_selector',ROOT/'v5/experiments'/SLUGS[-1]/'cpu_selector.py')
  cls.selector=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.selector)
 @classmethod
 def tearDownClass(cls):
  if cls.prior_common is None:sys.modules.pop('common',None)
  else:sys.modules['common']=cls.prior_common
 def test_all_five_current_runs_complete_with_separate_zero_exits(self):
  expected=[2,23,11,10,10]
  for slug,calls in zip(SLUGS,expected):
   r=E/slug;a=read(r/'technical_audit.json');c=read(r/'completion.json')
   self.assertEqual(a['status'],'pass');self.assertTrue(a['current_exit0']);self.assertEqual(a['new_surface_calls'],calls);self.assertEqual(c['status'],'complete')
   for name in ['controller.python_outcome.json','gpu.python_outcome.json']:self.assertEqual(read(r/name)['exit_code'],0)
   self.assertEqual(read(r/'report_check.json')['status'],'pass')
 def test_review_packet_and_completion_hash_chains(self):
  for slug in SLUGS:
   r=E/slug;c=read(r/'completion.json');root=read(r/'root_review.json')
   self.assertEqual(c['review_packet_sha256'],sha(r/'review_packet.json'))
   self.assertEqual(root['review_packet_sha256'],sha(r/'review_packet.json'))
   self.assertEqual(c['comparison_sha256'],sha(r/'comparison.html'))
   if 'root_review_sha256' in c:self.assertEqual(c['root_review_sha256'],sha(r/'root_review.json'))
   else:self.assertEqual(c['review_sha256'],sha(r/'root_review.json'))
   self.assertEqual(root['human_quality_labels'],0)
 def test_default_runtime_and_fixed_surface_core_preserved(self):
  for slug in SLUGS:
   src=ROOT/'v5/experiments'/slug
   for name in ['contract_runtime.py','runtime.py','flow_apply.py','driver_cpu.py','gpu_worker.py']:
    self.assertEqual((src/name).read_bytes(),(ROOT/'v5/runtime'/name).read_bytes(),(slug,name))
  self.assertNotIn('cpu_selector',(ROOT/'v5/runtime/run_cpu.py').read_text('utf-8'))
 def test_reference_h06_engine_bytes_identical_and_original_32_reproduced(self):
  ep=CPU/'reference/h06_engine/engine.py'
  self.assertEqual(ep.read_bytes(),(H06/'reference/stripe_engine/engine.py').read_bytes())
  spec=importlib.util.spec_from_file_location('publication_original_h06_engine',ep);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  trace=m.Engine(seed=17,mode='state',allow_cross=False).run('H06');expected=read(H06/'steps32.json')
  self.assertEqual(len(trace),32)
  self.assertEqual([(x['node_id'],x['operation']) for x in trace],[(x['memory_id'],x['operation']) for x in expected])
 def test_all_ten_cpu_selections_reproduce_entire_saved_graph_scores_trace(self):
  fixed=read(CPU/'memory_fixed.json');saved=read(CPU/'cpu_selections.json')
  # The archived selection file is a dict with per-sample entries in current sources.
  self.assertEqual(len(fixed),10)
  for t,s in zip(P['samples'],fixed):
   actual=self.selector.select(s)
   self.assertEqual(actual,t['selection'])
   self.assertEqual(actual['steps'],t['sample']['steps'])
   self.assertFalse(actual['manual_sequence']);self.assertTrue(all(n['requires']==[] for n in actual['graph']['nodes']))
   self.assertTrue(all(not e['semantic_verification'] for e in actual['derived_metadata']['edges']))
  self.assertTrue(saved)
 def test_old_manual_steps_and_original_array_order_do_not_select_new_order(self):
  s=read(CPU/'memory_fixed.json')[0];expected=self.selector.select(s)['steps']
  poisoned=copy.deepcopy(s);poisoned['steps']=[dict(index=999,memory_id='invalid',operation='DO_NOT_USE')];poisoned['nodes'].reverse()
  self.assertEqual(self.selector.select(poisoned)['steps'],expected)
 def test_memory_lora_and_all_generation_conditions_fixed_against_previous_ten(self):
  self.assertEqual(len(P['samples']),10)
  for t in P['samples']:
   old=t['baseline'];self.assertEqual(t['sample']['nodes'],old['sample']['nodes']);self.assertEqual(t['sample']['provenance'],old['sample']['provenance'])
   self.assertEqual(t['output']['generation_config'],old['output']['generation_config']);self.assertEqual(t['output']['seed'],old['output']['seed'])
   self.assertEqual(t['output']['generation_config']['max_new_tokens'],1536)
  cfg=read(CPU/'protocol_export.json');prior=read(TEN/'protocol_export.json')
  self.assertEqual(cfg['surface'],prior['surface']);self.assertEqual(cfg['surface_seed'],20260925)
 def test_all_twenty_full_actual_prompts_decoded_raw_and_bodies_present(self):
  doc=(CPU/'comparison.html').read_text('utf-8');plain=(CPU/'full_comparison.txt').read_text('utf-8')
  for t in P['samples']:
   for a in [t,t['baseline']]:
    for text in [a['request']['user_prompt'],a['request']['decoded_input'],a['output']['raw_output'],a['delivery']['body']]:self.assertIn(html.escape(text),doc)
    self.assertIn(a['delivery']['body'],plain)
 def test_cpu_selected_operations_are_exact_actual_payload_not_hand_insertion(self):
  fields=['index','memory_id','operation','kind','content','epistemic','relation','anchor_id']
  for t in P['samples']:
   text=t['request']['user_prompt'];ops=text.split('【今回の操作列】\n')[1]
   self.assertEqual(json.loads(ops),[{k:s[k] for k in fields} for s in t['selection']['steps']])
   self.assertIn(text,t['request']['decoded_input']);self.assertTrue(t['output']['official_stop_reached']);self.assertTrue(t['row']['delivered'])
   self.assertEqual(t['row']['after_history'],[dict(text=t['delivery']['body'],origin='offline unverified text; not Memory')])
 def test_fet_labels_use_actual_text_and_are_not_plan_execution_labels(self):
  labels=read(CPU/'output_annotations.json');by={x['call_id']:x['units'] for x in labels['calls']}
  self.assertEqual(sum(len(x) for x in by.values()),188)
  self.assertEqual(labels['human_quality_labels'],0)
  for t in P['samples']:
   ls=by[t['row']['call_id']];self.assertEqual(''.join(x['text'] for x in ls),t['delivery']['body'])
   for u in ls:self.assertIn(u['primary'],['F','E','T']);self.assertTrue(u['rationale'])
  self.assertTrue(read(CPU/'root_review.json')['no_full_operation_execution_rate'])
 def test_rhythm_comparison_is_llm_vs_llm_not_human_same_grain_claim(self):
  r=read(ROOT/'v5/progress/stripe_rhythm_comparison.json')
  self.assertEqual(r['human_vs_CPU_same_grain_rhythm_analysis'],'not_performed')
  totals=r['totals'];self.assertEqual(totals['manual_operations_LLM']['chars'],6635);self.assertEqual(totals['manual_operations_LLM']['E_chars'],1315)
  self.assertEqual(totals['CPU_operations_LLM']['chars'],4987);self.assertEqual(totals['CPU_operations_LLM']['E_chars'],975)
  old=read(TEN/'output_annotations.json');new=read(CPU/'output_annotations.json')
  for name,d in [('manual_operations_LLM',old),('CPU_operations_LLM',new)]:
   us=[u for call in d['calls'] for u in call['units']]
   self.assertEqual(sum(sum(not c.isspace() for c in u['text']) for u in us if u['primary']=='E'),totals[name]['E_chars'])
 def test_new_experiments_have_no_new_planner_guard_training_or_retries(self):
  for slug in SLUGS:
   a=read(E/slug/'technical_audit.json')
   for key in ['planner_calls','guard_calls','training','quality_retries','memory_writes']:self.assertEqual(a[key],0)

if __name__=='__main__':unittest.main()
