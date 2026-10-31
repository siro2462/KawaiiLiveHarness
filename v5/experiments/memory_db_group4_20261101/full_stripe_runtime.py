from common import *
import re
sys.path.insert(0,str(OUT/'reference'))
from v5.memory_db.surface import render_surface

def baseline_render(s):
 assert s['initial_history']==[] and s['steps']==s['selection']['steps']
 rendered=render_surface(s['db_sample'],s['selection'])
 assert rendered==s['surface'],'Saved CPU renderer/input changed'
 return rendered['user_prompt'],rendered['payload']

def baseline_prompt(s):
 return baseline_render(s)[0]

def style_block():
 return (OUT/'grouping_style.txt').read_text('utf-8')+(OUT/'reaction_style.txt').read_text('utf-8')+'\n'

def render_sample(s):
 base,payload=baseline_render(s)
 marker='【記憶と操作の入力】\n'
 assert base.count(marker)==1
 prompt=base.replace(marker,style_block()+marker,1)
 assert prompt.replace(style_block(),'')==base
 return prompt,payload

def format_reason(body,eos):
 if not isinstance(body,str) or not body.strip():return 'empty'
 if not eos:return 'incomplete_stop_or_token_cap'
 if len(body)>6000:return 'excessive_length_over6000'
 if re.search(r'<[^>]+>|^\s*[\[{]|【|^\s*#{1,6}\s|\b(?:REPORT|REACT|EXPLORE|REVISIT|REAPPRAISE|SPECULATE|EVIDENCE|GENERALIZE|ASSOCIATE|REENACT)\b|rev_[a-f0-9]+',body):return 'markup_or_operation_leak'
 return None
