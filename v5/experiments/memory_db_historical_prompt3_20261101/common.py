import os,sys,json,time,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
HERE=Path(__file__).resolve().parent
OUT=Path(os.environ['ZIP_INCREMENTAL_RUN']).resolve()
BETA=OUT.parents[1];TALK=BETA.parent;MULTI=TALK/'lora_v4_multibase';GEMMA=TALK/'lora_v4_gemma_runtime'
CPU_DEPS=BETA/'experiments/instruct_surface/dependencies'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  while b:=f.read(8*1024*1024):h.update(b)
 return h.hexdigest()
def digest(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def write(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 t=p.with_name(p.name+f'.{os.getpid()}.{time.monotonic_ns()}.tmp')
 t.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 deadline=time.monotonic()+5
 while True:
  try:
   os.replace(t,p)
   return
  except PermissionError as exc:
   if getattr(exc,'winerror',None) not in (5,32,33) or time.monotonic()>=deadline:raise
   time.sleep(.05)
def rows(p):return [json.loads(x) for x in Path(p).read_text(encoding='utf-8').splitlines() if x.strip()] if Path(p).exists() else []
def now():return datetime.now(timezone(timedelta(hours=9))).isoformat()
def obs(pid):
 import psutil
 p=psutil.Process(pid);return dict(pid=pid,created_unix=p.create_time(),command_line=p.cmdline(),executable=p.exe())
def verify():
 c=read(OUT/'protocol.json')
 for p,h in c['frozen_files'].items():
  if sha(p)!=h:raise ValueError('Frozen file changed: '+p)
 return c
def strict_json(s):
 s=s.strip()
 for opening in ('```json\n','```\n'):
  if s.startswith(opening) and s.endswith('\n```'):
   s=s[len(opening):-4]
   break
 def pairs(xs):
  d={}
  for k,v in xs:
   if k in d:raise ValueError('Duplicate JSON key')
   d[k]=v
  return d
 return json.loads(s,object_pairs_hook=pairs)

