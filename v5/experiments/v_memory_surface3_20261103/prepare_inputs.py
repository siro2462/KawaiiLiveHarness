from common import *
from processor_cpu import load_processor,prepare
from full_stripe_runtime import render_sample as render_whole
from compact_surface import decoded_parts
from stripe_runtime import render_step,groups


def fake_prior(sample,index,start,delivered):
 return [dict(call_id=f'R{start+j:04}',sample_id=sample['id'],unit_index=j+1,operations=groups(sample)[j],source_step_indices=list(range(j*4+1,min(j*4+5,len(sample['steps'])+1))),body=('CPU模擬の実履歴'+str(j+1)+'。') if delivered else '',eos=True,delivered=delivered,semantic_status='unverified') for j in range(index)]


def main():
 cfg=verify();proc,torch=load_processor();templates={};prepared={};proof=[];start=1
 for sample in read(OUT/'samples.json'):
  _,base_payload=render_whole(sample)
  for index,source_steps in enumerate(groups(sample)):
   key=sample['id']+f':G{index+1:02}'
   empty,_=render_step(sample,index,fake_prior(sample,index,start,False))
   prompt,payload=render_step(sample,index,fake_prior(sample,index,start,True));official=prepare(proc,prompt)
   templates[key]=dict(sample_id=sample['id'],unit_index=index+1,source_steps=source_steps,operations=base_payload['operations'][index*4:index*4+4])
   prepared[key]=dict(empty_history=prepare(proc,empty),simulated_history=official,warning='CPU synthetic history only; actual input rebuilt from adopted model outputs')
   assert payload['operations']==templates[key]['operations']
   assert decoded_parts(official['decoded_input'])==payload['model_input_parts']
   proof.append(dict(unit_key=key,operation_count=len(source_steps),source_step_indices=payload['generation_scope']['source_step_indices'],input_tokens_empty=len(prepared[key]['empty_history']['processor_fields']['input_ids'][0]),input_tokens_simulated=len(official['processor_fields']['input_ids'][0]),current_group4_full_source_payloads_exact=True,visible_model_parts_exact=True))
  start+=len(groups(sample))
 assert len(templates)==cfg['max_calls']
 write(OUT/'unit_templates.json',templates);write(OUT/'prepared_inputs.json',dict(kind='CPU synthetic examples, not actual dynamic-history requests',by_unit=prepared))
 write(OUT/'input_template_proof.json',dict(status='pass',records=proof,new_model_calls=0,actual_history_known_only_after_generation=True))
 print(json.dumps(dict(status='prepared',groups=len(templates),model_calls=0,input_tokens_empty=[min(x['input_tokens_empty'] for x in proof),max(x['input_tokens_empty'] for x in proof)])))
if __name__=='__main__':main()
