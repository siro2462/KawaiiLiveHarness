"""Independent HTML text-preservation check, not a semantic quality judge."""
from html.parser import HTMLParser
import html,json,hashlib

class SpeechParser(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.depth=0;self.buf=[];self.bodies=[]
 def handle_starttag(self,tag,attrs):
  if tag=='div':
   if self.depth:self.depth+=1
   elif dict(attrs).get('class')=='speech':self.depth=1;self.buf=[]
 def handle_endtag(self,tag):
  if tag=='div' and self.depth:
   self.depth-=1
   if not self.depth:self.bodies.append(''.join(self.buf))
 def handle_data(self,data):
  if self.depth:self.buf.append(data)

def check_report(root):
 def read(p):return json.loads(p.read_text('utf-8-sig'))
 packet=read(root/'review_packet.json');page=(root/'comparison.html').read_text('utf-8')
 parser=SpeechParser();parser.feed(page);expected=[];actual_inputs=0
 for sample in packet['samples']:
  for turn in sample['baseline']['turns']+sample['turns']:
   expected.append(turn['delivery']['body'])
   for text in [turn['request']['user_prompt'],turn['request']['decoded_input'],turn['output']['raw_output']]:
    assert html.escape(text) in page,'Missing actual input/RAW'
   actual_inputs+=1
  assert html.escape(json.dumps(sample['sample']['revision']['raw_document'],ensure_ascii=False,indent=2)) in page
  assert html.escape(json.dumps(sample['selection'],ensure_ascii=False,indent=2)) in page
 assert len(expected)==22 and parser.bodies==expected,'HTML bodies changed or missing'
 result=dict(status='pass',pairs=3,all22_bodies_exact=True,all22_actual_inputs_RAW_present=True,all_Memory_operations_present=True,body_sha256=[hashlib.sha256(s.encode()).hexdigest() for s in expected])
 (root/'report_presence_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 return result
