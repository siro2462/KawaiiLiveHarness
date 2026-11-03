"""CPU-only lossless review views. Never invoke inference or alter generated text."""
from pathlib import Path
import json,hashlib,os,sys,re
R=Path(__file__).resolve().parent/'runs/memory_db_v2_full_surface3_20261103_v1';D=R/'root_read';D.mkdir(exist_ok=True)
os.environ['ZIP_INCREMENTAL_RUN']=str(R);sys.path.insert(0,str(R/'executed_source'))
from compact_surface import TEMPLATE,parts,case_for
def read(p):return json.loads(p.read_text('utf-8-sig'))
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
packet=read(R/'review_packet.json');old=Path(read(R/'protocol.json')['baseline_run']);oldpacket=read(old/'review_packet.json');oldreview=read(old/'root_review.json');oldread=read(old/'root_read/reading_progress.json')
assert oldreview['root_full_text_read'] and oldread['root_full_text_read'] and oldread['unread_unique_text']==[]
first=packet['samples'][0]['turns'][0]['request'];pre,post=first['decoded_input'].split(first['user_prompt'].rstrip('\n'))
(D/'common.txt').write_text('【原v2全文テンプレート】\n'+TEMPLATE+'\n【公式decoded prefix】\n'+pre+'\n【公式decoded suffix】\n'+post+'\n',encoding='utf-8')
proof=[];reuse=[]
for sample,prior in zip(packet['samples'],oldpacket['samples']):
 s=sample['sample'];sid=s['id'];assert s==prior['sample'] and sample['baseline']['turns']==prior['turns'] and sample['baseline']['full_text']==prior['full_text']
 reuse.append(dict(sample_id=sid,all_source_sample_fields_exact=True,all_baseline_actual_turn_fields_exact=True,prior_root_review_sha256=sha(old/'root_review.json'),prior_full_read_progress_sha256=sha(old/'root_read/reading_progress.json')))
 def short(mid):return mid.rsplit(':',1)[-1] if mid else None
 nodes=[]
 for n in s['db_sample']['nodes']:
  q=n['sidecar'];a=q['attributes']
  nodes.append(dict(id=q['local_id'],content=n['content'],origin=q['origin'],epistemic=n['epistemic'],execution_status=q['execution_status'],attributes={k:v for k,v in a.items() if k not in ['ID','内容']},evidence=q['evidence']))
 write(D/(sid+'_source.json'),dict(sample_id=sid,title=s['title'],review_status=s['review_status'],context=s['surface']['payload']['context'],central_theme=s['surface']['payload']['central_theme'],unknowns=s['surface']['payload']['unknowns'],prohibitions=s['surface']['payload']['prohibitions'],nodes=nodes,operations=[dict(index=x['index'],memory=short(x['memory_id']),operation=x['operation'],kind=x['kind'],epistemic=x['epistemic'],relation=x['relation'],anchor=short(x['anchor_id'])) for x in s['steps']],deferred=s['selection']['deferred_nodes'],raw_document_reused_by_full_dict_equality=True))
 views=[];by={t['row']['call_id']:t for t in sample['turns']}
 for oldturn,t in zip(sample['baseline']['turns'],sample['turns']):
  req=t['request'];payload=req['context']['payload'];p=parts(s,payload);assert p==payload['model_input_parts'];case=case_for(s,payload)
  prompt=re.sub(r'\{\{(history|operation|relation_summary|facts|flow)\}\}',lambda m:p[m[1]],TEMPLATE)
  assert prompt==req['user_prompt'] and req['decoded_input']==pre+prompt.rstrip('\n')+post
  assert req['messages']==[dict(role='user',content=[dict(type='text',text=prompt)])]
  hist=payload['history'];assert p['history']==('\n\n'.join(f'[{i+1}] {h["text"]}' for i,h in enumerate(hist)) or 'なし')
  for h in hist:assert by[h['call_id']]['row']['delivered'] and by[h['call_id']]['delivery']['body']==h['text']
  assert t['row']['body']==t['delivery']['body'] and t['row']['raw_output']==t['output']['raw_output']==t['delivery']['raw_output']
  views.append(dict(call_id=req['call_id'],unit_index=t['row']['unit_index'],source_step_indices=t['row']['source_step_indices'],before_history_refs=[h['call_id'] for h in hist],history_string_reconstructed_from_already_displayed_prior_bodies=True,full_distinct_model_parts={k:v for k,v in p.items() if k!='history'},baseline_body=oldturn['delivery']['body'],new_RAW=t['output']['raw_output'],new_body=t['delivery']['body'],new_parsed=t['delivery']['parsed'],format_reason=t['row']['format_reason'],delivered=t['row']['delivered'],semantic_status=t['row']['semantic_status'],after_history_refs=[h['call_id'] for h in t['row']['after_history']],old_new_input_tokens=[len(oldturn['output']['input_ids']),len(t['output']['input_ids'])],old_new_output_tokens=[len(oldturn['output']['output_ids']),len(t['output']['output_ids'])],old_new_model_seconds=[oldturn['output']['seconds'],t['output']['seconds']],eos=t['output']['official_stop_reached'],generation_config_matches_baseline=oldturn['output']['generation_config']==t['output']['generation_config']))
  proof.append(dict(call_id=req['call_id'],all_prompt_decoded_characters_reconstructed_exact=True,actual_history_text_equals_prior_delivered_bodies=True,model_parts_case_source_exact=True,RAW_body_same_as_delivery_row=True,request_sha256=sha(R/'requests'/(req['call_id']+'.json'))))
 write(D/(sid+'_turns.json'),views)
 compact=[]
 for v in views:
  assert v['new_RAW']==v['new_body']+'<turn|>' and v['new_parsed']==dict(role='assistant',content=v['new_body'])
  compact.append({k:val for k,val in v.items() if k not in ['new_body','new_parsed']}|dict(new_body_and_parsed_content_exactly_equal_RAW_without_terminal='<turn|>'))
 write(D/(sid+'_compact_turns.json'),compact)
write(D/'view_proof.json',dict(status='pass',review_packet_sha256=sha(R/'review_packet.json'),common_template_sha256=hashlib.sha256(TEMPLATE.encode()).hexdigest(),new_calls=proof,reused_previously_root_full_read_source_and_A=reuse,compact_views='For every call, RAW equals body plus exact terminal <turn|>; parsed is assistant/content with that exact body; all characters recoverable',numeric_token_arrays='official CPU completion audit; not elided text',new_text_read_status='not yet marked read'))
print(json.dumps(dict(status='views_ready',source_samples=3,new_calls=11,full_character_reconstruction_exact=True,previous_source_A_reuse_exact=True)))
