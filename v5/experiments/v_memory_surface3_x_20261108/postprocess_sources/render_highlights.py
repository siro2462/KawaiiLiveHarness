"""Render only reviewed actual output spans; never generates or edits speech."""
import json,html,hashlib
from pathlib import Path
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[1]
def read(name):return json.loads((ROOT/name).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 audit=read('technical_audit.json');assert audit['status']=='pass'
 packet=read('review_packet.json');review=read('root_review.json');annotations=read('output_annotations.json')
 assert review['root_full_text_read'] and review['review_packet_sha256']==sha(ROOT/'review_packet.json')
 ann={x['call_id']:x for x in annotations['samples']};e=html.escape
 css=(Path(__file__).parent/'highlights.css').read_text('utf-8')
 nav=''.join('<a href="#'+e(s['sample']['id'])+'">'+e(s['sample']['id']+' '+s['sample']['title'])+'</a>' for s in packet['samples'])
 title='創作記憶N13〜N15の全文ハイライト'
 page='<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>'+css+'</style></head><body id="top"><main><header><h1>'+title+'</h1><p>新しい架空の記憶3件、全12発話。色は実際に生成された本文の各部分の役割です。</p><div class="legend" aria-label="色の凡例"><span class="F">F 事実・出来事</span><span class="E">E 感情・反応</span><span class="T">T 思考・評価</span><span class="N">N 呼びかけ・つなぎなど</span></div><nav aria-label="話題への移動">'+nav+'</nav><nav><a href="comparison.html">元記憶・CPU列・実発話の全文比較</a><a href="result.md">評価結果</a><a href="speech.txt">発話テキスト</a></nav><p>20代本人の公開投稿を参考に組み直した独立創作です。色は元記憶への忠実さの合否を表しません。</p></header>'
 expected=[];spans_expected=[]
 for sample in packet['samples']:
  sid=sample['sample']['id'];page+='<section id="'+e(sid)+'"><p class="case-id">'+e(sid)+'</p><h2>'+e(sample['sample']['title'])+'</h2>'
  for i,t in enumerate(sample['turns'],1):
   cid=t['row']['call_id'];body=t['delivery']['body'];spans=ann[cid]['spans']
   assert ''.join(s['text'] for s in spans)==body
   assert all(s['kind'] in ('F','E','T','N') and s['text'] for s in spans) or not body
   expected.append((cid,body));spans_expected.append([(s['kind'],s['text']) for s in spans])
   state=' · 形式保留' if not t['row']['delivered'] else ''
   page+='<article class="turn" id="'+e(cid)+'"><h3>発話 '+str(i)+' · '+e(cid)+state+'</h3><div class="speech" data-call="'+e(cid)+'">'+''.join('<span class="'+s['kind']+'">'+e(s['text'])+'</span>' for s in spans)+'</div></article>'
  page+='</section>'
 page+='<footer><a href="#top">先頭へ</a> · <a href="../v_memory_structure_20261108_v1/source_references.json">参考投稿と創作箇所の記録</a></footer></main></body></html>'
 (ROOT/'full_highlights.html').write_text(page,encoding='utf-8')
 # Independent parser verifies initial visibility, sequence, every body and every manual span.
 class Parser(HTMLParser):
  def __init__(self):super().__init__(convert_charrefs=True);self.depth=0;self.details=0;self.current=None;self.bodies=[];self.spans=[];self.span_kind=None;self.span_buf=[]
  def handle_starttag(self,tag,attrs):
   a=dict(attrs)
   if tag=='details':self.details+=1
   if tag=='div':
    if self.depth:self.depth+=1
    elif a.get('class')=='speech':
     assert self.details==0 and 'hidden' not in a and 'display:none' not in a.get('style','').replace(' ','')
     self.depth=1;self.current=(a['data-call'],[]);self.spans.append([])
   if self.depth and tag=='span':assert self.span_kind is None;self.span_kind=a['class'];self.span_buf=[]
  def handle_data(self,data):
   if self.depth:self.current[1].append(data)
   if self.span_kind is not None:self.span_buf.append(data)
  def handle_endtag(self,tag):
   if tag=='span' and self.span_kind is not None:self.spans[-1].append((self.span_kind,''.join(self.span_buf)));self.span_kind=None
   if tag=='div' and self.depth:
    self.depth-=1
    if self.depth==0:self.bodies.append((self.current[0],''.join(self.current[1])))
   if tag=='details':self.details-=1
 parser=Parser();parser.feed(page);assert parser.bodies==expected and parser.spans==spans_expected and len(expected)==12
 result=dict(status='pass',all12_bodies_exact=True,manual_span_sequence_exact=True,all_bodies_visible_initially=True,full_highlights_sha256=sha(ROOT/'full_highlights.html'),review_packet_sha256=sha(ROOT/'review_packet.json'),annotations_sha256=sha(ROOT/'output_annotations.json'))
 (ROOT/'highlight_presence_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
