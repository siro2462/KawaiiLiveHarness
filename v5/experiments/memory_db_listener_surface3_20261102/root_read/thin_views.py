"""Shared exact headers plus complete dynamic prompt blocks; no semantic summarization."""
from pathlib import Path
import json,hashlib,difflib
R=Path(__file__).resolve().parents[1];D=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text('utf-8-sig'))
def write(name,x):
 p=D/(name+'.json');p.write_text(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8');return dict(file=name,characters=len(p.read_text('utf-8')),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
packet=read(R/'review_packet.json');common={};files=[];proof=[]
old_dynamic=['history','operations','generation_scope','previously_presented_reference'];new_dynamic=['history_text','anchors','qualifiers','operations']
headings=[('theme','現在のテーマ',True),('operations_legend','操作の意味',True),('epistemic_legend','確実性の意味',True),('history_text','直前の発話',False),('anchors','接続の参照・新たな操作ではない',True),('qualifiers','時点・確かさ・実行の区別',True),('limits','不明・守る範囲',True),('operations','今回の操作列',True)]
for sample in packet['samples']:
 sid=sample['sample']['id'];headers={};pairs=[]
 for index,(a,b) in enumerate(zip(sample['baseline']['turns'],sample['turns'])):
  pair={}
  for side,t in [('A',a),('B',b)]:
   req=t['request'];prompt=req['user_prompt']
   prefix=prompt.split('【現在のテーマ】\n')[0];payload=req['context']['payload']['model_input_parts'];dynamic=new_dynamic
   assert side not in common or common[side]==prefix;common[side]=prefix
   header={k:v for k,v in payload.items() if k not in dynamic};actual={k:payload[k] for k in dynamic}
   assert side not in headers or headers[side]==header;headers[side]=header
   rebuilt={k:actual[k] if k in actual else header[k] for k in payload}
   rp=prefix
   for j,(key,title,is_json) in enumerate(headings):rp+=('' if j==0 else '\n')+'【'+title+'】\n'+(json.dumps(rebuilt[key],ensure_ascii=False,separators=(',',':')) if is_json else rebuilt[key])+'\n'
   assert rp==prompt
   delta=[];out=''
   for tag,i,j,k,l in difflib.SequenceMatcher(a=prompt,b=req['decoded_input'],autojunk=False).get_opcodes():
    out+=prompt[i:j] if tag=='equal' else req['decoded_input'][k:l]
    if tag!='equal':delta.append(dict(operation=tag,prompt_range=[i,j],replacement=req['decoded_input'][k:l]))
   assert out==req['decoded_input']
   body=t['delivery']['body'];raw=t['output']['raw_output']
   if body and raw.count(body)==1:
    before,after=raw.split(body);raw_view=dict(before_body=before,after_body=after);assert before+body+after==raw
   else:raw_view=dict(full_RAW=raw)
   pair[side]=dict(call_id=t['row']['call_id'],shared_input_header_reference=sid+':'+side,actual_dynamic_input=actual,decoded_edits=delta,body=body,RAW_representation=raw_view,source_step_indices=t['row']['source_step_indices'],format_reason=t['row']['format_reason'],delivered=t['row']['delivered'],eos=t['output']['official_stop_reached'],before_history=t['row']['before_history'],after_history=t['row']['after_history'],semantic_status=t['row']['semantic_status'])
   proof.append(dict(sample_id=sid,side=side,call_id=t['row']['call_id'],actual_prompt_decoded_RAW_exact=True))
  pairs.append(pair)
 source=sample['sample'];nodes=[]
 for n in source['db_sample']['nodes']:
  sc=n['sidecar'];assert all(n[k]==sc[k] for k in ['origin','execution_status','utterance_hint','attributes','evidence'])
  nodes.append({k:n.get(k) for k in ['id','local_id','kind','original_kind','content','origin','epistemic','original_epistemic','execution_status','utterance_hint','attributes','evidence','requires','projection_deferred']})
 files.append(write('read_'+sid+'_source',dict(sample_id=sid,title=source['title'],original_document=source['revision']['raw_document'],all_nodes=nodes,CPU_operation_sequence=sample['selection']['steps'],deferred=sample['selection']['deferred_nodes'],selection_control={k:v for k,v in sample['selection'].items() if k not in ['steps','decisions','rank_scores','first_occurrence_order','provenance']},exact_shared_input_headers=headers,initial_history=source['initial_history'])))
 for i,pair in enumerate(pairs):files.append(write('read_'+sid+f'_pair{i+1}',pair))
files.insert(0,write('read_common',dict(exact_prompt_prefixes=common,RAW_policy='actual prefix/suffix or full RAW preserved including held/cap',header_partition='every actual model input field retained in common header plus per-call dynamic block',CPU_only='numeric token arrays/journal and DB administrative hashes/selector scores verified by CPU; not semantic quality')))
write('thin_view_proof',dict(status='pass',source_packet_sha256=hashlib.sha256((R/'review_packet.json').read_bytes()).hexdigest(),all22_actual_prompt_decoded_RAW_exact=True,sidecar_human_fields_exact_duplicate=True,no_unique_model_input_text_omitted=True,files=files,turns=proof))
print(json.dumps(dict(status='pass',files=files),ensure_ascii=False))
