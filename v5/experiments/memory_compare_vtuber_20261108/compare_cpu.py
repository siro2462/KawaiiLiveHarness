"""Compare saved speech only. Standard library; no model, network or source mutation."""
import argparse,json,hashlib,statistics,html
from pathlib import Path
from html.parser import HTMLParser
def read(p):return json.loads(p.read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def lcs(x,y):
 row=[0]*(len(y)+1);best=end=0
 for i,c in enumerate(x,1):
  nxt=[0]*(len(y)+1)
  for j,d in enumerate(y,1):
   if c==d:
    nxt[j]=row[j-1]+1
    if nxt[j]>best:best=nxt[j];end=i
  row=nxt
 return x[end-best:end]
def main(root):
 inp=read(root/'comparison_inputs.json');f=read(root/'findings.json');groups=[];protected={}
 for g in inp['groups']:
  base=Path(g['run'])
  for n in ['review_packet.json','output_annotations.json','protocol.json']:protected[str(base/n)]=sha(base/n)
  packet=read(base/'review_packet.json');ann={x['call_id']:x for x in read(base/'output_annotations.json')['samples']};cfg=read(base/'protocol.json');topic=[];pairs=[];calls=[]
  for s in packet['samples']:
   sid=s['sample']['id'];text='\n'.join(t['delivery']['body'] for t in s['turns']);terms=g['named_place_brand_terms'][sid]
   assert all(n in text for n in terms)
   for t in s['turns']:
    body=t['delivery']['body'];a=ann[t['row']['call_id']];assert ''.join(x['text'] for x in a['spans'])==body
    calls.append(dict(sample_id=sid,call_id=t['row']['call_id'],chars=sum(not c.isspace() for c in body),tokens=len(t['output']['output_ids'])))
   for i,t in enumerate(s['turns']):
    for u in s['turns'][i+1:]:
     x=lcs(t['delivery']['body'],u['delivery']['body']);pairs.append(dict(sample_id=sid,left=t['row']['call_id'],right=u['row']['call_id'],length=len(x),text=x))
   cats=s['sample']['revision']['raw_document']['記憶'];topic.append(dict(sample_id=sid,named_place_or_brand=bool(terms),named_terms=terms,source_fragment_counts={k:len(cats[k]) for k in ['出来事','望み・期待','反応','考え・評価','疑問・推測','その後・今後']}))
  groups.append(dict(id=g['id'],label=g['label'],base=base,packet=packet,ann=ann,cfg=cfg,topics=topic,calls=calls,pairs=pairs,summary=dict(topics=len(topic),calls=len(calls),nonwhitespace_chars=sum(c['chars'] for c in calls),output_tokens=sum(c['tokens'] for c in calls),mean_chars=statistics.mean(c['chars'] for c in calls),median_chars=statistics.median(c['chars'] for c in calls),named_place_brand_topics=sum(x['named_place_or_brand'] for x in topic),within_topic_pairs=len(pairs),pairs_with_exact_shared20plus=sum(x['length']>=20 for x in pairs),max_exact_shared_chars=max(x['length'] for x in pairs),opening_hear_me_topics=sum('聞いてよ' in s['turns'][0]['delivery']['body'][:40] for s in packet['samples']))))
 old,new=groups;parity=dict(same_model_adapter_complete_generation_config=old['cfg']['surface']==new['cfg']['surface'],same_seed=old['cfg']['surface_seed']==new['cfg']['surface_seed'],same_history_rule=old['cfg']['history_mode']==new['cfg']['history_mode'],same_call_budget=len(old['calls'])==len(new['calls'])==12)
 assert all(parity.values())
 refs=read(Path(inp['reference_source_json']));protected[inp['reference_source_json']]=sha(Path(inp['reference_source_json']));protected[inp['reference_original_yaml']]=sha(Path(inp['reference_original_yaml']))
 assert all(protected[inp['reference_original_yaml']]==s['provenance']['source_sha256'] for s in refs)
 metrics=dict(status='pass',groups={g['id']:dict(summary=g['summary'],topics=g['topics'],pairs=g['pairs'],calls=g['calls']) for g in groups},parity=parity,definitions=dict(chars='Actual body Unicode characters excluding whitespace.',exact_repetition='Longest contiguous exact common substring for each different call pair within the same topic, including whitespace; threshold20. Not a semantic repetition score.',named_places_brands=inp['named_entity_method']),reference_scope=dict(topics=len(refs),unique_speakers=len({s['provenance']['speaker'] for s in refs}),editorial_not_raw_audio=all(s['provenance']['editorial_source_not_raw_audio'] for s in refs)),new_model_calls=0,human_quality_ratings=0)
 (root/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 e=html.escape;page='<h1>前回3件・今回3件・VTuber発話の比較</h1><p class="lead">'+e(f['conclusion'])+'</p><p>同じ生成設定で異なる題材を比較。音声の評価や同題材A/Bではありません。</p><table><tr><th>観点</th><th>前回</th><th>今回</th><th>判断</th></tr>'
 for r in f['overview']:page+='<tr>'+''.join('<td>'+e(r[k])+'</td>' for k in ['aspect','previous','current','judgment'])+'</tr>'
 page+='</table><h2>定義した数値</h2><table><tr><th>項目</th><th>前回</th><th>今回</th></tr>'
 for label,k in [('全発話数','calls'),('非空白文字','nonwhitespace_chars'),('一発話の平均文字数','mean_chars'),('地名・施設・ブランドが出る話題数','named_place_brand_topics'),('20字以上の逐語一致がある組','pairs_with_exact_shared20plus'),('比較した同話題の発話ペア','within_topic_pairs')]:page+='<tr><td>'+e(label)+'</td>'+''.join('<td>'+str(g['summary'][k])+'</td>' for g in groups)+'</tr>'
 page+='</table><p>名前の出現は手動照合。文字一致は同一話題の異なるcall間で測定し、内容反復や自然さの点数にはしていません。</p><h2>保存VTuber原文5話題との比較</h2>'
 for v in f['vtuber_comparison']:
  page+='<article><h3>'+e(v['id']+' '+v['title'])+'</h3><p>'+e(v['observation'])+'</p><p>'+e(v['contrast'])+'</p>'
  if v['short_quote']:page+='<blockquote>'+e(v['short_quote'])+'</blockquote>'
  page+='</article>'
 page+='<h2>6件の具体的な所見</h2>'
 for c in f['cases']:page+='<article><h3>'+e(c['id'])+'</h3><p>'+e(c['strength'])+'</p><p>'+e(c['limit'])+'</p><p>'+e(' ／ '.join(c['quotes']))+'</p></article>'
 page+='<h2>全24発話の全文ハイライト</h2><p>既存の実本文由来F/E/T/N注釈を、その本文との完全一致を検査して使用。色は役割の分類で、忠実さの合格色ではありません。左右の話題は同題材の対応ではありません。</p><div class="grid">';expected=[]
 for g in groups:
  page+='<div><h3>'+e(g['label'])+'</h3>'
  for s in g['packet']['samples']:
   page+='<section><h3>'+e(s['sample']['id']+' '+s['sample']['title'])+'</h3>'
   for t in s['turns']:
    cid=t['row']['call_id'];body=t['delivery']['body'];expected.append((g['id'],cid,body));page+='<p class="meta">'+e(cid)+'</p><div class="speech" data-group="'+e(g['id'])+'" data-call="'+e(cid)+'">'+''.join('<span class="'+e(x['kind'])+'">'+e(x['text'])+'</span>' for x in g['ann'][cid]['spans'])+'</div>'
   page+='</section>'
  page+='</div>'
 page+='</div><h2>比較の限界</h2><ul>'+''.join('<li>'+e(s)+'</li>' for s in f['limits'])+'</ul>'
 css='body{font:16px/1.85 system-ui,Meiryo,sans-serif;background:#f4f6fa;color:#203040;max-width:1400px;margin:auto;padding:24px}h1{font-size:28px}table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #cbd5e1;padding:12px;text-align:left;vertical-align:top}th{background:#e7eef7}article,section{background:white;border:1px solid #cbd5e1;border-radius:10px;padding:18px;margin:16px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.speech{white-space:pre-wrap;overflow-wrap:anywhere;margin-bottom:24px;line-height:2.1}.F{background:#cde7ff}.E{background:#ffeaac}.T{background:#d6eebd}.meta{font-size:13px;color:#526579}.lead{font-weight:650}.speech span{box-decoration-break:clone;-webkit-box-decoration-break:clone}@media(max-width:900px){.grid{grid-template-columns:1fr}table{font-size:14px}}'
 page='<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>前回・今回・VTuber比較</title><style>'+css+'</style><body>'+page+'</body></html>'
 (root/'comparison.html').write_text(page,encoding='utf-8')
 class Parser(HTMLParser):
  def __init__(self):super().__init__(convert_charrefs=True);self.depth=0;self.out=[]
  def handle_starttag(self,tag,attrs):
   a=dict(attrs)
   if tag=='div':
    if self.depth:self.depth+=1
    elif a.get('class')=='speech':self.depth=1;self.group=a['data-group'];self.cid=a['data-call'];self.buf=[]
  def handle_data(self,d):
   if self.depth:self.buf.append(d)
  def handle_endtag(self,tag):
   if tag=='div' and self.depth:
    self.depth-=1
    if not self.depth:self.out.append((self.group,self.cid,''.join(self.buf)))
 p=Parser();p.feed(page);assert p.out==expected and len(expected)==24
 assert all(sha(Path(p))==h for p,h in protected.items())
 audit=dict(status='pass',all24_bodies_exact=True,source_files_unchanged=True,source_sha256=protected,comparison_sha256=sha(root/'comparison.html'),metrics_sha256=sha(root/'metrics.json'),reference_originals_root_read=5,new_model_calls=0)
 (root/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(dict(status='pass',metrics={g['id']:g['summary'] for g in groups},reference_scope=metrics['reference_scope'],all24_bodies_exact=True),ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);main(p.parse_args().run)
