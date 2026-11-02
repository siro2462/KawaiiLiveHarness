"""CPU-only synthetic finalizer integration; no source Memory or model call."""
from common import *
from unittest.mock import patch
import tempfile
import finalize_cpu

def main():
 with tempfile.TemporaryDirectory(dir=OUT/'cpu_temp') as tmp:
  q=Path(tmp);samples=[];oldann=[];newann=[];per_turn=[];per_sample=[];oldids=[];newids=[];n=0
  fields=['listener_address','self_question','direct_reaction','emotion_explanation','live_rhythm','unit_length','oral_style','repetition','fact_preservation','epistemic_preservation','operation_following','discourse','naturalness','unsupported_additions']
  for sid,count in [('X1',4),('X2',4),('X3',3)]:
   sides=[]
   for new in [False,True]:
    turns=[]
    for j in range(count):
     cid=f'R{n+j+1:04}';body=('新' if new else '旧')+sid+str(j)+'。「<&>」\n次。'
     row=dict(call_id=cid,sample_id=sid,unit_index=j+1,source_step_indices=[j+1],format_reason=None,delivered=True)
     turns.append(dict(row=row,delivery=dict(body=body),request=dict(user_prompt='入力'+body,decoded_input='復号'+body),output=dict(raw_output=body+'<turn|>',official_stop_reached=True,output_ids=[1,2],seconds=0)))
     ann=dict(call_id=cid,spans=[dict(kind='F',text=body)])
     (newann if new else oldann).append(ann);(newids if new else oldids).append(cid)
     if new:per_turn.append(dict(call_id=cid,sample_id=sid,unit_index=j+1,quotes=[body],**{f:'CPU synthetic only' for f in ['listener_address','self_question','direct_reaction','emotion_explanation','live_rhythm','operation_following','history_use','fact_preservation','epistemic_preservation','repetition','naturalness','unsupported_additions']}))
    sides.append(turns)
   oldtext='\n'.join(t['delivery']['body'] for t in sides[0]);newtext='\n'.join(t['delivery']['body'] for t in sides[1])
   samples.append(dict(sample=dict(id=sid,title='模擬',revision=dict(raw_document={'原文':'CPUだけの模擬資料'})),selection=dict(steps=[],deferred_nodes=[]),baseline=dict(turns=sides[0],full_text=oldtext),turns=sides[1],full_text=newtext))
   per_sample.append(dict(sample_id=sid,quotes_baseline=[sides[0][0]['delivery']['body']],**{f:'CPU synthetic only' for f in fields}));n+=count
  write(q/'review_packet.json',dict(samples=samples));write(q/'technical_audit.json',dict(status='pass'))
  write(q/'root_review.json',dict(review_packet_sha256=sha(q/'review_packet.json'),root_full_text_read=True,human_quality_labels=0,limits=['CPU synthetic only'],reviewed_call_ids=newids,reviewed_baseline_call_ids=oldids,per_turn=per_turn,per_sample=per_sample))
  write(q/'output_annotations.json',dict(samples=newann));write(q/'baseline_annotations.json',dict(samples=oldann));(q/'root_final_summary.md').write_text('CPU合成検査であり意味品質評価ではない。',encoding='utf-8')
  with patch.object(finalize_cpu,'OUT',q),patch.object(finalize_cpu,'verify',lambda:None):finalize_cpu.main()
  report=read(q/'report_presence_check.json');assert report['all22_bodies_exact']
 write(OUT/'report_cpu_test.json',dict(status='pass',checks=5,synthetic22_bodies_exact=True,html_special_characters_and_newlines_exact=True,all_inputs_RAW_present=True,report_completion_created=True,model_calls=0))
 print(json.dumps(dict(status='pass',synthetic_report_checks=5,new_model_calls=0)))
if __name__=='__main__':main()
