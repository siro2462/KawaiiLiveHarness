from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parent/'runs/surface_v2_replay_20261102_v1';D=R/'root_read';D.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=json.loads((R/'review_packet.json').read_text('utf-8-sig'));proof=[]
first=p['pairs'][0]['A']['request'];header=first['user_prompt'].split('【直前の発話】',1)[0]
decoded_prefix,decoded_suffix=first['decoded_input'].split(first['user_prompt'].rstrip('\n'))
generation_config=p['pairs'][0]['A']['output']['generation_config']
for item in p['pairs']:
 a,b=item['A'],item['B'];pair=item['pair'];cid=pair['pair_id']
 assert a['request']==b['request'] and a['output']['input_ids']==b['output']['input_ids'] and a['output']['output_ids']==b['output']['output_ids']
 for k in ['raw_output','generation_config','seed']:assert a['output'][k]==b['output'][k]
 for k in ['body','parsed','raw_output']:assert a['delivery'][k]==b['delivery'][k]
 assert a['request']['context']['case']==pair['case']
 assert a['request']['messages']==[dict(role='user',content=[dict(type='text',text=a['request']['user_prompt'])])]
 request={k:v for k,v in a['request'].items() if k not in ['processor_fields','context','messages']}
 request['context']={k:v for k,v in a['request']['context'].items() if k!='case'}
 output={k:v for k,v in b['output'].items() if k not in ['input_ids','output_ids','resources','request_sha256','journal_sha256']}
 view=dict(pair_id=cid,memory_id=pair['memory_id'],case=pair['case'],source_memory=pair['source_memory'],source_facts=pair['source_facts'],full_shared_request=request,full_shared_delivery={k:v for k,v in b['delivery'].items() if k not in ['request_sha256','output_sha256']},current_row=b['row'],output_metadata=output,old_seconds=a['output']['seconds'],new_seconds=b['output']['seconds'],old_new_input_tokens=[len(a['output']['input_ids']),len(b['output']['input_ids'])],old_new_output_tokens=[len(a['output']['output_ids']),len(b['output']['output_ids'])])
 # current_row can contain the same body/raw again, but never replace distinct text with omission.
 write(D/(cid+'.json'),view)
 assert request['user_prompt'].startswith(header)
 suffix=request['user_prompt'][len(header):]
 assert request['decoded_input']==decoded_prefix+(header+suffix).rstrip('\n')+decoded_suffix
 assert b['output']['generation_config']==generation_config and b['row']['case']==pair['case']
 for k in ['body','raw_output']:assert b['row'][k]==b['delivery'][k]
 thin=dict(pair_id=cid,memory_id=pair['memory_id'],case=pair['case'],source_memory=pair['source_memory'],source_facts=pair['source_facts'],request_metadata={k:v for k,v in request.items() if k not in ['user_prompt','decoded_input']},user_prompt_full_unique_suffix=suffix,decoded_prefix_shared=decoded_prefix,decoded_suffix_shared=decoded_suffix,shared_header_already_full_read_in='P01.json',full_actual_decoded_reconstruction='decoded_prefix + (shared exact header + unique suffix).rstrip(newline) + decoded_suffix; CPU all characters exact',delivery=view['full_shared_delivery'],row_state={k:v for k,v in b['row'].items() if k not in ['case','body','raw_output']},output_metadata={k:v for k,v in output.items() if k not in ['raw_output','generation_config']},generation_config_exact_to_already_read_P01=True,old_seconds=a['output']['seconds'],new_seconds=b['output']['seconds'],input_tokens=len(b['output']['input_ids']),output_tokens=len(b['output']['output_ids']))
 write(D/(cid+'_thin.json'),thin)
 proof.append(dict(pair_id=cid,all_request_fields_identical=True,input_and_output_token_arrays_identical=True,RAW_body_parsed_generation_config_seed_identical=True,request_context_case_is_displayed_case=True,messages_are_exact_user_prompt=True,view_sha256=sha(D/(cid+'.json'))))
refs=[x for x in p['references'] if x['memory_id'] in ['H04','H06','H07']];assert len(refs)==3
write(D/'human_references.json',refs)
write(D/'view_proof.json',dict(status='pass',review_packet_sha256=sha(R/'review_packet.json'),pairs=proof,all_distinct_required_text_displayed=True,deduplication='A/B full equal strings shown once; numeric token arrays audited by CPU',thin_views=dict(shared_header_sha256=hashlib.sha256(header.encode()).hexdigest(),shared_header_full_view='P01.json',all_prompt_and_decoded_reconstructed_character_exact=True,same_complete_generation_config=True),human_references_sha256=sha(D/'human_references.json')))
print(json.dumps(dict(status='views_ready',pairs=4,human_references=3,all4_A_B_text_and_tokens_exact=True)))
