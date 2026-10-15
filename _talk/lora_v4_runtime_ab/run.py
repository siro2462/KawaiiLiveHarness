"""Frozen v4 Base/R1/R2, real inference and 30-minute modeled playback."""
import argparse,hashlib,json,os,queue,shutil,sqlite3,subprocess,sys,threading,time,traceback
from pathlib import Path

ROOT=Path(__file__).resolve().parent
V4=ROOT.parent/'lora_v4_planner_talk'
sys.path.insert(0,str(V4))
from common import read,write,sha,now,Lock,MODEL,TALK,RUN,SEED
from contracts import planner_prompt,talk_prompt,fallback_prompt
from runtime import Runtime,obtain_plan,hard_failure
from core import POLICY,compact,detect,ranked_candidate

OUT=ROOT/'runs/runtime_30m_20261007'
FIXTURE=TALK/'memory_talk_lora_abc_v2/evaluation/memory_swap_abc_v2/audit/fixtures.json'
PROFILE=TALK/'models/multilingual-e5-small-onnx/profile.json'
ARMS=['Base','R1','R2']

class Embedder:
    def __init__(self,out):
        self.stderr=(out/'embedding.stderr.log').open('a',encoding='utf8')
        self.proc=subprocess.Popen([read(PROFILE)['python'],'-X','utf8','-B',str(ROOT/'embed_worker.py')],
             stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,text=True,encoding='utf8')
        self.q=queue.Queue();self.cache={}
        def consume():
            for line in self.proc.stdout:self.q.put(line)
            self.q.put(None)
        threading.Thread(target=consume,daemon=True).start()
        self.ready=self.response();assert self.ready['ready'] and self.ready['profile_sha256']==sha(PROFILE)
        self.log=(out/'embeddings.jsonl').open('a',encoding='utf8')
    def response(self):
        line=self.q.get(timeout=180)
        if line is None:raise RuntimeError('CPU embedding worker ended; inspect embedding.stderr.log')
        return json.loads(line)
    def embed(self,kind,texts):
        missing=list(dict.fromkeys(s for s in texts if (kind,s) not in self.cache))
        if missing:
            req={'kind':kind,'texts':missing};self.proc.stdin.write(json.dumps(req,ensure_ascii=False)+'\n');self.proc.stdin.flush()
            response=self.response();vectors=response['vectors']
            assert len(vectors)==len(missing)
            for s,v in zip(missing,vectors):
                assert len(v)==384 and abs(sum(x*x for x in v)-1)<1e-4
                self.cache[(kind,s)]=v
            self.log.write(json.dumps({'request':req,'response':response},ensure_ascii=False)+'\n');self.log.flush()
        return [self.cache[(kind,s)] for s in texts]
    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.write('{"stop":true}\n');self.proc.stdin.flush();self.proc.wait(timeout=30)
        self.log.close();self.stderr.close()

