"""Compare real baseline inputs under identical history; only common prefix may differ."""
from common import *
import importlib.util
from processor_cpu import prepare
from stripe_runtime import render_step
from full_stripe_runtime import style_block
from compact_surface import decoded_parts,PREFIX

def run_probe(proc,check):
 cfg=read(OUT/'protocol.json');base=Path(cfg['baseline_run'])
 spec=importlib.util.spec_from_file_location('frozen_prior_prefix_renderer',OUT/'reference/baseline_compact_surface.py')
 old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
 check('historical prefix exact257',len(PREFIX)==257 and sha(OUT/'historical_prefix.txt')==cfg['historical_prefix_sha256'])
 oldpacket=read(Path(cfg['historical_prefix_source'])/'review_packet.json')
 hist=next(a for a in oldpacket['arms'] if a['arm']=='C')['turns'][0]['request']['user_prompt'].split('【現在のテーマ】\n',1)[0]
 check('historical actual source prefix byte exact',PREFIX.encode()==hist.encode())
 check('all source Memory dicts byte fixed',sha(OUT/'samples.json')==sha(base/'samples.json'))
 check('entire instructions archival references unchanged',all(sha(OUT/n)==sha(base/n) for n in ['reaction_style.txt','grouping_style.txt','unit_instruction.txt']))
 examples=[]
 for sample in read(OUT/'baseline_packet.json')['samples']:
  s=sample['sample'];prior=[]
  for index,turn in enumerate(sample['turns']):
   newprompt,payload=render_step(s,index,prior)
   oldprompt,oldparts=old.render(s,payload,style_block(),(OUT/'unit_instruction.txt').read_text('utf-8'))
   oldofficial=prepare(proc,oldprompt);newofficial=prepare(proc,newprompt);key=s['id']+f':G{index+1:02}'
   check(key+' prior actual official request exact',all(turn['request'][k]==v for k,v in oldofficial.items()))
   check(key+' complete visible payload unchanged at equal history',oldparts==payload['model_input_parts']==turn['request']['context']['payload']['model_input_parts'])
   check(key+' all model input suffix bytes unchanged',oldprompt.split('【現在のテーマ】\n',1)[1].encode()==newprompt.split('【現在のテーマ】\n',1)[1].encode())
   check(key+' old988 new257 prefix only',len(oldprompt.split('【現在のテーマ】\n')[0])==988 and newprompt.startswith(PREFIX+'【現在のテーマ】\n') and len(oldprompt)-len(newprompt)==731)
   check(key+' no added oral examples or sentence target',all(word not in newprompt for word in ['【反応の出し方】','例1 入力','例2 入力','例3 入力','目安は2〜3文','【今回のひとまとまりの発話】']))
   check(key+' official decoded unchanged model parts',decoded_parts(newofficial['decoded_input'])==oldparts)
   check(key+' all active cues limited to historical plus fixed payload',newprompt.count('【現在のテーマ】\n')==1 and newofficial['user_prompt']==newprompt)
   examples.append(dict(unit_key=key,baseline_call_id=turn['row']['call_id'],same_baseline_actual_history=True,model_input_parts_identical=True,only_prefix_changed=True,old_input_tokens=len(oldofficial['processor_fields']['input_ids'][0]),new_input_tokens_same_history=len(newofficial['processor_fields']['input_ids'][0]),old_prompt_chars=len(oldprompt),new_prompt_chars=len(newprompt),source_step_indices=turn['row']['source_step_indices']))
   prior.append(turn['row'])
 check('paired comparison11 all original baseline calls',len(examples)==11)
 write(OUT/'instruction_only_cpu_proof.json',dict(status='pass',new_model_calls=0,old_prefix_chars=988,new_prefix_chars=257,old_reaction_examples_active=True,new_reaction_examples_active=False,new_sentence_target_active=False,all11_complete_model_input_parts_unchanged=True,all11_suffix_bytes_unchanged=True,records=examples,baseline_histories_used_for_CPU_comparison_only=True,actual_new_history_unknown_until_generation=True))
