"""CPU-only synthetic escaped/full-text report verification."""
from common import *
from replay_finalize_cpu import render_report,check_html
def main():
 pairs=[];rv=[]
 for i in range(4):
  pid=f'P{i+1:02}';d=dict(pair=dict(pair_id=pid,memory_id='X',case={'facts':['CPUだけの模擬']}))
  for side in ['A','B']:
   body=side+str(i)+'「<&>」\n次。';d[side]=dict(request=dict(user_prompt='入力'+body,decoded_input='復号'+body),output=dict(raw_output=body+'<turn|>'),delivery=dict(body=body))
  pairs.append(d);rv.append(dict(pair_id=pid,quotes_old=[d['A']['delivery']['body']],quotes_new=[d['B']['delivery']['body']],**{k:'CPU synthetic only' for k in ['condition_match','replay_match','oral_style_comparison','fact_preservation','inherited_additions','new_additions']}))
 packet=dict(pairs=pairs);review=dict(per_pair=rv);page,text,bodies=render_report(packet,review,'CPU検査のみ')
 result=check_html(page,bodies,packet);assert all(t in text for t in bodies)
 result.update(check_count=5,model_calls=0,synthetic=True);write(OUT/'report_cpu_test.json',result);print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