def prepare():
    OUT.mkdir(parents=True,exist_ok=False)
    fixture=read(FIXTURE)
    bank=[{'id':c['case_id'],'body':c['memory']} for c in fixture['cases'] if c['condition'] in ['A','B']]
    initial=next(c['context'] for c in fixture['cases'] if c['case_id']=='S2A')
    identities={str(MODEL/'model.safetensors'):read(V4/'baseline/manifest.json')['identities']['base_sha256']['sha256']}
    for p in [MODEL/'tokenizer.json',FIXTURE,PROFILE,V4/'evaluate.py',V4/'runtime.py',V4/'common.py',V4/'contracts.py']:
        identities[str(p)]=sha(p)
    for kind in ['planner','talk']:
        result=read(RUN/kind/'training_result.json');assert result['status']=='complete'
        for p in Path(result['final_adapter']).iterdir():
            if p.is_file():identities[str(p)]=sha(p)
    for item in read(PROFILE)['files']:
        p=PROFILE.parent/item['local'];assert sha(p)==item['sha256'];identities[str(p)]=item['sha256']
    db=sqlite3.connect(OUT/'memory_bank.sqlite')
    db.execute('CREATE TABLE memories(id TEXT PRIMARY KEY,body TEXT NOT NULL)')
    db.executemany('INSERT INTO memories VALUES(?,?)',[(m['id'],m['body']) for m in bank]);db.commit();db.close()
    identities[str(OUT/'memory_bank.sqlite')]=sha(OUT/'memory_bank.sqlite')
    write(OUT/'protocol.json',{'major_model_version':4,'arms':ARMS,'seed':SEED,'initial':initial,'memory_bank':bank,
        'identities':identities,'runtime_policies':{'Base':'existing v4 Runtime, observe loops without intervention',
        'R1':'reject entire unplayed loop candidate, reset Plan, retrieve highest scored different Memory at original threshold',
        'R2':'same as R1, plus extractive clean played-history view before replanning; first healthy fact mention remains'},
        'detector':POLICY,'retrieval':{'top_k':1,'threshold':.6,'query_tail_chars':1500,
        'embedding_profile':str(PROFILE),'rank_formula':'L2 E5 dot product','on_loop':'exclude current candidate ID only; no threshold relaxation'},
        'generation':read(V4/'baseline/manifest.json')['speech_generation'],
        'timing':{'target_modeled_seconds':1800,'characters_per_second':4.5,'target_played_chars':8100,
                  'max_turns_per_arm':1200,'stop_consecutive_zero_playback':30},
        'seed_schedule':'Talk seed + generation turn + retry*10000, Planner seed + retry, identical across arms',
        'playback':'simulated; no actual audio or 30-minute wall-clock claim',
        'external_events':'none in every arm; prior scheduled synthetic interruption was a separate integrity test',
        'facts':'ten original synthetic fixture memories; spoken claims never promoted to retrieved factual memories',
        'semantic_metrics':'proxy counts plus root reading; no automatic quality pass',
        'compact':'no additional LLM; exact excerpts only; original events unchanged',
        'created':now(),'training':False})
    source=OUT/'executed_code';source.mkdir()
    for p in ROOT.glob('*.py'):shutil.copy2(p,source/p.name)
    write(OUT/'code_hashes.json',{p.name:sha(p) for p in ROOT.glob('*.py')})
    write(OUT/'manifest.json',{'status':'prepared','run':str(OUT),'protocol_sha256':sha(OUT/'protocol.json')})

def verify():
    cfg=read(OUT/'protocol.json')
    for p,digest in cfg['identities'].items():
        if sha(Path(p))!=digest:raise ValueError('Frozen identity changed: '+p)
    for name,digest in read(OUT/'code_hashes.json').items():
        if sha(ROOT/name)!=digest:raise ValueError('Experiment code changed: '+name)
    return cfg

def preflight():
    cfg=verify()
    test=subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','test_core'],cwd=ROOT,capture_output=True,text=True,encoding='utf8')
    if test.returncode:raise RuntimeError(test.stdout+test.stderr)
    embedding=Embedder(OUT)
    try:
        texts=[cfg['initial']]+[m['body'] for m in cfg['memory_bank']]
        req=OUT/'embedding_parity.request.json';res=OUT/'embedding_parity.response.json'
        write(req,{'kind':'query','texts':texts})
        proc=subprocess.run([read(PROFILE)['python'],'-X','utf8','-B',str(TALK/'src/e5-embed.py'),str(req),str(res)],
                            capture_output=True,text=True,encoding='utf8',timeout=180)
        (OUT/'embedding_parity.stderr.log').write_text(proc.stderr,encoding='utf8')
        if proc.returncode:raise RuntimeError('Existing E5 parity exit '+str(proc.returncode))
        expected=read(res);actual=embedding.embed('query',texts)
        error=max(abs(a-b) for x,y in zip(actual,expected['vectors']) for a,b in zip(x,y))
        assert error<=1e-7
        # Initial Base prompt is identical to the previous v4 rollout input.
        saved=read(RUN/'evaluation/rollout/results.json')['records'][0]
        vectors=embedding.embed('passage',[m['body'] for m in cfg['memory_bank']])
        candidate,retrieval=ranked_candidate(cfg['memory_bank'],vectors,actual[0])
        assert candidate==saved['candidate'] and retrieval['top_id']==saved['retrieval']['top_id']
        inp={'recent':cfg['initial']+'\n','current_state':{},'memory_candidates':candidate,'previous_plan':None}
        assert planner_prompt(inp)==saved['planner_attempts'][0]['input_text']
        write(OUT/'cpu_preflight.json',{'status':'pass','GPU_loaded':False,'tests':test.stderr,
             'E5_max_absolute_difference':error,'original_initial_retrieval_and_planner_prompt_equal':True,
             'frozen_identities':len(cfg['identities']),'base_policy_unchanged':True,'finished':now()})
    finally:embedding.close()

