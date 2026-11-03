"""Synthetic normal/held/cap report preservation; never uses model output."""
from common import *
import copy,tempfile
from unittest.mock import patch
import finalize_cpu
from stripe_runtime import groups


def main():
 cfg=verify();checks=[]
 for variant in ['normal','held_empty','held_cap']:
  with tempfile.TemporaryDirectory(dir=OUT/'cpu_temp') as temp:
   root=Path(temp);packets=[];review=dict(root_full_text_read=True,human_quality_labels=0,limits=['CPU synthetic report only'],per_turn=[],per_sample=[],reviewed_call_ids=[]);ann=[];n=0
   for sample in read(OUT/'samples.json'):
    turns=[]
    for i,ops in enumerate(groups(sample)):
     n+=1;cid=f'R{n:04}';body='' if variant=='held_empty' else 'CPU模擬本文。';held=variant!='normal'
     row=dict(call_id=cid,sample_id=sample['id'],unit_index=i+1,source_step_indices=list(range(i*4+1,min(i*4+5,len(sample['steps'])+1))),body=body,raw_output='CPU RAW '+variant,eos=variant!='held_cap',delivered=not held,format_reason=variant if held else None)
     turns.append(dict(row=row,delivery=dict(body=body),request=dict(user_prompt='CPU user '+cid,decoded_input='CPU decoded '+cid),output=dict(raw_output=row['raw_output'],official_stop_reached=row['eos'],output_ids=[7,8],seconds=0)))
     review['reviewed_call_ids'].append(cid);review['per_turn'].append(dict(call_id=cid,sample_id=sample['id'],unit_index=i+1,quotes=[body] if body else [],**{f:'CPU synthetic, not a quality claim' for f in finalize_cpu.TURN_FIELDS}))
     ann.append(dict(call_id=cid,spans=[dict(kind='N',text=body)] if body else []))
    packets.append(dict(sample=sample,selection=sample['selection'],turns=turns,full_text='' if held else '\n'.join(t['delivery']['body'] for t in turns)))
    review['per_sample'].append(dict(sample_id=sample['id'],quotes=[body] if body else [],**{f:'CPU synthetic, not a quality claim' for f in finalize_cpu.SAMPLE_FIELDS}))
   write(root/'technical_audit.json',dict(status='pass',synthetic=True));write(root/'protocol.json',cfg);write(root/'review_packet.json',dict(samples=packets));review['review_packet_sha256']=sha(root/'review_packet.json')
   write(root/'root_review.json',review);write(root/'output_annotations.json',dict(samples=ann));(root/'root_final_summary.md').write_text('CPU synthetic report only. No model generation.',encoding='utf-8')
   with patch.object(finalize_cpu,'OUT',root),patch.object(finalize_cpu,'verify',lambda:cfg):finalize_cpu.main()
   result=read(root/'report_presence_check.json');assert result['all_bodies_exact']==cfg['max_calls'] and result['all_actual_inputs_RAW_present']==cfg['max_calls']
   checks.append(dict(variant=variant,status='pass',bodies=cfg['max_calls']))
 write(OUT/'report_cpu_test.json',dict(status='pass',checks=checks,model_calls=0,synthetic_only=True));print(json.dumps(dict(status='pass',variants=len(checks),model_calls=0)))
if __name__=='__main__':main()
