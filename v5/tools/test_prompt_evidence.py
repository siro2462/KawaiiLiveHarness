"""CPU verification of saved prompt experiments; no model imports or generation."""
import hashlib,html,json,os,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
V2=ROOT/'v5/evidence/surface_prompt_v2_20261025'
V3=ROOT/'v5/evidence/surface_prompt_v3_vs_v2_20261026'
SRC2=ROOT/'v5/experiments/surface_prompt_v2_20261025'
SRC3=ROOT/'v5/experiments/surface_prompt_v3_vs_v2_20261026'
os.environ.setdefault('ZIP_INCREMENTAL_RUN',str(Path(tempfile.gettempdir())/'zipchan-prompt-publication'))
sys.path.insert(0,str(SRC3))
from prompt_v2 import render as render2
from prompt_v3 import render as render3
from contract_runtime import render as original

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
PACKETS={p:read(p/'review_packet.json') for p in [V2,V3]}
class PromptEvidenceChecks(unittest.TestCase):
 def test_final_hashes_and_completed_four_pairs(self):
  for path,packet in PACKETS.items():
   with self.subTest(path=path):
    c=read(path/'completion.json');a=read(path/'technical_audit.json');r=read(path/'root_review.json')
    self.assertEqual(c['status'],'complete');self.assertEqual(a['status'],'pass')
    self.assertEqual(c['review_packet_sha256'],sha(path/'review_packet.json'))
    self.assertEqual(c['root_review_sha256'],sha(path/'root_review.json'))
    self.assertEqual(r['review_packet_sha256'],c['review_packet_sha256'])
    self.assertTrue(r['root_full_text_read']);self.assertEqual(r['human_quality_labels'],0)
    self.assertEqual(r['reviewed_pair_ids'],['P01','P02','P03','P04'])
    self.assertEqual(len(packet['pairs']),4)
 def test_v3_is_only_three_point_section_and_title(self):
  a=(SRC3/'surface_prompt_v2.txt').read_text(encoding='utf-8');b=(SRC3/'surface_prompt_v3.txt').read_text(encoding='utf-8')
  start=b.index('## v3：話の中心と評価の進め方');end=b.index('## 語り方：短い報告で終わらせない')
  self.assertEqual(b[start:end].strip(),(V3/'v3_added_instructions.md').read_text(encoding='utf-8').strip())
  reduced=(b[:start]+b[end:]).replace('# ZIPちゃん Surface Prompt v3 — Focused Live Narrative','# ZIPちゃん Surface Prompt v2 — Live Narrative')
  self.assertEqual(a,reduced)
 def test_real_saved_requests_match_actual_renderers(self):
  for path,packet in PACKETS.items():
   for pair in packet['pairs']:
    case=pair['pair']['case']
    for arm in ['A','B']:
     renderer=(original if arm=='A' else render2) if path==V2 else (render2 if arm=='A' else render3)
     req=pair[arm]['request'];self.assertEqual(renderer(case),req['user_prompt'])
     self.assertEqual(req['context']['case'],case);self.assertEqual(req['messages'],[{'role':'user','content':[{'type':'text','text':req['user_prompt']}]}])
     self.assertEqual(req['decoded_input'],'<bos><|turn>user\n'+req['user_prompt'].strip()+'<turn|>\n<|turn>model\n<|channel>thought\n<channel|>');self.assertFalse(req['template_kwargs']['enable_thinking'])
 def test_v3_baseline_is_exact_saved_v2_without_new_calls(self):
  for old,new in zip(PACKETS[V2]['pairs'],PACKETS[V3]['pairs']):
   for key in ['request','output','delivery']:self.assertEqual(old['B'][key],new['A'][key])
   self.assertEqual(old['pair']['case'],new['pair']['case'])
 def test_core_worker_and_existing_runtime_are_unchanged(self):
  for n in ['gpu_worker.py','driver_cpu.py','runtime.py','flow_apply.py','common.py','request_protocol.py','token_journal.py','processor_cpu.py','contract_runtime.py','prompt_v2.py','surface_prompt_v2.txt']:
   self.assertEqual((SRC2/n).read_bytes(),(SRC3/n).read_bytes(),n)
  self.assertNotIn('prompt_v3',(ROOT/'v5/runtime/run_cpu.py').read_text(encoding='utf-8'))
  self.assertFalse(read(ROOT/'SOURCE_MANIFEST.json')['default_runtime_prompt_changed'])
 def test_fixed_config_and_no_quality_retry_or_planner_calls(self):
  cfg=PACKETS[V3]['pairs'][0]['A']['output']['generation_config']
  for path,packet in PACKETS.items():
   a=read(path/'technical_audit.json')
   for key in ['planner_calls','guard_calls','quality_retries','training']:self.assertEqual(a[key],0)
   self.assertEqual(a['new_surface_calls'],4)
   for name in ['controller.python_outcome.json','gpu.python_outcome.json']:self.assertEqual(read(path/name)['exit_code'],0)
   for pair in packet['pairs']:
    for arm in ['A','B']:
     out=pair[arm]['output'];self.assertEqual(out['generation_config'],cfg);self.assertEqual(out['seed'],20260925)
     self.assertFalse(out['adapter_disabled']);self.assertTrue(out['official_stop_reached']);self.assertLess(len(out['output_ids']),384)
 def test_full_html_raw_inputs_and_exact_review_quotes(self):
  for path,packet in PACKETS.items():
   page=(path/'comparison.html').read_text(encoding='utf-8');r=read(path/'root_review.json')
   for pair,review in zip(packet['pairs'],r['per_pair']):
    for arm in ['A','B']:
     x=pair[arm]
     for text in [x['delivery']['body'],x['request']['user_prompt'],x['request']['decoded_input'],x['output']['raw_output']]:self.assertIn(html.escape(text),page)
     for quote in review['quotes'][arm]:self.assertIn(quote,x['delivery']['body'])
 def test_report_counts_and_fixed_history_not_closed_loop(self):
  packet=PACKETS[V3];self.assertEqual(sum(sum(not c.isspace() for c in x['A']['delivery']['body']) for x in packet['pairs']),1067)
  self.assertEqual(sum(sum(not c.isspace() for c in x['B']['delivery']['body']) for x in packet['pairs']),984)
  self.assertEqual(len(read(V3/'report_check.json')['metrics']),4)
  for pair in packet['pairs']:
   self.assertFalse(pair['B']['row']['history_updated']);self.assertEqual(pair['B']['row']['semantic_status'],'unverified')
  p2,p3=packet['pairs'][1:3]
  self.assertNotEqual(p2['B']['delivery']['body'],p3['pair']['case']['history'][-1]['text'])
if __name__=='__main__':unittest.main()
