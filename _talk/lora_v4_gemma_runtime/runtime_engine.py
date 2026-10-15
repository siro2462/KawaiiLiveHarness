"""v5 extension of the frozen Event Store/retrieval/detector Runtime primitives."""
import copy
import json
from pathlib import Path
from context_runtime import MemoryStore, GroundedPlanStore, recent_view, planner_input, speech_context, original, shrink_recent_context
from runtime_state import PlanStore
from planner_policy import obtain_plan, parse_plan
from fact_gate import check_text, check_plan, VERSION
from original_runtime import Runtime, hard_failure, detect, compact, ranked_candidate, normal, POLICY
from generation_errors import audit_error, classify

SEED=20260925
ARMS={'CONTEXT':{'planner':True,'facts':False},'GOLD':{'planner':False,'facts':True},
      'GUARDED':{'planner':True,'facts':True},'PLANLESS':{'planner':False,'facts':True}}
SHORT_FILLER={'え','えっ','あれ','ん','うん','ああ','あー','おー','へえ','へー','そう','まあ','うそ','まじ','やば','ほんと'}


class Arm:
    def __init__(self, name, directory, initial, bank, writer, fixed_id=None, gold=None, target=2700):
        if name not in ARMS:raise ValueError('Unknown v5 condition')
        self.name=name;self.dir=Path(directory);self.dir.mkdir(parents=True,exist_ok=False)
        self.initial=initial;self.writer=writer;self.fixed_id=fixed_id;self.gold=copy.deepcopy(gold)
        self.target=target;self.turn=0;self.total=0;self.zero=0;self.status='running';self.played=[]
        self.rt=Runtime(self.dir/'events.sqlite',initial)
        self.factors=ARMS[name];self.memory=MemoryStore(bank)
        self.store=GroundedPlanStore() if self.factors['facts'] else PlanStore()
        self.blocked=None;self.refresh_reason='initial';self.compacted=None;self.after_compact=[]
        self.interventions=0;self.loop_streak=0;self.first_loop=None;self.collapse=None
        self.log=(self.dir/'io.jsonl').open('w',encoding='utf8');self.records=[]
        self.plan_history=[]

    def retrieval_recent(self):
        return self.rt.recent() if self.compacted is None else self.compacted+'\n'+''.join(self.after_compact)

    def usable(self, memory):
        bundle=self.store.active
        if bundle is None or self.turn>=bundle['expires_before_turn']:return None
        from runtime_state import memory_reference
        return copy.deepcopy(bundle) if bundle['grounding']==memory_reference(memory) else None

    def state(self):
        return {'arm':self.name,'status':self.status,'turns':self.turn,'played_chars':self.total,
                'target_chars':self.target,'modeled_seconds':self.total/4.5,'consecutive_zero_playback':self.zero,
                'active_original_memory_id':self.memory.current['id'] if self.memory.current else None,
                'memory_selection_state':'selected' if self.memory.current else 'none',
                'available_memory_count':len(self.memory.bank),
                'active_plan_expires_before_turn':self.store.active['expires_before_turn'] if self.store.active else None,
                'first_loop':self.first_loop,'collapse':self.collapse,'interventions':self.interventions,
                'quality':'not automatically passed'}

    def step(self, models, embed, bank, vectors):
        if self.status!='running':raise ValueError('Runtime is not running; do not automatically resume failed generation')
        try:
            return self._step(models,embed,bank,vectors)
        except Exception as exc:
            self.status='failed_implementation'
            error={'arm':self.name,'turn':self.turn,'fatal_error':audit_error(exc),
                   'planner_attempts':getattr(exc,'v5_generation_attempts',[]),
                   'speech_attempts':getattr(exc,'v5_speech_attempts',[])}
            self.log.write(json.dumps(error,ensure_ascii=False)+'\n');self.log.flush()
            self.writer(self.dir/'state.json',self.state())
            raise

    def _step(self, models, embed, bank, vectors):
        before=self.state();memory_before=copy.deepcopy(self.memory.current)
        recent=recent_view(self.initial,self.played).rstrip('\n')
        canonical=original(self.memory.current);bundle=self.usable(canonical)
        plan=copy.deepcopy(bundle['plan']) if bundle else None
        candidate=[];retrieval=None;plans=[];fallback=False;commit_check=None;pending=None;generation_halt=None
        if bundle is None or self.refresh_reason:
            if self.fixed_id:
                candidate=[copy.deepcopy(self.memory.bank[self.fixed_id])]
                retrieval={'method':'fixed diagnostic Memory','top_id':self.fixed_id,'excluded_id':None}
            else:
                query=self.retrieval_recent()[-1500:]
                candidate,retrieval=ranked_candidate(bank,vectors,embed.embed('query',[query])[0],self.blocked)
                retrieval.update(query_text=query)
            self.blocked=None
            canonical=self.memory.preview(candidate)
            from runtime_state import memory_reference
            if memory_reference(canonical)!=memory_reference(original(self.memory.current)):
                self.store.invalidate('grounding_changed_or_no_candidate')
            refs=self.memory.references(canonical)
            previous=copy.deepcopy(bundle['plan']) if bundle and not self.refresh_reason else None
            inp=planner_input(recent,candidate,previous,canonical,self.refresh_reason or 'expired')
            proposed=None
            if self.factors['planner']:
                ids=[m['id'] for m in candidate]
                def generate(prompt, recent, retry):return models.planner(prompt,recent,ids,retry)
                def validate(proposed, data):
                    return check_plan(proposed,refs)
                proposed,plans=obtain_plan(generate,inp,validate if self.factors['facts'] else None)
                generation_halt=next((a['generation_error'] for a in plans if a.get('generation_error',{}).get('action')=='halt_no_further_generation'),None)
                if proposed:
                    commit_check=plans[-1]['factual_validation']
            elif self.name=='GOLD':
                if not self.gold:raise ValueError('Gold diagnostic requires an original fixture Plan')
                proposed=copy.deepcopy(self.gold)
                commit_check=check_plan(proposed,[canonical] if canonical else [])
                if not commit_check['accepted']:raise ValueError('Admitted Gold Plan rejected')
            if proposed:
                if not self.factors['facts']:
                    commit_check={'accepted':True,'status':'not_checked','scope':'Context-only ablation; no factual acceptance claim'}
                self.store.stage(proposed,canonical,self.turn,commit_check)
                pending=copy.deepcopy(self.store.pending);bundle=self.store.commit()
                self.memory.commit(canonical);plan=copy.deepcopy(bundle['plan'])
                identity={'memory_id':canonical['id'] if canonical else None,'topic':plan['topic'],'flow':plan['flow']}
                self.plan_history.append({**identity,'created_turn':self.turn,'played':[],
                    'same_as_recent_plan':any(all(h[k]==identity[k] for k in identity) for h in self.plan_history[-5:]),
                    'semantic_progress_verdict':'unreviewed; observation only'})
                self.plan_history=self.plan_history[-5:]
            else:
                if self.name!='PLANLESS':
                    bundle=self.store.fallback(self.turn,canonical);fallback=bundle is not None
                else:bundle=None
                if bundle:
                    plan=copy.deepcopy(bundle['plan']);canonical=original(bundle['grounding'])
                else:plan=None
                # Only a currently selected source survives a missing/false
                # Plan. A search miss clears selection, never the original DB.
                self.memory.commit(canonical)
            self.refresh_reason=None
        canonical=original(self.memory.current)
        refs=self.memory.references()
        if plan:
            candidates=[canonical] if canonical else []
            remaining=max(1,bundle['expires_before_turn']-self.turn)
            self.rt.set_plan(plan,candidates,remaining)
        else:
            self.rt.plan=None;self.rt.candidates=[canonical] if canonical else [];self.rt.remaining=0
        context=speech_context(self.initial,self.played,canonical,plan)
        expected_sources=[context['grounding']] if context['grounding'] else []
        if self.factors['facts'] and plan and bundle['fact_check']['source_references']!=expected_sources:
            raise ValueError('Plan validation and actual Talk grounding differ')
        attempts=[];accepted=None;failure=None;looped=False;compact_audit=None
        retry_note=''
        for retry in range(0 if generation_halt else 2):
            try:
                rec=models.talk(context,SEED+self.turn+retry*10000,retry_note)
            except Exception as exc:
                error=audit_error(exc,retry_note+context['prompt'],context['recent'],[r['id'] for r in refs])
                attempts.append({'text':None,'attempt':retry,'generation_error':error,'playback_committed':False})
                if classify(exc) is None:
                    exc.v5_speech_attempts=copy.deepcopy(attempts)
                    raise
                failure=error['code']
                if not error['retry'] or retry==1:
                    generation_halt=error
                    break
                if error['action']=='shrink_recent_only':context=shrink_recent_context(context)
                continue
            reason=hard_failure(rec['text'])
            filler=normal(rec['text']) in SHORT_FILLER
            if reason=='too_short' and filler:reason=None
            vector=embed.embed('passage',[rec['text']])[0]
            repetition=detect(rec['text'],vector,self.played,reason)
            if filler and len(self.played)>=2 and all(p.get('short_filler') for p in self.played[-2:]):
                repetition['loop']=True
                repetition['evidence'].append({'kind':'three_short_filler_turns_without_content_progress',
                                              'matched_turn':self.played[-2]['turn']})
            fact_check=check_text(rec['text'],refs)
            rec.update(hard_failure=reason,loop=repetition,memory_consistency=fact_check,
                       fact_gate_applied=self.factors['facts'],semantic_vector=vector,short_filler=filler,
                       attempt=retry,playback_committed=False,plan_used=copy.deepcopy(plan),
                       factual_source_bindings=copy.deepcopy(expected_sources))
            if fact_check['source_references']!=expected_sources:
                raise ValueError('Talk validator and actual Talk input grounding differ')
            attempts.append(rec)
            if repetition['loop']:
                looped=True;self.interventions+=1
                self.blocked=canonical['id'] if canonical else None
                self.store.invalidate('repetition');self.rt.plan=None;self.rt.remaining=0
                self.refresh_reason='repetition';failure='repetition'
                self.compacted,compact_audit=compact(self.initial,self.played,set())
                self.after_compact=[];compact_audit['LLM_exposed']=False
                break
            if reason:
                failure=reason
                retry_note='【発話形式】\n説明や見出しではなく、雑談の発話だけを続ける。\n\n'
                continue
            if self.factors['facts'] and not fact_check['accepted']:
                failure='memory_consistency'
                self.store.invalidate('talk_fact_rejected');self.rt.plan=None;self.rt.remaining=0
                self.refresh_reason='talk_fact_rejected';plan=None;bundle=None
                context=speech_context(self.initial,self.played,canonical,None)
                retry_note='【出来事の扱い】\n'+fact_check['feedback']+'\n\n'
                continue
            accepted=rec;failure=None;break
        if looped:
            self.loop_streak+=1
            if self.first_loop is None:self.first_loop={'turn':self.turn,'modeled_seconds':self.total/4.5}
            if self.collapse is None and (self.loop_streak>=POLICY['collapse_consecutive_candidates'] or
                                         any(a.get('hard_failure')=='repetition' for a in attempts)):
                self.collapse={'turn':self.turn,'definition':'original candidate-collapse criterion'}
        else:self.loop_streak=0
        played_text='';played_chars=0
        if accepted:
            played_chars=min(len(accepted['text']),self.target-self.total)
            played_text=accepted['text'][:played_chars]
            event_id=self.rt.commit_playback(accepted['text'],played_chars)
            accepted['playback_committed']=True
            accepted['played_event_id']=event_id
            self.played.append({'turn':self.turn,'text':played_text,'vector':embed.embed('passage',[played_text])[0],
                                'plan':copy.deepcopy(plan),'memory_id':canonical['id'] if canonical else None,
                                'short_filler':accepted['short_filler'],'loop':False})
            self.total+=played_chars;self.zero=0
            if plan and self.plan_history:self.plan_history[-1]['played'].append({'turn':self.turn,'text':played_text})
            if self.compacted is not None:self.after_compact.append(played_text)
            if played_chars<len(accepted['text']):self.store.invalidate('partial_playback')
        else:
            self.zero+=1
            if not looped:
                self.refresh_reason='speech_rejected'
                self.store.invalidate('speech_rejected:'+str(failure or 'planner_generation_failure'))
                self.rt.plan=None;self.rt.remaining=0
        record={'arm':self.name,'turn':self.turn,'seed':SEED+self.turn,'candidate':candidate,'retrieval':retrieval,
                'planner_attempts':plans,'plan':copy.deepcopy(plan),'pending_bundle':pending,
                'active_bundle_after':copy.deepcopy(self.store.active),'last_valid_fallback':fallback,
                'original_memory_before':memory_before,'original_memory_after':copy.deepcopy(self.memory.current),
                'factual_source_references':refs,'speech_context':context,'recent_input_text':recent,
                'speech_attempts':attempts,'accepted_attempt':len(attempts)-1 if accepted else None,
                'played_text':played_text,'played_chars':played_chars,'failure':failure,
                'compact':compact_audit,'runtime_factors':self.factors,
                'generation_halt':generation_halt,'recent_plan_observations':copy.deepcopy(self.plan_history),
                'memory_selection_observation':{'offered_ids':[c['id'] for c in candidate],
                    'declared_use_memory':plan['use_memory'] if plan else None,
                    'declared_memory_id':plan['memory_id'] if plan else None,
                    'Talk_grounding_ids':[r['id'] for r in refs],
                    'selection_correctness':'unreviewed; not inferred from schema or injected grounding'},
                'modeled_seconds_before':before['modeled_seconds'],'modeled_seconds_after':self.total/4.5,
                'canonical_grounding_independent_of_use_memory':True}
        self.records.append(record);self.log.write(json.dumps(record,ensure_ascii=False)+'\n');self.log.flush()
        self.turn+=1
        if generation_halt:self.status='halted_generation_error'
        elif self.total>=self.target:self.status='complete'
        elif self.zero>=30:self.status='stalled_zero_playback'
        elif self.turn>=1200:self.status='turn_limit_unmet'
        self.writer(self.dir/'state.json',self.state())
        return record

    def close(self, diagnostic=False):
        rows=self.rt.db.execute("SELECT id,body FROM events WHERE kind='played_speech' ORDER BY id").fetchall()
        assert len(rows)==len(self.played)==self.rt.db.execute('SELECT COUNT(*) FROM memory').fetchone()[0]
        assert [json.loads(body)['played_text'] for _,body in rows]==[p['text'] for p in self.played]
        for body,event_id in self.rt.db.execute('SELECT body,event_id FROM memory'):
            value=json.loads(body);event=json.loads(self.rt.db.execute('SELECT body FROM events WHERE id=?',(event_id,)).fetchone()[0])
            assert value['facts_verified'] is False and value['played_text']==event['played_text']
        assert sum(len(p['text']) for p in self.played)==self.total
        if diagnostic and self.status=='running':self.status='diagnostic_complete'
        (self.dir/'transcript.md').write_text('# '+self.name+'\n\n'+'\n\n'.join(p['text'] for p in self.played),encoding='utf8')
        self.writer(self.dir/'result.json',{**self.state(),'Event_Store_integrity':'pass','actual_audio':False})
        self.log.close();self.rt.close()
