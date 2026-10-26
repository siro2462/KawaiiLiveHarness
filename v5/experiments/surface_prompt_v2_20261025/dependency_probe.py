from common import *
from token_journal import TokenJournal
import token_journal,run_cpu,gpu_worker
checks=[]
def check(n,c):
 checks.append(dict(name=n,passed=bool(c)));assert c,n
class Value:
 def __init__(self,x):self.x=x
 def tolist(self):return self.x
source=Path(read(OUT/'recovery_manifest.json')['dependency_source'])
check('original dependency exact SHA',sha(Path(token_journal.__file__))==sha(source)==read(OUT/'recovery_manifest.json')['dependency_sha256'])
check('dependency resolved within current executed_source',Path(token_journal.__file__).resolve().parent==HERE)
path=OUT/'dependency_probe.tokens.jsonl';j=TokenJournal(path,[7,8],lambda x:str(x),'CPU')
j.put(Value([[7,8]]));check('prompt excluded from output',j.ids==[] and j.prompt_seen)
j.put(Value(list(range(16))));j.put(Value([91,92,93]));j.end();j.close()
logged=rows(path);check('stream and tail intact',sum([x['ids'] for x in logged],[])==list(range(16))+[91,92,93])
check('cumulative count intact',logged[-1]['total_tokens']==19)
try:TokenJournal(path,[7,8],str,'CPU');raised=False
except FileExistsError:raised=True
check('existing journal cannot be overwritten',raised)
q=OUT/'dependency_probe.bad_prompt.jsonl';j=TokenJournal(q,[7,8],str,'CPU')
try:j.put(Value([[7,9]]));raised=False
except AssertionError:raised=True
finally:j.close()
check('mismatched prompt rejected',raised)
check('worker/controller import',callable(run_cpu.main) and callable(gpu_worker.main))
verify();write(OUT/'dependency_probe.json',dict(status='pass',checks=checks,check_count=len(checks),model_calls=0,dependency_sha256=sha(Path(token_journal.__file__))))
print(json.dumps(dict(status='pass',check_count=len(checks),model_calls=0),ensure_ascii=False))
