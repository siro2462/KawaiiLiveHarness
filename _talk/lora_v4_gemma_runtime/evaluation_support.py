"""Evaluation plumbing only. Does not alter admitted Runtime or generation rules."""
import ast
import copy
import hashlib
import json
import queue
import subprocess
import threading
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TALK=ROOT.parent


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def embedder_type():
    path=TALK/'lora_v4_runtime_ab/run.py'
    tree=ast.parse(path.read_text(encoding='utf8'))
    body=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Embedder']
    assert len(body)==1
    ns={'Path':Path,'json':json,'queue':queue,'threading':threading,'subprocess':subprocess,
        'read':read,'sha':sha,'ROOT':path.parent,'PROFILE':TALK/'models/multilingual-e5-small-onnx/profile.json'}
    exec(compile(ast.Module(body=body,type_ignores=[]),str(path),'exec'),ns)
    return ns['Embedder']


class LoggedModels:
    def __init__(self,models,out,writer):
        self.models=models;self.out=Path(out);self.write=writer;self.stage='initial';self.case=None
        self.calls=0;self.counts={'planner':0,'talk':0};self.tok=models.tok;self.hashes=models.hashes
        self.stream=(self.out/'all_calls.jsonl').open('x',encoding='utf8')

    def call(self,role,prompt,recent,invoke):
        self.calls+=1;self.counts[role]+=1
        metadata={'call_id':self.calls,'role':role,'stage':self.stage,'case':self.case,
                  'started_unix':time.time(),'input_text':prompt,'recent':recent}
        self.write(self.out/'active_call.json',{**metadata,'status':'running','counts':self.counts})
        try:record=copy.deepcopy(invoke())
        except Exception as exc:
            from generation_errors import audit_error
            record={'text':None,'generation_error':audit_error(exc,prompt,recent)}
            row={**metadata,**record,'finished_unix':time.time(),'status':'failed'}
            self.stream.write(json.dumps(row,ensure_ascii=False)+'\n');self.stream.flush()
            self.write(self.out/'active_call.json',row)
            raise
        record['actual_generation_call_id']=self.calls
        assert self.tok.decode(record['input_ids'],skip_special_tokens=False)==record['decoded_input']
        assert self.tok.decode(record['output_ids'],skip_special_tokens=True)==record['text']
        assert len(record['input_ids'])==record['input_tokens'] and len(record['output_ids'])==record['output_tokens']
        if not record.get('context_cut_tokens'):
            assert self.tok.encode(prompt,add_special_tokens=False).ids==record['input_ids']
        record['token_input_output_integrity']='pass'
        row={**metadata,**record,'finished_unix':time.time(),'status':'complete'}
        self.stream.write(json.dumps(row,ensure_ascii=False)+'\n');self.stream.flush()
        self.write(self.out/'active_call.json',{k:v for k,v in row.items() if k not in {'input_ids','output_ids','constraint'}})
        print(json.dumps({'event':'generation_complete','call_id':self.calls,'role':role,'stage':self.stage,
                          'case':self.case,'tokens':record.get('output_tokens'),'seconds':record.get('seconds')},ensure_ascii=False),flush=True)
        return record

    def planner(self,prompt,recent,ids,retry=0):
        return self.call('planner',prompt,recent,lambda:self.models.planner(prompt,recent,ids,retry))

    def talk(self,context,seed,retry_note=''):
        return self.call('talk',retry_note+context['prompt'],context['recent'],lambda:self.models.talk(context,seed,retry_note))

    def close(self):self.stream.close()
