"""Lossless line patches against the already-read N01 projection metadata.

Every new specification/Memory is printed in full. Only exactly equal metadata
lines are reused, after the explicitly displayed case-ID alias substitution.
"""
import difflib,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(x):return hashlib.sha256(x.encode('utf-8')).hexdigest()
marker='## 正規化/全投影・付帯情報（重複objectは上記への完全一致参照）'
base=(R/'N01_source.txt').read_text(encoding='utf-8')
baseline_tail=base[base.index(marker):]
manifest=[]
for sid in ['N02','N03']:
 target=(R/(sid+'_source.txt')).read_text(encoding='utf-8')
 point=target.index(marker);head=target[:point];tail=target[point:]
 before=baseline_tail.replace('N01',sid)
 a=before.splitlines(keepends=True);b=tail.splitlines(keepends=True)
 ops=difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes()
 rebuilt=[];patch=[]
 for tag,i,j,k,l in ops:
  if tag=='equal':rebuilt.extend(a[i:j])
  else:
   fresh=''.join(b[k:l]);rebuilt.extend(b[k:l])
   patch.append(dict(action=tag,baseline_lines=[i,j],target_lines=[k,l],new_text=fresh))
 assert ''.join(rebuilt)==tail
 # Replay from the published patch and equal intervals; no unshown new line.
 cursor=0;restored=[]
 for row in patch:
  i,j=row['baseline_lines'];restored.extend(a[cursor:i]);restored.append(row['new_text']);cursor=j
 restored.extend(a[cursor:]);assert ''.join(restored)==tail
 intro=dict(method='exact text patch, not semantic summary',baseline='N01_source.txt after the projection heading',baseline_alias_substitution=['N01',sid],baseline_text_sha256=sha(before),target_full_text_sha256=sha(target),full_Memory_and_specification_are_below=True,projection_target_reconstruction_exact=True,all_new_metadata_lines_shown=True)
 text='## 参照の規則と完全復元proof\n'+json.dumps(intro,ensure_ascii=False,indent=2)+'\n'+head
 text+='\n## 投影/参照メタデータ差分：基準の同じ行は再掲せず、変更行は全文\n'
 for row in patch:
  text+='\n'+json.dumps({k:v for k,v in row.items() if k!='new_text'},ensure_ascii=False)+'\n'+row['new_text']
 file=R/(sid+'_source_delta.txt');file.write_text(text,encoding='utf-8')
 manifest.append(dict(sample_id=sid,file=file.name,chars=len(text),patches=len(patch),target_full_source_chars=len(target),target_text_sha256=sha(target),roundtrip_exact=True))
(R/'source_delta_proof.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False))