class Arm:
    def __init__(self,name,initial):
        self.name=name;self.dir=OUT/name;self.dir.mkdir(exist_ok=False)
        self.rt=Runtime(self.dir/'events.sqlite',initial);self.initial=initial
        self.played=[];self.total=0;self.turn=0;self.zero=0;self.loop_streak=0
        self.first_loop=None;self.collapse=None;self.blocked=None;self.compacted=None;self.context_after_compact=[]
        self.interventions=0;self.status='running';self.log=(self.dir/'io.jsonl').open('w',encoding='utf8')
    def recent(self):
        return self.rt.recent() if self.compacted is None else self.compacted+'\n'+''.join(self.context_after_compact)
    def step(self,models,embed,bank,vectors):
        before=self.total/4.5;retrieval=None;plan_attempts=[];compact_audit=None
        candidate=self.rt.candidates
        if self.rt.needs_plan():
            query_text=self.recent()[-1500:]
            query=embed.embed('query',[query_text])[0]
            candidate,retrieval=ranked_candidate(bank,vectors,query,self.blocked)
            retrieval.update(query_text=query_text,query_vector=query)
            self.blocked=None
            inp={'recent':self.recent(),'current_state':{},'memory_candidates':candidate,'previous_plan':self.rt.plan}
            plan,plan_attempts=obtain_plan(models.plan,inp)
            self.rt.candidates=candidate
            if plan:self.rt.set_plan(plan,candidate)
        recent=self.recent().rstrip('\n');plan=self.rt.plan if self.rt.remaining else None
        prompt=talk_prompt(recent,candidate,plan) if plan else fallback_prompt(recent)
        attempts=[];accepted=None;intervened=False;failure=None;observed_loop=False
        for retry in range(2):
            generated=models.generate('v4',prompt,recent,SEED+self.turn+retry*10000)
            failure=hard_failure(generated['text'])
            vector=embed.embed('passage',[generated['text']])[0]
            loop=detect(generated['text'],vector,self.played,failure)
            generated.update(hard_failure=failure,loop=loop,semantic_vector=vector)
            attempts.append(generated);observed_loop|=loop['loop']
            if loop['loop'] and self.name!='Base':
                intervened=True;self.interventions+=1
                self.blocked=(plan['memory_id'] if plan and plan['use_memory'] else candidate[0]['id'] if candidate else None)
                self.rt.plan=None;self.rt.remaining=0;self.rt.candidates=[]
                if self.name=='R2':
                    excluded={p['turn'] for p in self.played if p['loop']}
                    self.compacted,compact_audit=compact(self.initial,self.played,excluded)
                    self.context_after_compact=[]
                    compact_audit['compact_text']=self.compacted
                    compact_audit['discarded_candidate']=generated['text']
                break
            if failure is None:accepted=generated;break
        if observed_loop:
            if self.first_loop is None:self.first_loop={'turn':self.turn,'modeled_seconds':before}
            self.loop_streak+=1
            if self.collapse is None and (self.loop_streak>=POLICY['collapse_consecutive_candidates']
                                         or any(a['hard_failure']=='repetition' for a in attempts)):
                self.collapse={'turn':self.turn,'modeled_seconds':before,'definition':'three consecutive detected-loop turns or within-output exact collapse'}
        else:self.loop_streak=0
        played_chars=0
        if accepted:
            played_chars=min(len(accepted['text']),8100-self.total)
            self.rt.commit_playback(accepted['text'],played_chars)
            played_text=accepted['text'][:played_chars]
            self.played.append({'turn':self.turn,'text':played_text,'vector':embed.embed('passage',[played_text])[0],
                'loop':accepted['loop']['loop'],'plan':plan,
                'memory_id':plan['memory_id'] if plan and plan['use_memory'] else None})
            if self.compacted is not None:self.context_after_compact.append(played_text)
            self.total+=played_chars;self.zero=0
        else:
            self.zero+=1;self.rt.plan=None;self.rt.remaining=0
        record={'arm':self.name,'turn':self.turn,'seed':SEED+self.turn,'modeled_seconds_before':before,
                'candidate':candidate,'retrieval':retrieval,'plan':plan,'planner_attempts':plan_attempts,
                'speech_attempts':attempts,'accepted_attempt':len(attempts)-1 if accepted else None,
                'played_text':accepted['text'][:played_chars] if accepted else '',
                'played_chars':played_chars,'intervened':intervened,'compact':compact_audit,
                'failure':failure,'recent_after':self.recent(),'authoritative_recent_after':self.rt.recent(),
                'modeled_seconds_after':self.total/4.5}
        self.log.write(json.dumps(record,ensure_ascii=False)+'\n');self.log.flush()
        self.turn+=1
        if self.total>=8100:self.status='complete'
        elif self.zero>=30:self.status='stalled_zero_playback'
        elif self.turn>=1200:self.status='turn_limit_unmet'
        write(self.dir/'state.json',self.state())
        return record
    def state(self):
        return {'arm':self.name,'status':self.status,'turns':self.turn,'played_chars':self.total,
                'modeled_seconds':self.total/4.5,'first_loop':self.first_loop,'collapse':self.collapse,
                'interventions':self.interventions,'consecutive_zero_playback':self.zero,'updated':now(),'pid':os.getpid()}
    def close(self):
        count=self.rt.db.execute("SELECT COUNT(*) FROM events WHERE kind='played_speech'").fetchone()[0]
        assert count==len(self.played)==self.rt.db.execute('SELECT COUNT(*) FROM memory').fetchone()[0]
        for body,eid in self.rt.db.execute('SELECT body,event_id FROM memory'):
            memory=json.loads(body);event=json.loads(self.rt.db.execute('SELECT body FROM events WHERE id=?',(eid,)).fetchone()[0])
            assert memory['played_text']==event['played_text'] and memory['facts_verified'] is False
        assert sum(len(p['text']) for p in self.played)==self.total
        (self.dir/'transcript.md').write_text('# '+self.name+'\n\n'+ '\n\n'.join(p['text'] for p in self.played),encoding='utf8')
        write(self.dir/'result.json',{**self.state(),'G5_integrity':'pass','quality':'root reading pending','actual_audio':False})
        self.log.close();self.rt.close()

