"""Prepare lossless root reading views after the all-call technical audit."""
import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def load(name):return json.loads((R/name).read_text('utf-8-sig'))
def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
def main():
 assert load('technical_audit.json')['status']=='pass'
 packet=load('review_packet.json');assert load('controller.json')['status']=='complete'
 saved=[]
 common=packet['samples'][0]['turns'][0]['request']['user_prompt'].split('【直前の発話】',1)[0]
 assert all(t['request']['user_prompt'].startswith(common) for s in packet['samples'] for t in s['turns'])
 (R/'review_views/common_input_prefix.txt').write_text(common,encoding='utf-8')
 for sample in packet['samples']:
  for t in sample['turns']:
   req,out,row,delivery=(t[k] for k in ('request','output','row','delivery'))
   cid=row['call_id'];prompt=req['user_prompt'];decoded=req['decoded_input'];body=delivery['body'];raw=out['raw_output']
   proof=dict(call_id=cid,sample_id=row['sample_id'],prompt_sha256=digest(prompt),decoded_sha256=digest(decoded),raw_sha256=digest(raw),body_sha256=digest(body))
   text='CALL '+cid+' / '+row['sample_id']+' / unit '+str(row['unit_index'])+'\n'
   assert common+prompt[len(common):]==prompt
   proof['common_prefix_sha256']=digest(common)
   text+='ACTUAL USER PROMPT — FULL RECONSTRUCTION: exact common_input_prefix.txt + suffix below. Final newline is part of suffix.\n'+prompt[len(common):]+'\nEND ACTUAL USER PROMPT SUFFIX\n'
   embedded=prompt.rstrip()
   if embedded and decoded.count(embedded)==1:
    before,after=decoded.split(embedded);assert before+embedded+after==decoded
    proof['decoded_exact_reconstruction']=dict(prefix=before,suffix=after,user_prompt_occurrences=1,removed_exact_trailing_whitespace=prompt[len(embedded):])
    text+='ACTUAL DECODED — EXACT FULL RECONSTRUCTION: prefix '+json.dumps(before,ensure_ascii=False)+' + the full actual prompt above excluding only its exact final newline + suffix '+json.dumps(after,ensure_ascii=False)+'\n'
   else:
    text+='ACTUAL DECODED — FULL\n'+decoded+'\nEND ACTUAL DECODED\n'
   text+='ACTUAL RAW — FULL\n'+raw+'\nEND ACTUAL RAW\n'
   if body and raw.count(body)==1:
    before,after=raw.split(body);assert before+body+after==raw
    proof['body_exact_raw_substring']=dict(prefix=before,suffix=after,body_occurrences=1)
    text+='ACTUAL BODY — the full RAW above with exact prefix '+json.dumps(before,ensure_ascii=False)+' and suffix '+json.dumps(after,ensure_ascii=False)+' removed. No other character changes.\n'
   else:text+='ACTUAL BODY — FULL\n'+body+'\nEND ACTUAL BODY\n'
   history=req['context']['payload']['history'];history_refs=[]
   by={u['row']['call_id']:u for u in sample['turns']}
   for h in history:
    # Keep the exact actual text visible if it cannot be proved to equal a reviewed full body.
    ref=h.get('call_id');prior=by.get(ref);expected=prior['delivery']['body'] if prior else None
    if h.get('text')==expected:history_refs.append(dict(call_id=ref,exact_full_body_equal=True,body_sha256=digest(expected)))
    else:history_refs.append(h)
   proof['history']=history_refs
   text+='ACTUAL HISTORY: '+json.dumps(history_refs,ensure_ascii=False,indent=2)+'\n'
   metadata={k:row[k] for k in ['source_step_indices','operations','eos','delivered','format_reason','semantic_status','attempted_not_semantically_executed']}
   metadata.update(input_tokens=len(out['input_ids']),output_tokens=len(out['output_ids']),model_seconds=out['seconds'],history_calls=[h.get('call_id') for h in history])
   text+='ACTUAL CALL METADATA\n'+json.dumps(metadata,ensure_ascii=False,indent=2)+'\n'
   dest=R/'review_views'/(cid+'_full.txt');dest.write_text(text,encoding='utf-8');proof['view_sha256']=digest(text);proof['view_bytes']=len(text.encode('utf-8'));saved.append(proof)
 (R/'review_views/input_raw_read_proof.json').write_text(json.dumps(dict(review_packet_sha256=hashlib.sha256((R/'review_packet.json').read_bytes()).hexdigest(),deduplication='Only exact character-equal contained strings; all nonduplicate text remains visible. This script does not mark anything root-read.',calls=saved),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(dict(status='prepared_for_root_reading',calls=len(saved),human_labels=0)))
if __name__=='__main__':main()
