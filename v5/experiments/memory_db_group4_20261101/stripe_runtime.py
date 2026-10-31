from common import *
import copy
from full_stripe_runtime import baseline_render,render_sample,style_block,format_reason

def groups(sample):
 steps=sample['steps']
 return [steps[i:i+4] for i in range(0,len(steps),4)]

def validate_prior(sample,index,prior):
 gs=groups(sample)
 assert 0<=index<len(gs) and len(prior)==index
 for j,row in enumerate(prior):
  assert row['sample_id']==sample['id'] and row['unit_index']==j+1
  assert row['operations']==gs[j] and row['source_step_indices']==list(range(j*4+1,min(j*4+5,len(sample['steps'])+1)))
  assert row['semantic_status']=='unverified'
  assert row['delivered']==(format_reason(row['body'],row['eos']) is None)
 return True

def recent(prior):
 kept=[]
 for row in reversed(prior):
  if not row['delivered']:continue
  item=dict(call_id=row['call_id'],text=row['body'],origin='offline generated text; semantically unverified; not Memory')
  if len(kept)==2 or sum(len(x['text']) for x in kept)+len(item['text'])>800:break
  kept.insert(0,item)
 return kept

def render_step(sample,index,prior):
 validate_prior(sample,index,prior)
 original,full=baseline_render(sample);gs=groups(sample);start=index*4;end=min(start+4,len(sample['steps']))
 payload=copy.deepcopy(full);current=copy.deepcopy(full['operations'][start:end])
 assert [x['memory_id'] for x in current]==[x['memory_id'] for x in gs[index]]
 payload['history']=recent(prior);payload['operations']=current
 payload['generation_scope']=dict(unit_index=index+1,total_units=len(gs),current_operations=len(current),source_step_indices=list(range(start+1,end+1)),is_final_unit=index==len(gs)-1,semantic_status='unverified')
 refs=[];seen=set();current_ids={x['memory_id'] for x in current}
 for op in current:
  anchor=op['anchor_id']
  if not anchor or anchor in current_ids or anchor in seen:continue
  matches=[(row,s) for row in prior if row['delivered'] for s in row['operations'] if s['memory_id']==anchor]
  if matches:
   row,s=matches[-1];source=next(x for x in full['operations'] if x['memory_id']==anchor)
   refs.append(dict(memory_id=source['memory_id'],content=source['content'],epistemic=source['epistemic'],execution_status=source['execution_status'],reference_status='previously presented material; not verified as spoken',presented_call_id=row['call_id']));seen.add(anchor)
 payload['previously_presented_reference']=refs
 marker='【記憶と操作の入力】\n';prefix=original.split(marker,1)[0]
 instruction=(OUT/'unit_instruction.txt').read_text('utf-8')
 prompt=prefix+style_block()+instruction+'\n'+marker+json.dumps(payload,ensure_ascii=False,separators=(',',':'))
 return prompt,payload

def make_context(sample,index,prior,payload):
 return dict(experiment=read(OUT/'protocol.json')['experiment'],sample_id=sample['id'],unit_index=index+1,total_units=len(groups(sample)),operations=copy.deepcopy(groups(sample)[index]),payload=payload,
             before=dict(attempted_units=index,history=recent(prior),prior_call_ids=[r['call_id'] for r in prior],semantic_status='unverified'),
             source_inputs_sha256=sha(OUT/'samples.json'),fixed_sequence=True,adaptive_reselection=False,actual_text_feedback=True)

def validate_request(req,prior_global=None):
 cfg=read(OUT/'protocol.json');n=int(req['call_id'][1:]);assert 1<=n<=cfg['max_calls']
 job=read(OUT/'unit_schedule.json')[n-1]
 sample=next(s for s in read(OUT/'samples.json') if s['id']==job['sample_id'])
 if prior_global is None:prior_global=[read(OUT/'turns'/(f'R{i:04}'+'.json')) for i in range(1,n)]
 assert [r['call_id'] for r in prior_global]==[f'R{i:04}' for i in range(1,n)]
 prior=[r for r in prior_global if r['sample_id']==sample['id']]
 index=job['unit_index']-1;prompt,payload=render_step(sample,index,prior)
 assert req['role']=='surface' and req['seed']==cfg['surface_seed']
 assert req['context']==make_context(sample,index,prior,payload) and req['user_prompt']==prompt
 assert req['messages']==[dict(role='user',content=[dict(type='text',text=prompt)])]
 assert req['template_kwargs']==dict(tokenize=True,return_dict=True,return_tensors='pt',add_generation_prompt=True,enable_thinking=False)
 assert len(req['processor_fields']['input_ids'][0])+cfg['surface']['generation_config']['max_new_tokens']<8192
 template=read(OUT/'unit_templates.json')[job['unit_key']]
 assert payload['operations']==template['operations'] and req['context']['operations']==template['source_steps']
 return True