def run():
    cfg=verify();assert read(OUT/'cpu_preflight.json')['status']=='pass'
    if read(OUT/'manifest.json')['status']!='prepared':raise ValueError('No automatic rerun of existing experiment')
    from evaluate import Models
    manifest={'status':'running','started':now(),'pid':os.getpid(),'run':str(OUT),
              'protocol_sha256':sha(OUT/'protocol.json'),'training':False,'stage':'loading_frozen_models'}
    write(OUT/'manifest.json',manifest);embedding=None;arms=[];started=time.perf_counter()
    try:
        with Lock(V4/'gpu.lock'),Lock(ROOT/'gpu.lock'):
            models=Models();embedding=Embedder(OUT)
            vectors=embedding.embed('passage',[m['body'] for m in cfg['memory_bank']])
            arms=[Arm(name,cfg['initial']) for name in ARMS]
            manifest['adapter_hashes']=models.hashes
            while any(a.status=='running' for a in arms):
                for a in arms:
                    if a.status!='running':continue
                    record=a.step(models,embedding,cfg['memory_bank'],vectors)
                    # Verify identical initial output as existing v4; no extra GPU calls.
                    if a.turn==1:
                        saved=read(RUN/'evaluation/rollout/results.json')['records'][0]
                        assert record['speech_attempts'][0]['input_ids']==saved['speech_attempts'][0]['input_ids']
                        assert record['speech_attempts'][0]['output_ids']==saved['speech_attempts'][0]['output_ids']
                    manifest.update(stage='rollout',arms=[x.state() for x in arms],updated=now())
                    write(OUT/'manifest.json',manifest)
            for a in arms:a.close()
            embedding.close();embedding=None
            verify()
            manifest.update(status='outputs_ready' if all(a.status=='complete' for a in arms) else 'partial_outputs_ready',
                finished=now(),wall_seconds=time.perf_counter()-started,root_review='pending',
                all_30m_targets_met=all(a.status=='complete' for a in arms),arms=[a.state() for a in arms])
            write(OUT/'manifest.json',manifest)
    except Exception as exc:
        manifest.update(status='failed',finished=now(),error=str(exc),traceback=traceback.format_exc())
        write(OUT/'manifest.json',manifest)
        raise
    finally:
        if embedding:embedding.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','preflight','run']);args=p.parse_args()
    {'prepare':prepare,'preflight':preflight,'run':run}[args.mode]()
