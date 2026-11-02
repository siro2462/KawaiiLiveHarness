"""Local full-text replay comparison; no inference and no text repair."""
from common import *
import html
from html.parser import HTMLParser

def render_report(packet,review,summary):
 esc=html.escape
 def pre(x):return '<pre>'+esc(x if isinstance(x,str) else json.dumps(x,ensure_ascii=False,indent=2))+'</pre>'
 page='<h1>当時v2と同じ入力・条件で再生成</h1><p>A=保存された当時v2の実出力。B=全文prompt/形式/Fact/固定元履歴/Flow/LoRA/seed/384token設定/call順を同じにした新規生成。H06後半へ新前半本文は入れない。</p>'+pre(summary)
 speech=[];expected=[]
 assert len(packet['pairs'])==len(review['per_pair'])==4
 for pair,rv in zip(packet['pairs'],review['per_pair']):
  pid=pair['pair']['pair_id'];assert rv['pair_id']==pid
  for field in ['condition_match','replay_match','oral_style_comparison','fact_preservation','inherited_additions','new_additions']:assert rv[field]
  for side,field in [('A','quotes_old'),('B','quotes_new')]:assert (rv[field] or not pair[side]['delivery']['body']) and all(q and q in pair[side]['delivery']['body'] for q in rv[field])
  page+='<section><h2>'+esc(pid+' '+pair['pair']['memory_id'])+'</h2><div class="grid">'
  parts=[]
  for side,label in [('A','当時v2・保存実出力'),('B','今回・同条件の新規生成')]:
   body=pair[side]['delivery']['body'];expected.append(body)
   page+='<article><h3>'+label+'</h3><div class="speech">'+esc(body)+'</div></article>';parts.append('【'+label+'】\n'+body)
  page+='</div><details><summary>元Fact・固定履歴・操作Flow・全旧新実入力RAW・引用評価</summary>'+pre(pair['pair']['case'])
  for side in ['A','B']:
   req=pair[side]['request'];out=pair[side]['output'];page+='<h3>'+side+'</h3>'+pre(req['user_prompt'])+pre(req['decoded_input'])+pre(out['raw_output'])
  page+=pre(rv)+'</details></section>';speech.append(pid+' '+pair['pair']['memory_id']+'\n'+'\n'.join(parts))
 page='<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>v2同条件再生成比較</title><style>body{font:16px/1.9 system-ui;background:#f4f6fa;color:#203040;max-width:1500px;margin:20px auto;padding:20px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}article{background:white;padding:20px;border:1px solid #cad5e3;border-radius:8px;min-width:0}.speech,pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}section{margin:32px 0}summary{cursor:pointer}@media(max-width:850px){.grid{grid-template-columns:1fr}}</style>'+page+'</html>'
 return page,'\n\n'.join(speech)+'\n',expected

def check_html(page,expected,packet):
 class Reader(HTMLParser):
  def __init__(self):super().__init__(convert_charrefs=True);self.active=False;self.parts=[];self.bodies=[]
  def handle_starttag(self,t,a):
   if t=='div' and dict(a).get('class')=='speech':self.active=True;self.parts=[]
  def handle_data(self,s):
   if self.active:self.parts.append(s)
  def handle_endtag(self,t):
   if t=='div' and self.active:self.bodies.append(''.join(self.parts));self.active=False
 parser=Reader();parser.feed(page);assert parser.bodies==expected and len(expected)==8
 for p in packet['pairs']:
  assert html.escape(json.dumps(p['pair']['case'],ensure_ascii=False,indent=2)) in page
  for side in ['A','B']:
   for text in [p[side]['request']['user_prompt'],p[side]['request']['decoded_input'],p[side]['output']['raw_output']]:assert html.escape(text) in page
 return dict(status='pass',pairs=4,all8_bodies_exact=True,all8_actual_inputs_RAW_present=True,all_cases_present=True)

def main():
 verify();audit=read(OUT/'technical_audit.json');assert audit['status']=='pass' and audit['all4_full_request_dicts_exact']
 packet=read(OUT/'review_packet.json');review=read(OUT/'root_review.json')
 assert review['review_packet_sha256']==sha(OUT/'review_packet.json') and review['root_full_text_read'] and review['human_quality_labels']==0 and review['limits']
 assert review['reviewed_pair_ids']==[p['pair']['pair_id'] for p in packet['pairs']]
 summary=(OUT/'root_final_summary.md').read_text('utf-8-sig');assert summary.strip()
 page,speech,bodies=render_report(packet,review,summary);presence=check_html(page,bodies,packet)
 (OUT/'comparison.html').write_text(page,encoding='utf-8');(OUT/'speech.txt').write_text(speech,encoding='utf-8')
 (OUT/'result.md').write_text(summary,encoding='utf-8')
 (OUT/'full_comparison.txt').write_text(speech+'\n【全入力RAWと評価】\n'+json.dumps(packet,ensure_ascii=False,indent=2)+'\n'+json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
 write(OUT/'report_presence_check.json',presence);write(OUT/'completion.json',dict(status='complete',pairs=4,review_packet_sha256=sha(OUT/'review_packet.json'),root_review_sha256=sha(OUT/'root_review.json'),comparison_sha256=sha(OUT/'comparison.html'),report_check_sha256=sha(OUT/'report_presence_check.json'),human_quality_labels=0,finished_jst=now()))
 print(json.dumps(dict(status='complete',pairs=4,new_calls=4,old_saved_calls=4),ensure_ascii=False))
if __name__=='__main__':main()
