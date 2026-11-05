"""Reversible full-text review views. Only token number arrays are CPU-only."""
import copy
import hashlib
import json
import os
import sys
from pathlib import Path

OUT=Path(__file__).resolve().parent.parent
os.environ['ZIP_INCREMENTAL_RUN']=str(OUT)
sys.path.insert(0,str(OUT/'executed_source'))
from compact_surface import decoded_parts,TEMPLATE

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def file_sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(x):return json.dumps(x,ensure_ascii=False,indent=2)


def main():
 packet=read(OUT/'review_packet.json');cfg=read(OUT/'protocol.json')
 assert read(OUT/'technical_audit.json')['review_packet_sha256']==file_sha(OUT/'review_packet.json')
 root=OUT/'root_read';root.mkdir(exist_ok=True)
 aliases={};references={};proof=[];files=[]
 def bind(name,obj):references[name]=copy.deepcopy(obj);return {'$exact_ref':name}
 def alias(name,value):
  assert value not in aliases or aliases[value]==name
  aliases[value]=name
 def encode(obj):
  if isinstance(obj,str):return aliases.get(obj,obj)
  if isinstance(obj,list):return [encode(v) for v in obj]
  if isinstance(obj,dict):return {aliases.get(k,k):encode(v) for k,v in obj.items()}
  return obj
 def restore(obj):
  reverse={v:k for k,v in aliases.items()}
  if isinstance(obj,str):return reverse.get(obj,obj)
  if isinstance(obj,list):return [restore(v) for v in obj]
  if isinstance(obj,dict):
   if set(obj)=={'$exact_ref'}:return copy.deepcopy(references[obj['$exact_ref']])
   if set(obj)=={'$exact_merge'}:
    result={}
    for part in obj['$exact_merge']:
     item=restore(part);assert isinstance(item,dict) and not (set(result)&set(item));result.update(item)
    return result
   return {reverse.get(k,k):restore(v) for k,v in obj.items()}
  return obj
 def section(label,obj):return '\n## '+label+'\n'+(obj if isinstance(obj,str) else dump(encode(obj)))+'\n'
 def save(name,text):
  (root/name).write_text(text,encoding='utf-8');files.append(dict(file=name,chars=len(text),sha256=file_sha(root/name)))
 for s in packet['samples']:
  sample=s['sample'];sid=sample['id'];rev=sample['revision'];db=sample['db_sample']
  alias('@'+sid+'/revision',rev['revision_id']);alias('@'+sid+'/episode',rev['episode_id'])
  alias('@'+sid+'/content_sha',rev['content_sha256'])
  for node in db['nodes']:alias('@'+sid+'/'+node['local_id'],node['id'])
 if packet['samples']:alias('@snapshot',packet['samples'][0]['sample']['db_sample']['provenance']['snapshot_id'])
 header=TEMPLATE.split('【直前の発話】',1)[0]
 common=section('実prompt共通prefix（全12で全字一致）',header)+section('固定条件',cfg['surface'])
 wrappers=[]
 for s in packet['samples']:
  for t in s['turns']:
   req=t['request'];u=req['user_prompt'];d=req['decoded_input'];core=u.strip();assert u.startswith(header) and d.count(core)==1
   before,after=d.split(core);left=u[:len(u)-len(u.lstrip())];right=u[len(u.rstrip()):]
   assert before+core+after==d and left+core+right==u
   wrappers.append((before,after,left,right))
 assert len(set(wrappers))==1
 common+=section('decoded_input = 以下prefix + user_prompt.strip() + 以下suffix。user_prompt自体は共通prefixと各tailで全字復元',dict(prefix=wrappers[0][0],suffix=wrappers[0][1],stripped_leading_whitespace=wrappers[0][2],stripped_trailing_whitespace=wrappers[0][3],note='実Processorのchat templateが末尾改行を除く挙動。原user_promptの改変や入力token切詰ではない'))
 common+=section('IDの可逆別名表（一度だけ表示）',dump({v:k for k,v in aliases.items()}))
 save('00_common.txt',common)
 for s in packet['samples']:
  sample=s['sample'];sid=sample['id'];rev=sample['revision'];db=sample['db_sample'];doc=rev['raw_document']
  rows={r['ID']:r for k in ['出来事','望み・期待','反応','考え・評価','疑問・推測','その後・今後'] for r in doc['記憶'][k]}
  atoms={a['local_id']:a for a in rev['atoms']}
  reduced=copy.deepcopy(sample)
  # The original source and attributes are displayed once, then exact objects referenced.
  text=section('元の創作仕様・由来（全文）',rev['sources'])+section('元Memory全dict（全文）',doc)
  for aid,a in atoms.items():
   assert a['attributes']==rows[aid] and a['evidence']==rows[aid]['創作仕様根拠']
   ar=copy.deepcopy(a);ar['attributes']=bind(sid+'.fragment.'+aid,rows[aid]);ar['evidence']=bind(sid+'.evidence.'+aid,a['evidence'])
   reduced['revision']['atoms'][list(atoms).index(aid)]=ar
   bind(sid+'.atom.'+aid,a)
  reduced['revision']['raw_document']=bind(sid+'.raw_document',doc)
  reduced['revision']['sources']=bind(sid+'.sources',rev['sources'])
  for ni,node in enumerate(reduced['db_sample']['nodes']):
   aid=node['local_id'];original=atoms[aid]
   assert node['raw_atom']==original and node['attributes']==rows[aid] and node['sidecar']['attributes']==rows[aid]
   node['raw_atom']=bind(sid+'.atom.'+aid,original)
   node['attributes']=bind(sid+'.fragment.'+aid,rows[aid]);node['sidecar']['attributes']=bind(sid+'.fragment.'+aid,rows[aid])
   assert node['evidence']==original['evidence'] and node['sidecar']['evidence']==original['evidence']
   node['evidence']=bind(sid+'.evidence.'+aid,original['evidence']);node['sidecar']['evidence']=bind(sid+'.evidence.'+aid,original['evidence'])
   prov=db['provenance'];assert all(node['sidecar'][k]==v for k,v in prov.items())
   extra_side={k:v for k,v in node['sidecar'].items() if k not in prov}
   node['sidecar']={'$exact_merge':[bind(sid+'.projection.provenance',prov),extra_side]}
   inherited={k:v for k,v in original.items() if k!='kind'}
   assert all(db['nodes'][ni][k]==v for k,v in inherited.items())
   extra_node={k:v for k,v in node.items() if k not in inherited}
   reduced['db_sample']['nodes'][ni]={'$exact_merge':[bind(sid+'.atom.'+aid+'.except_kind',inherited),extra_node]}
  for key in ['raw_document','sources']:
   assert db[key]==rev[key];reduced['db_sample'][key]=bind(sid+'.'+key,rev[key])
  # The archived renderer is not the actual full-v2 input. Keep it complete via exact payload/text references.
  reduced['surface']=bind(sid+'.archived_source_renderer',sample['surface'])
  reduced['selection']=bind(sid+'.selection',s['selection']);reduced['steps']=bind(sid+'.steps',s['selection']['steps'])
  assert sample['selection']==s['selection'] and sample['steps']==s['selection']['steps']
  enc=encode(reduced);assert restore(enc)==sample
  text+=section('正規化/全投影・付帯情報（重複objectは上記への完全一致参照）',reduced)
  # Display the archived non-generated source renderer too, without counting it as a real model input.
  archived=sample['surface'];serialized=json.dumps(archived['payload'],ensure_ascii=False,separators=(',',':'))
  assert archived['user_prompt'].endswith(serialized)
  prefix=archived['user_prompt'][:-len(serialized)]
  assert prefix+serialized==archived['user_prompt']
  archive_view={k:v for k,v in archived.items() if k!='user_prompt'}
  archive_view['user_prompt_exact_reconstruction']={'prefix':prefix,'suffix':'json.dumps(payload,ensure_ascii=False,separators=(comma,colon))'}
  text+=section('検査用元renderer（実入力と別）。user_promptはprefix+payloadの可逆compact JSON',archive_view)
  save(sid+'_source.txt',text)
  save(sid+'_selection.txt',section('全CPU操作・候補score/判断trace/保留・条件（全文）',s['selection']))
  for t in s['turns']:
   cid=t['row']['call_id'];req=t['request'];out=t['output'];delivery=t['delivery'];body=delivery['body'];raw=out['raw_output'];u=req['user_prompt'];d=req['decoded_input']
   assert req['messages']==[dict(role='user',content=[dict(type='text',text=u)])]
   assert req['processor_fields']['input_ids'][0]==out['input_ids'] and out['generation_config']==cfg['surface']['generation_config']
   actual_parts=decoded_parts(d);assert actual_parts==req['context']['payload']['model_input_parts']
   context=copy.deepcopy(req['context']);context['payload']['model_input_parts']=bind(cid+'.actual_five_sections',actual_parts)
   index=t['row']['unit_index']-1;start=index*4;end=min(start+4,len(s['selection']['steps']))
   assert context['operations']==t['row']['operations']==s['selection']['steps'][start:end]
   assert context['payload']['operations']==s['sample']['surface']['payload']['operations'][start:end]
   context['operations']=bind(cid+'.source_plan_steps',s['selection']['steps'][start:end])
   context['payload']['operations']=bind(cid+'.source_full_operations',s['sample']['surface']['payload']['operations'][start:end])
   text=section('実prompt固有部分（00_commonのprefixを付けるとuser_prompt全字復元）',u[len(header):])
   if body and raw.count(body)==1:
    left,right=raw.split(body);assert left+body+right==raw
    text+=section('実本文（全文）',body)+section('RAW = 以下prefix + 上記本文 + 以下suffix',dict(prefix=left,suffix=right))
   else:text+=section('RAW全文',raw)+section('実本文全文',body)
   bind(cid+'.body',body);bind(cid+'.raw_output',raw)
   def history_view(history):
    result=copy.deepcopy(history)
    for h in result:
     name=h['call_id']+'.body';assert references[name]==h['text']
     h['text']={'$exact_ref':name}
    return result
   context['payload']['history']=history_view(context['payload']['history'])
   context['before']['history']=history_view(context['before']['history'])
   text+=section('実context/履歴/提示済み参照/範囲（全項目）',context)
   row=copy.deepcopy(t['row']);row['body']={'$exact_ref':cid+'.body'};row['raw_output']={'$exact_ref':cid+'.raw_output'}
   row['operations']={'$exact_ref':cid+'.source_plan_steps'}
   for key in ['before_history','after_history']:row[key]=history_view(row[key])
   assert restore(encode(row))==t['row']
   text+=section('全状態row',row)
   other={k:v for k,v in out.items() if k not in ['input_ids','output_ids','raw_output','generation_config']}
   text+=section('出力条件・資源・EOS・実測秒（token数値配列は技術監査照合）',other)
   delivery_view=copy.deepcopy(delivery)
   assert delivery['parsed']['content']==body
   delivery_view['body']={'$exact_ref':cid+'.body'};delivery_view['raw_output']={'$exact_ref':cid+'.raw_output'};delivery_view['parsed']['content']={'$exact_ref':cid+'.body'}
   assert restore(encode(delivery_view))==delivery
   text+=section('delivery/parse（完全一致の本文重複だけ参照）',delivery_view)
   req_other={k:v for k,v in req.items() if k not in ['user_prompt','decoded_input','messages','processor_fields','context']}
   text+=section('requestの残り全項目',req_other)
   assert restore(encode(context))==req['context']
   save(cid+'.txt',text)
   proof.append(dict(call_id=cid,user_prompt_sha256=digest(u),decoded_input_sha256=digest(d),body_sha256=digest(body),raw_sha256=digest(raw),common_header_exact=True,decoded_wrapper_reconstruction_exact=True,context_reference_expansion_exact=True,source_step_indices=t['row']['source_step_indices'],body_chars=len(body),input_tokens=len(out['input_ids']),output_tokens=len(out['output_ids'])))
 manifest=dict(status='pass',scope='lossless duplicate presentation only; numerical input/output token arrays verified in technical audit; no semantic read claim',review_packet_sha256=file_sha(OUT/'review_packet.json'),files=files,turns=proof,source_object_roundtrip_exact=True)
 (root/'view_manifest.json').write_text(dump(manifest)+'\n',encoding='utf-8')
 print(dump(dict(status='pass',files=[dict(file=f['file'],chars=f['chars']) for f in files],body_chars=sum(t['body_chars'] for t in proof))))


if __name__=='__main__':main()
