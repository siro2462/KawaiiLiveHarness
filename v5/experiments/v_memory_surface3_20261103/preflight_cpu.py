from common import *
from processor_cpu import load_processor,prepare
from stripe_runtime import render_step,make_context,validate_request,recent,format_reason,groups
from compact_surface import parts,case_for,decoded_parts,TEMPLATE
from baseline_compact import parts as source_parts
from cpu_selector import select
from candidate_projection import make_snapshot
from v5.memory_db.selector_adapter import select_episode
from unittest.mock import patch
import run_cpu,copy,tempfile


def signature(plan,nodes):
 by={n['id']:n['title'] for n in nodes}
 return [(s['content'],s['kind'],s['epistemic'],s['operation'],s['relation'],by.get(s['anchor_id'])) for s in plan['steps']]


def main():
 cfg=verify();base=Path(cfg['source_run']);manifest=read(OUT/'setup_manifest.json');checks=[]
 def check(name,condition):checks.append(dict(name=name,passed=bool(condition)));assert condition,name
 samples=read(OUT/'samples.json');schedule=read(OUT/'unit_schedule.json')
 check('same LoRA complete generation config seed',cfg['surface']==read(base/'protocol.json')['surface'] and cfg['surface_seed']==20260925 and cfg['surface']['generation_config']['max_new_tokens']==1536)
 check('schedule budget exact',len(samples)==3 and cfg['max_calls']==cfg['max_new_model_calls']==len(schedule) and 0<len(schedule)<=12)
 check('no cached output Planner Guard retry training',not cfg['prefix_reuse'] and all(cfg[k]==0 for k in ['new_planner_calls','new_guard_calls','quality_retries','training']))
 for name,h in manifest['unchanged_core'].items():check('same execution source '+name,sha(HERE/name)==sha(base/'executed_source'/name)==h)
 for name,h in manifest['original_v2_sources'].items():check('original full v2 source '+name,sha(HERE/name)==h)
 for p,h in {**manifest['source_db_files'],**manifest['source_material_files']}.items():check('preserved '+Path(p).name,sha(p)==h)
 candidate_source=read(OUT/'source_candidates.json');authored={x['document']['記憶']['記憶ID']:read(OUT/x['authored_source']) for x in candidate_source}
 snapshot,normalized=make_snapshot(candidate_source,authored)
 check('unchanged36 Memory dictionaries',normalized==read(OUT/'source_normalized_candidates.json') and sum(len(n['atoms']) for n in normalized)==36)
 check('pure standalone projection exact',snapshot==read(OUT/'reference/validation_snapshot.json'))
 proc,torch=load_processor();allprior=[];n=0;counts=[]
 for sample in samples:
  sid=sample['id'];selected=select(sample,cfg['engine_seed'])
  check(sid+' CPU selector exact',selected==sample['selection']==read(OUT/'cpu_selections.json')[sid])
  check(sid+' groups are untouched CPU sequence',[o for g in groups(sample) for o in g]==selected['steps'])
  poison=copy.deepcopy(sample);poison['steps']=[dict(operation='POISON')];poison['selection']={}
  check(sid+' ignores manually supplied operation fields',select(poison,cfg['engine_seed'])==selected)
  projected=sample['db_sample'];reversed_sample=copy.deepcopy(projected);reversed_sample['nodes'].reverse();reversed_sample['edges'].reverse()
  reversed_plan=select_episode(reversed_sample,backend='rhythm')
  check(sid+' array reversal leaves content sequence unchanged',signature(selected,projected['nodes'])==signature(reversed_plan,reversed_sample['nodes']))
  renamed=copy.deepcopy(projected);mapping={x['id']:'cpu_alias_'+str(i) for i,x in enumerate(reversed(renamed['nodes']))}
  for node in renamed['nodes']:
   node['id']=mapping[node['id']];node['requires']=[mapping[v] for v in node['requires']]
  for edge in renamed['edges']:edge['src']=mapping[edge['src']];edge['dst']=mapping[edge['dst']]
  renamed_plan=select_episode(renamed,backend='rhythm')
  check(sid+' ID rename leaves content sequence unchanged',signature(selected,projected['nodes'])==signature(renamed_plan,renamed['nodes']))
  prior=[]
  for index in range(len(groups(sample))):
   n+=1;key=sid+f':G{index+1:02}';prompt,payload=render_step(sample,index,prior);actual=prepare(proc,prompt);p=parts(sample,payload);case=case_for(sample,payload);source=source_parts(sample,payload)
   check(key+' original complete v2 prefix',prompt.split('【直前の発話】',1)[0]==TEMPLATE.split('【直前の発話】',1)[0])
   check(key+' all five sections in actual decoded',decoded_parts(actual['decoded_input'])==payload['model_input_parts']==p and len(p)==5)
   check(key+' current source content same order',[f['claim'].split('\n確実性：',1)[0] for f in case['facts']]==[o['content'] for o in payload['operations']])
   check(key+' only up to4 current operations',1<=len(payload['operations'])<=4 and payload['operations']==read(OUT/'unit_templates.json')[key]['operations'])
   check(key+' meanings and certainty present',all(read(OUT/'meaning_legend.json')['OPS'][op['operation']] in p['flow'] and read(OUT/'meaning_legend.json')['EPI'][op['epistemic']] in p['facts'] for op in payload['operations']))
   check(key+' no style additions',all((OUT/f).read_text('utf-8').strip() not in prompt for f in ['reaction_style.txt','unit_instruction.txt','listener_style.txt']))
   check(key+' no management metadata',all(x not in prompt for x in ['snapshot_','rev_','generation_scope','source_inputs_sha256','創作仕様根拠']))
   visible=p['facts']+'\n'+p['relation_summary']
   for q in source['qualifiers']:
    for k,v in q.items():
     if k!='memory_id':check(key+' source qualifier '+q['memory_id']+'/'+k,(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,separators=(',',':'))) in visible)
   check(key+' all unknowns and prohibitions present',all(v in p['relation_summary'] for v in source['limits']['不明']+source['limits']['禁止']))
   check(key+' no input truncation',len(actual['processor_fields']['input_ids'][0])+1536<8192)
   req=dict(call_id=f'R{n:04}',role='surface',seed=cfg['surface_seed'],context=make_context(sample,index,prior,payload),**actual)
   check(key+' actual request contract',validate_request(req,allprior))
   for field in ['seed','prompt','history','operation_order','visible_content']:
    bad=copy.deepcopy(req)
    if field=='seed':bad['seed']+=1
    elif field=='prompt':bad['user_prompt']+='CPU POISON'
    elif field=='history':bad['context']['payload']['history'].append(dict(text='CPU POISON'))
    elif field=='operation_order':
     if len(bad['context']['operations'])>1:bad['context']['operations'].reverse()
     else:bad['context']['operations'].append(copy.deepcopy(bad['context']['operations'][0]))
    else:bad['context']['payload']['model_input_parts']['facts']+='CPU POISON'
    try:validate_request(bad,allprior);raised=False
    except (AssertionError,ValueError,KeyError):raised=True
    check(key+' reject '+field,raised)
   row=dict(call_id=req['call_id'],sample_id=sid,unit_index=index+1,operations=groups(sample)[index],source_step_indices=payload['generation_scope']['source_step_indices'],body='CPU模擬採用'+str(n)+'。',eos=True,delivered=True,semantic_status='unverified')
   counts.append(len(actual['processor_fields']['input_ids'][0]));prior.append(row);allprior.append(row)
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
   check('real bounded controller synthetic held='+str(held),stub.n==cfg['max_calls'] and result['completed_samples']==3 and result['completed_operations']==cfg['selected_operations'])
   check('independent empty initial histories held='+str(held),all(not x['payload']['history'] for x in stub.contexts if x['unit_index']==1))
   check('all CPU steps same order held='+str(held),[s for r in result['records'] for s in r['operations']]==[s for sample in samples for s in sample['steps']])
   check('held excludes adoption and no retry '+str(held),all(r['delivered']==(not held) for r in result['records']))
 check('held excludes history',recent([dict(delivered=False,body='CPU')])==[])
 check('over800 whole message omitted',recent([dict(delivered=True,body='あ'*801,call_id='R9999')])==[])
 check('empty and token cap remain held',format_reason('',True)=='empty' and format_reason('途中。',False)=='incomplete_stop_or_token_cap')
 write(OUT/'cpu_preflight.json',dict(status='pass',check_count=len(checks),checks=checks,new_model_calls=0,prepared_inputs_sha256=sha(OUT/'prepared_inputs.json'),source_db_unchanged=True,source_material_unchanged=True,context_cut_tokens=0,input_token_range=[min(counts),max(counts)]))
 write(OUT/'setup_validation.json',dict(status='pass',original_v2_full_template=True,same_generation_config1536=True,source_Memory_unchanged=True,CPU_selected_not_handordered=True,simulated_history_not_actual_output=True))
 print(json.dumps(dict(status='pass',checks=len(checks),new_model_calls=0,groups=cfg['max_calls'],operations=cfg['selected_operations'],deferred=cfg['selected_deferred'],input_token_range=[min(counts),max(counts)])))
if __name__=='__main__':main()
