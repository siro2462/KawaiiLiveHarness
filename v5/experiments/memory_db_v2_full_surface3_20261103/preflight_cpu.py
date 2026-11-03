"""CPU proof: immutable data/conditions, full v2, complete plain Fact delivery."""
from common import *
from processor_cpu import load_processor,prepare
from stripe_runtime import render_step,make_context,validate_request,recent,format_reason,groups
from compact_surface import parts,case_for,decoded_parts,TEMPLATE
from baseline_compact import render as baseline_render,parts as baseline_parts
from full_stripe_runtime import style_block
from cpu_selector import select
from unittest.mock import patch
import run_cpu,copy,tempfile

def main():
 cfg=verify();base=Path(cfg['baseline_run']);manifest=read(OUT/'setup_manifest.json');checks=[]
 def check(n,v):checks.append(dict(name=n,passed=bool(v)));assert v,n
 samples=read(OUT/'samples.json');baseline=read(OUT/'baseline_packet.json')['samples'];schedule=read(OUT/'unit_schedule.json')
 check('same3 entire sample dicts',samples==[s['sample'] for s in baseline] and sha(OUT/'samples.json')==manifest['samples_sha256'])
 check('same LoRA complete generation config1536 seed',cfg['surface']==read(base/'protocol.json')['surface'] and cfg['surface_seed']==read(base/'protocol.json')['surface_seed']==20260925 and cfg['surface']['generation_config']['max_new_tokens']==1536)
 check('same11 contiguous units and40 operations',cfg['max_calls']==cfg['max_new_model_calls']==len(schedule)==11 and [[len(g) for g in groups(s)] for s in samples]==[[4,4,4,2],[4,4,4,2],[4,4,4]])
 check('no cached output Planner Guard retry training',not cfg['prefix_reuse'] and all(cfg[k]==0 for k in ['new_planner_calls','new_guard_calls','quality_retries','training']))
 for name,h in manifest['unchanged_core'].items():check('unchanged execution core '+name,sha(HERE/name)==sha(base/'executed_source'/name)==h)
 for name,h in manifest['original_v2_sources'].items():check('original full v2 source exact '+name,sha(HERE/name)==h)
 for p,h in manifest['source_db_files'].items():check('source DB byte unchanged '+Path(p).name,sha(p)==h)
 check('same deferred1',sum(len(s['selection']['deferred_nodes']) for s in samples)==1)
 proc,torch=load_processor();equal=[];allprior=[];n=0;counts=[]
 for sample,saved in zip(samples,baseline):
  check(sample['id']+' selector exact',select(sample,cfg['engine_seed'])==sample['selection']==read(OUT/'cpu_selections.json')[sample['id']])
  check(sample['id']+' all operations same',[o for g in groups(sample) for o in g]==sample['steps'])
  prior=[]
  for index,old in enumerate(saved['turns']):
   n+=1;key=sample['id']+f':G{index+1:02}';oldreq=old['request'];oldpayload=oldreq['context']['payload']
   oldprompt,oldparts=baseline_render(sample,oldpayload,style_block(),(OUT/'unit_instruction.txt').read_text('utf-8'))
   check(key+' reproduce saved actual A prompt and all official processor fields',oldprompt==oldreq['user_prompt'] and all(oldreq[k]==v for k,v in prepare(proc,oldprompt).items()))
   check(key+' fixed old generation settings',old['output']['generation_config']==cfg['surface']['generation_config'] and old['output']['seed']==cfg['surface_seed'] and not old['output']['adapter_disabled'])
   prompt,payload=render_step(sample,index,prior);actual=prepare(proc,prompt);p=parts(sample,payload);case=case_for(sample,payload);source=baseline_parts(sample,payload)
   check(key+' payload all semantic data unchanged',all(payload[k]==v for k,v in oldpayload.items() if k!='model_input_parts'))
   check(key+' original five section decoded exact',decoded_parts(actual['decoded_input'])==payload['model_input_parts']==p)
   check(key+' original complete v2 instructions only',prompt.split('【直前の発話】',1)[0]==TEMPLATE.split('【直前の発話】',1)[0] and len(p)==5)
   check(key+' no appended fewshot guide listener blocks',all((OUT/f).read_text('utf-8').strip() not in prompt for f in ['reaction_style.txt','unit_instruction.txt','listener_style.txt']))
   check(key+' current operation content same order',[f['claim'].split('\n確実性：',1)[0] for f in case['facts']]==[o['content'] for o in payload['operations']])
   check(key+' context IDs only short facts',all(x not in prompt for x in ['snapshot_','rev_','generation_scope','source_inputs_sha256']))
   check(key+' operation semantics and certainty delivered',all(read(OUT/'meaning_legend.json')['OPS'][op['operation']] in p['flow'] and read(OUT/'meaning_legend.json')['EPI'][op['epistemic']] in p['facts'] for op in payload['operations']))
   all_visible=p['facts']+'\n'+p['relation_summary']
   for q in source['qualifiers']:
    for k,v in q.items():
     if k!='memory_id':check(key+' qualifier '+q['memory_id']+'/'+k,(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,separators=(',',':'))) in all_visible)
   check(key+' theme context unknowns preserved',all((v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,separators=(',',':'))) in p['relation_summary'] for v in [source['theme']['話題'],source['theme']['話の中心']]+source['theme']['世界']+source['limits']['不明']+source['limits']['禁止']))
   check(key+' actual old history only for CPU comparison',payload['history']==recent(prior))
   check(key+' no context truncation',len(actual['processor_fields']['input_ids'][0])+1536<8192)
   req=dict(call_id=f'R{n:04}',role='surface',seed=cfg['surface_seed'],context=make_context(sample,index,prior,payload),**actual)
   check(key+' full request contract',validate_request(req,allprior))
   for field in ['seed','prompt','history','operation_order','visible_content']:
    bad=copy.deepcopy(req)
    if field=='seed':bad['seed']+=1
    elif field=='prompt':bad['user_prompt']+='CPU POISON'
    elif field=='history':bad['context']['payload']['history'].append(dict(text='CPU POISON'))
    elif field=='operation_order':bad['context']['operations'].reverse()
    else:bad['context']['payload']['model_input_parts']['facts']+='CPU POISON'
    try:validate_request(bad,allprior);raised=False
    except (AssertionError,ValueError,KeyError):raised=True
    check(key+' reject '+field,raised)
   equal.append(dict(unit_key=key,source_call_id=old['row']['call_id'],old_input_tokens=len(old['output']['input_ids']),new_equal_history_input_tokens=len(actual['processor_fields']['input_ids'][0]),old_prompt_chars=len(oldprompt),new_equal_history_prompt_chars=len(prompt),new_plain_parts_chars=sum(len(v) for v in p.values()),old_card_parts_chars=sum(len(json.dumps(v,ensure_ascii=False)) for v in oldparts.values()),source_current_contents_exact=True,all_qualifiers_present=True,original_full_template=True))
   counts.append(len(actual['processor_fields']['input_ids'][0]));prior.append(old['row']);allprior.append(old['row'])
 class Stub:
  def __init__(self,held):self.n=0;self.held=held;self.prior=[];self.contexts=[]
  def call(self,role,prompt,seed,context):
   self.n+=1;actual=prepare(proc,prompt);req=dict(call_id=f'R{self.n:04}',role=role,seed=seed,context=context,**actual);assert validate_request(req,self.prior)
   body='' if self.held else 'CPU模擬の採用文'+str(self.n)+'。'
   self.prior.append(dict(call_id=req['call_id'],sample_id=context['sample_id'],unit_index=context['unit_index'],operations=context['operations'],source_step_indices=context['payload']['generation_scope']['source_step_indices'],body=body,eos=True,delivered=not self.held,semantic_status='unverified'));self.contexts.append(context)
   return req['call_id'],dict(body=body,raw_output=body+'<turn|>',official_stop_reached=True)
 for held in [False,True]:
  with tempfile.TemporaryDirectory(dir=OUT/'cpu_temp') as temp:
   q=Path(temp)
   for name in ['samples.json','cpu_selections.json','unit_schedule.json']:write(q/name,read(OUT/name))
   with patch.object(run_cpu,'OUT',q):stub=Stub(held);result=run_cpu.rollout(stub,cfg)
   check('real controller11 synthetic held='+str(held),stub.n==11 and result['completed_samples']==3 and result['completed_operations']==40)
   check('independent sample initial empty held='+str(held),all(not x['payload']['history'] for x in stub.contexts if x['unit_index']==1))
   check('all40 source order held='+str(held),[s for row in result['records'] for s in row['operations']]==[s for sample in samples for s in sample['steps']])
   check('no quality retry held='+str(held),all(r['delivered']==(not held) for r in result['records']))
 check('held excludes history',recent([dict(delivered=False,body='CPU')])==[])
 check('over800 whole message omitted',recent([dict(delivered=True,body='あ'*801,call_id='R9999')])==[])
 check('empty and cap format holds',format_reason('',True)=='empty' and format_reason('途中。',False)=='incomplete_stop_or_token_cap')
 write(OUT/'equal_history_comparison.json',dict(status='pass',scope='CPU equal saved A histories only; never injected into actual B rollout',records=equal))
 write(OUT/'cpu_preflight.json',dict(status='pass',check_count=len(checks),checks=checks,new_model_calls=0,prepared_inputs_sha256=sha(OUT/'prepared_inputs.json'),source_db_unchanged=True,context_cut_tokens=0,new_equal_history_token_range=[min(counts),max(counts)]))
 write(OUT/'setup_validation.json',dict(status='pass',same_Memory_CPU_sequence=True,original_v2_full_template=True,same_generation_config1536=True,simulated_history_not_actual_output=True))
 print(json.dumps(dict(status='pass',checks=len(checks),new_model_calls=0,groups=11,operations=40,input_token_range=[min(counts),max(counts)])))
if __name__=='__main__':main()
