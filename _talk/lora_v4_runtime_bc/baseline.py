"""Frozen old R2 Arm, 2700-character horizon and observational metadata only."""
from bootstrap import *
from policy import recent_measure

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
            generated.update(recent_measure(models.tok,prompt,recent,generated['context_cut_tokens']))
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
            played_chars=min(len(accepted['text']),2700-self.total)
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
        record.update(runtime_factors={'control':False,'history':False,'transition':False},
            recent_input_text=recent,recent_input_chars=len(recent),
            recent_input_tokens=len(models.tok.encode(recent,add_special_tokens=False).ids),
            active_memory_id=plan['memory_id'] if plan and plan['use_memory'] else None,
            played_semantic_vector=self.played[-1]['vector'] if played_chars else None,
            transition=None,last_valid_plan_fallback=False)
        self.log.write(json.dumps(record,ensure_ascii=False)+'\n');self.log.flush()
        self.turn+=1
        if self.total>=2700:self.status='complete'
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
