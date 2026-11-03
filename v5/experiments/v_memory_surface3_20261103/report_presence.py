"""Independent HTML full-text preservation checks; no semantic judging."""
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
  for turn in sample['turns']:
   expected.append(turn['delivery']['body'])
   for text in [turn['request']['user_prompt'],turn['request']['decoded_input'],turn['output']['raw_output']]:assert html.escape(text) in page,'Missing actual input/RAW'
   actual_inputs+=1
  for obj in [sample['sample']['revision']['raw_document'],sample['sample']['revision']['sources'],sample['sample']['db_sample'],sample['selection']]:
   assert html.escape(json.dumps(obj,ensure_ascii=False,indent=2)) in page,'Missing full source/projection/selection'
 assert parser.bodies==expected,'HTML bodies changed or missing'
 result=dict(status='pass',samples=len(packet['samples']),all_bodies_exact=len(expected),all_actual_inputs_RAW_present=actual_inputs,all_Memory_operations_present=True,body_sha256=[hashlib.sha256(s.encode()).hexdigest() for s in expected])
 (root/'report_presence_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 return result
