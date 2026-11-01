from common import *
import copy,tempfile
from unittest.mock import patch
from processor_cpu import load_processor,prepare
from full_stripe_runtime import render_sample as render_whole
from stripe_runtime import render_step,make_context,validate_request,recent,format_reason,groups
from prepare_inputs import fake_prior
from cpu_selector import select
import run_cpu
from compact_surface import decoded_parts,parts

def main():
 cfg=verify();samples=read(OUT/'samples.json');schedule=read(OUT/'unit_schedule.json');checks=[]
 def check(n,v):checks.append(dict(name=n,passed=bool(v)));assert v,n
 basecfg=read(Path(cfg['baseline_run'])/'protocol.json')
 check('same3 and grouped11 budget',[s['id'] for s in samples]==['M06','M17','M23'] and cfg['max_calls']==cfg['max_new_model_calls']==len(schedule)==11)
 check('fixed contiguous grouping sizes',[[len(g) for g in groups(s)] for s in samples]==[[4,4,4,2],[4,4,4,2],[4,4,4]])
 check('same LoRA generation seed',cfg['surface']==basecfg['surface'] and cfg['surface_seed']==basecfg['surface_seed']==20260925)
 check('no replay Planner Guard training',cfg['prefix_reuse']==[] and all(cfg[k]==0 for k in ['new_planner_calls','new_guard_calls','training','quality_retries']))
 check('same style bytes',all(sha(OUT/n)==sha(Path(cfg['baseline_run'])/n) for n in ['reaction_style.txt','grouping_style.txt']))
 for name,h in read(OUT/'setup_manifest.json')['unchanged_core'].items():check('unchanged core '+name,sha(HERE/name)==h==sha(Path(cfg['baseline_run'])/'executed_source'/name))
 baseline=read(OUT/'baseline_packet.json')['samples']
 check('all entire sample dicts unchanged',[t['sample'] for t in baseline]==samples)
 check('same40 operations held1',sum(len(s['steps']) for s in samples)==40 and sum(len(s['selection']['deferred_nodes']) for s in samples)==1)
 proc,torch=load_processor();saved=read(OUT/'prepared_inputs.json')['by_unit'];allprior=[];n=0;counts=[]
 for sample,base in zip(samples,baseline):
  sid=sample['id'];gs=groups(sample)
  check(sid+' CPU selection exact',select(sample,cfg['engine_seed'])==sample['selection']==read(OUT/'cpu_selections.json')[sid])
  check(sid+' flatten groups preserves full source order',[s for g in gs for s in g]==sample['steps'])
  whole,full=render_whole(sample)
  check(sid+' source entire Memory unchanged',base['sample']==sample)
  check(sid+' saved group4 full payloads same',[op for t in base['turns'] for op in t['request']['context']['payload']['operations']]==full['operations'])
  check(sid+' old group4 schedule unchanged',[t['row']['operations'] for t in base['turns']]==gs)
  prior=[];start=n+1
  for index,steps in enumerate(gs):
   n+=1;key=sid+f':G{index+1:02}'
   check(key+' fixed schedule',schedule[n-1]==dict(unit_key=key,sample_id=sid,unit_index=index+1))
   prompt,payload=render_step(sample,index,prior);actual=prepare(proc,prompt)
   check(key+' exact contiguous current full operations',payload['operations']==full['operations'][index*4:index*4+4] and payload['generation_scope']['current_operations']==len(steps))
   check(key+' source indices and final flag',payload['generation_scope']['source_step_indices']==list(range(index*4+1,min(index*4+5,len(sample['steps'])+1))) and payload['generation_scope']['is_final_unit']==(index==len(gs)-1))
   check(key+' recent adopted text exact',payload['history']==recent(prior) and len(payload['history'])<=2 and sum(len(h['text']) for h in payload['history'])<=800)
   check(key+' prior anchors only',all(x['memory_id'] in {op['memory_id'] for row in prior if row['delivered'] for op in row['operations']} for x in payload['previously_presented_reference']))
   check(key+' header unknowns authority unchanged',all(payload[k]==v for k,v in full.items() if k not in ['history','operations']))
   decoded=decoded_parts(actual['decoded_input'])
   check(key+' official decoded all visible parts exact',decoded==payload['model_input_parts']==parts(sample,payload))
   check(key+' management fields excluded',all(x not in actual['user_prompt'] for x in ['snapshot_','rev_','history_authority','generation_scope']))
   check(key+' eight original card fields only',all(len(c)==8 for c in decoded['operations']))
   check(key+' content unchanged ordered',[c['content'] for c in decoded['operations']]==[op['content'] for op in steps])
   check(key+' Japanese operation epistemic legends',all(c['operation'] in decoded['operations_legend'] and c['epistemic'] in decoded['epistemic_legend'] for c in decoded['operations']))
   check(key+' actual history text only',decoded['history_text']==('\n\n'.join(r['text'] for r in recent(prior)) or 'なし'))
   qby={q['memory_id']:q for q in decoded['qualifiers']}
   by={node['id']:node for node in sample['db_sample']['nodes']}
   for op in steps:
    node=by[op['memory_id']];side=node['sidecar'];attrs=side['attributes'];lid=side['local_id'];q=qby.get(lid,{})
    for attr in ['いつの望み・期待か','確かさ','状態']:
     if attr in attrs:check(key+' '+lid+' exact '+attr,q.get(attr)==attrs[attr])
    if side['execution_status'] in ['desired','planned']:check(key+' '+lid+' unexecuted distinction','実行' in q.get('実行の区別','') and 'しない' in q['実行の区別'])
   check(key+' no truncation with fixed1536',len(actual['processor_fields']['input_ids'][0])+1536<8192)
   sim,_=render_step(sample,index,fake_prior(sample,index,start,True))
   check(key+' saved synthetic template exact',prepare(proc,sim)==saved[key]['simulated_history'])
   req=dict(call_id=f'R{n:04}',role='surface',seed=cfg['surface_seed'],context=make_context(sample,index,prior,payload),**actual)
   check(key+' dynamic request accepted',validate_request(req,allprior))
   for field in ['seed','history','prompt','operation_order']:
    bad=copy.deepcopy(req)
    if field=='seed':bad['seed']+=1
    elif field=='history':bad['context']['payload']['history'].append(dict(text='別素材の発話',call_id='R9999',origin='bad'))
    elif field=='prompt':bad['user_prompt']+='未提示の操作'
    else:bad['context']['operations'].reverse()
    try:validate_request(bad,allprior);raised=False
    except (AssertionError,ValueError,KeyError):raised=True
    check(key+' reject '+field,raised)
   row=dict(call_id=f'R{n:04}',sample_id=sid,unit_index=index+1,operations=steps,source_step_indices=payload['generation_scope']['source_step_indices'],body='CPU模擬の採用本文'+str(n)+'。',eos=True,delivered=True,semantic_status='unverified')
   prior.append(row);allprior.append(row);counts.append(dict(unit_key=key,input_tokens=len(actual['processor_fields']['input_ids'][0]),operations=len(steps)))
 check('recent actual two calls',[x['call_id'] for x in recent(allprior[-3:])]==['R0010','R0011'])
 big=copy.deepcopy(allprior[-1]);big['body']='あ'*801
 check('over800 history omitted whole',recent([big])==[])
 held=copy.deepcopy(allprior[-1]);held.update(body='',delivered=False)
 check('held excluded',recent([held])==[])
 class Stub:
  def __init__(self,held):self.n=0;self.held=held;self.prior=[];self.contexts=[]
  def call(self,role,prompt,seed,context):
   self.n+=1;actual=prepare(proc,prompt)
   req=dict(call_id=f'R{self.n:04}',role=role,seed=seed,context=context,**actual)
   assert validate_request(req,self.prior)
   body='' if self.held else '模擬の採用本文'+str(self.n)+'。'
   self.prior.append(dict(call_id=req['call_id'],sample_id=context['sample_id'],unit_index=context['unit_index'],operations=context['operations'],source_step_indices=context['payload']['generation_scope']['source_step_indices'],body=body,eos=True,delivered=not self.held,semantic_status='unverified'))
   self.contexts.append(context)
   return req['call_id'],dict(body=body,raw_output=body+'<turn|>',official_stop_reached=True)
 for held_mode in [False,True]:
  with tempfile.TemporaryDirectory(dir=OUT/'cpu_temp') as tmp:
   q=Path(tmp)
   for name in ['samples.json','cpu_selections.json','unit_schedule.json']:write(q/name,read(OUT/name))
   with patch.object(run_cpu,'OUT',q):stub=Stub(held_mode);result=run_cpu.rollout(stub,cfg)
   check('actual controller11 held='+str(held_mode),stub.n==len(result['records'])==11 and result['completed_samples']==3)
   check('reset sample history held='+str(held_mode),all(not c['payload']['history'] for c in stub.contexts if c['unit_index']==1))
   check('all40 attempted order held='+str(held_mode),[s for row in result['records'] for s in row['operations']]==[s for sample in samples for s in sample['steps']])
   check('format held no retry '+str(held_mode),all(row['delivered']==(not held_mode) for row in result['records']) and result['completed_operations']==40)
 w2=next(n for n in samples[2]['db_sample']['nodes'] if n['sidecar']['local_id']=='W2')
 p23,_=render_step(samples[2],2,fake_prior(samples[2],2,9,True))
 check('M23 W2 failure-after hope and next execution unspecified in actual decoded',w2['sidecar']['attributes']['いつの望み・期待か'] in prepare(proc,p23)['decoded_input'])
 check('deferred M23 P1 never requested',all(op['memory_id'].rsplit(':',1)[-1]!='P1' for op in samples[2]['steps']))
 check('empty held',format_reason('',True)=='empty')
 check('cap held',format_reason('途中。',False)=='incomplete_stop_or_token_cap')
 write(OUT/'cpu_preflight.json',dict(status='pass',check_count=len(checks),checks=checks,counts=counts,new_model_calls=0,prepared_inputs_sha256=sha(OUT/'prepared_inputs.json'),unit_templates_sha256=sha(OUT/'unit_templates.json'),real_history_requests_must_be_replayed_after_generation=True,context_cut_tokens=0))
 write(OUT/'setup_validation.json',dict(status='pass',up_to4_operations_per_call=True,same_Memory_CPU_sequence=True,simulated_history_not_actual_output=True))
 print(json.dumps(dict(status='pass',checks=len(checks),groups=11,operations=40,new_model_calls=0,input_token_range=[min(x['input_tokens'] for x in counts),max(x['input_tokens'] for x in counts)]),ensure_ascii=False))
if __name__=='__main__':main()
