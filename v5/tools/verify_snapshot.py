"""Read-only source snapshot verification; no model imports or network access."""
import argparse,ast,hashlib,json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--source-talk',type=Path);a=parser.parse_args()
 manifest=json.loads((ROOT/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'));syntax=0;source_checked=0;total=0
 forbidden={'.zip','.sqlite','.sqlite3','.db','.safetensors','.pt','.pth','.bin','.gguf','.onnx','.pem','.key'}
 secret_patterns=[r'ghp_[A-Za-z0-9]{30,}',r'github_pat_[A-Za-z0-9_]{40,}',r'AKIA[0-9A-Z]{16}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
 for x in manifest['files']:
  p=ROOT/x['path'];assert p.resolve().is_relative_to(ROOT.resolve())
  assert p.is_file() and p.stat().st_size==x['bytes'] and sha(p)==x['sha256'],x['path']
  assert p.suffix.lower() not in forbidden and p.name not in {'.env','credentials.json'},x['path']
  text=p.read_text(encoding='utf-8-sig')
  for pattern in secret_patterns:assert not re.search(pattern,text),('credential-like value in',x['path'])
  if p.suffix=='.py':ast.parse(text,filename=x['path']);syntax+=1
  if a.source_talk and x['kind']=='source-byte-preserving':
   s=a.source_talk/x['source_relative_to_talk'];assert sha(s)==x['source_sha256']==x['sha256'],x['path'];source_checked+=1
  total+=x['bytes']
 print(json.dumps(dict(status='pass',version=manifest['version'],files=len(manifest['files']),python_syntax=syntax,bytes=total,original_sources_checked=source_checked,model_calls=0,network=False),ensure_ascii=False))
if __name__=='__main__':main()
