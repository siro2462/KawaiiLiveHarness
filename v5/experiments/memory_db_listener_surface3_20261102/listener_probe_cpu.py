"""CPU-only paired input check; baseline real histories are not rollout inputs."""
from common import *
import importlib.util
from processor_cpu import prepare
from stripe_runtime import render_step
from full_stripe_runtime import style_block
from compact_surface import decoded_parts

def run_probe(proc,check):
 cfg=read(OUT/'protocol.json');base=Path(cfg['baseline_run'])
 spec=importlib.util.spec_from_file_location('saved_compact_renderer',OUT/'reference/baseline_compact_surface.py')
 old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
 cue=(OUT/'listener_style.txt').read_text('utf-8')
 check('listener cue fixed bytes',sha(OUT/'listener_style.txt')==cfg['listener_style_sha256'])
 check('same full Memory dict file bytes',sha(OUT/'samples.json')==sha(base/'samples.json'))
 check('three oral examples and sentence target held fixed',all(sha(OUT/n)==sha(base/n) for n in ['reaction_style.txt','grouping_style.txt','unit_instruction.txt']))
 check('no length target restored','200' not in cue and '300' not in cue)
 records=[]
 for item in read(OUT/'baseline_packet.json')['samples']:
  sample=item['sample'];prior=[]
  for index,turn in enumerate(item['turns']):
   prompt,payload=render_step(sample,index,prior)
   original,parts=old.render(sample,payload,style_block(),(OUT/'unit_instruction.txt').read_text('utf-8'))
   a=prepare(proc,original);b=prepare(proc,prompt);key=sample['id']+f':G{index+1:02}'
   check(key+' exact saved baseline official fields',all(turn['request'][k]==v for k,v in a.items()))
   check(key+' all model input parts identical',parts==payload['model_input_parts']==turn['request']['context']['payload']['model_input_parts'])
   check(key+' only appended listener block',prompt.count(cue)==1 and prompt.replace(cue,'',1).encode()==original.encode())
   check(key+' theme payload suffix byte identical',prompt.split('【現在のテーマ】\n',1)[1].encode()==original.split('【現在のテーマ】\n',1)[1].encode())
   check(key+' real decoded gets complete cue',cue in b['decoded_input'])
   check(key+' real decoded gets exact payload',decoded_parts(b['decoded_input'])==parts)
   check(key+' same three examples and sentence instruction',all(word in b['decoded_input'] for word in ['例1 入力','例2 入力','例3 入力','目安は2〜3文程度']))
   check(key+' no token truncation',len(b['processor_fields']['input_ids'][0])+1536<8192)
   records.append(dict(unit_key=key,baseline_call_id=turn['row']['call_id'],only_listener_block_changed=True,model_input_parts_identical=True,
    old_input_tokens=len(a['processor_fields']['input_ids'][0]),new_input_tokens_same_history=len(b['processor_fields']['input_ids'][0]),
    old_prompt_chars=len(original),new_prompt_chars=len(prompt),source_step_indices=turn['row']['source_step_indices']))
   prior.append(turn['row'])
 check('all11 baseline calls checked',len(records)==11)
 write(OUT/'listener_only_cpu_proof.json',dict(status='pass',new_model_calls=0,listener_characters=len(cue),
  all11_actual_baseline_official_inputs_exact=True,all11_model_parts_identical=True,all11_suffix_bytes_identical=True,
  direct_reaction_examples_fixed=True,sentence_target_fixed=True,records=records,
  baseline_histories_used_for_CPU_only=True,actual_rollout_uses_own_generated_history=True))
