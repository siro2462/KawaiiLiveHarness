import json,statistics,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1]
p=json.loads((R/'review_packet.json').read_text('utf-8-sig'))
a=json.loads((R/'technical_audit.json').read_text('utf-8-sig'));assert a['status']=='pass'
def lcs(x,y):
 row=[0]*(len(y)+1);best=0;end=0
 for i,c in enumerate(x,1):
  nxt=[0]*(len(y)+1)
  for j,d in enumerate(y,1):
   if c==d:
    nxt[j]=row[j-1]+1
    if nxt[j]>best:best=nxt[j];end=i
  row=nxt
 return x[end-best:end]
turns=[];samples=[]
for s in p['samples']:
 local=[];pairs=[]
 for t in s['turns']:
  r=dict(call_id=t['row']['call_id'],sample_id=s['sample']['id'],body_chars_non_whitespace=sum(not c.isspace() for c in t['delivery']['body']),input_tokens=len(t['output']['input_ids']),output_tokens=len(t['output']['output_ids']),model_seconds=t['output']['seconds'],eos=t['output']['official_stop_reached'],delivered=t['row']['delivered'])
  evidence=next(x for x in a['entries'] if x['call_id']==r['call_id']);assert evidence['input_tokens']==r['input_tokens'] and evidence['output_tokens']==r['output_tokens'];turns.append(r);local.append(r)
 for i,t in enumerate(s['turns']):
  for u in s['turns'][i+1:]:
   shared=lcs(t['delivery']['body'],u['delivery']['body']);pairs.append(dict(left=t['row']['call_id'],right=u['row']['call_id'],longest_exact_shared_chars=len(shared),text=shared))
 samples.append(dict(sample_id=s['sample']['id'],calls=len(local),body_chars_non_whitespace=sum(x['body_chars_non_whitespace'] for x in local),output_tokens=sum(x['output_tokens'] for x in local),model_seconds=round(sum(x['model_seconds'] for x in local),3),max_exact_shared_chars=max(x['longest_exact_shared_chars'] for x in pairs),pairs_ge20=sum(x['longest_exact_shared_chars']>=20 for x in pairs),pair_count=len(pairs),exact_pairs=pairs))
result=dict(status='pass',definitions=dict(body_chars='Unicode characters excluding whitespace, actual body only',tokens='CPU lengths of actual token arrays, equal to technical audit entries',repetition='Per same-sample call pair, longest character-exact contiguous common substring including whitespace; not a semantic repetition score',model_seconds='sum of recorded generation-only seconds; not speech or wall-clock duration'),totals=dict(calls=len(turns),eos=sum(x['eos'] for x in turns),delivered=sum(x['delivered'] for x in turns),body_chars_non_whitespace=sum(x['body_chars_non_whitespace'] for x in turns),output_tokens=sum(x['output_tokens'] for x in turns),model_seconds=round(sum(x['model_seconds'] for x in turns),3),body_chars_range=[min(x['body_chars_non_whitespace'] for x in turns),max(x['body_chars_non_whitespace'] for x in turns)],body_chars_median=statistics.median(x['body_chars_non_whitespace'] for x in turns)),turns=turns,samples=samples,operation_execution_rate=None,human_ratings=0,real_tts=0)
(R/'numeric_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status='pass',totals=result['totals'],samples=[{k:v for k,v in s.items() if k!='exact_pairs'} for s in samples]),ensure_ascii=False))
