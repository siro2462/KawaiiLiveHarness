"""One factorized experimental Arm; frozen detector, retrieval and Talk generator."""
import copy
from bootstrap import *
from baseline import Arm as BaselineArm
from policy import *

class Arm(BaselineArm):
    def __init__(self,name,initial):
        super().__init__(name,initial)
        self.control,self.history,self.transition_enabled=ARMS[name]
        self.improved=name=='BC_IMPROVED'
        self.store=PlanStore();self.transition=None;self.force_refresh=False
        self.active_memory_id=None
    def retrieval_recent(self):return super().recent()
    def model_recent(self):
        return recent_window(self.initial,self.played) if self.history else self.retrieval_recent()
    def install(self,bundle,turns=3):
        self.rt.set_plan(bundle['plan'],bundle['candidates'],turns)
        self.active_memory_id=bundle['plan']['memory_id'] if bundle['plan']['use_memory'] else None
    def restore_transition(self,episode):
        self.store.pending=None
        self.rt.plan=copy.deepcopy(episode['old_plan']);self.rt.candidates=copy.deepcopy(episode['old_candidates'])
        self.rt.remaining=1 if self.rt.plan else 0
        self.active_memory_id=episode['old_memory_id'];self.transition=None;self.force_refresh=False
    def step(self,models,embed,bank,vectors):
        before=self.total/4.5;retrieval=None;plan_attempts=[];compact_audit=None
        candidate=self.rt.candidates;fallback=False;episode=copy.deepcopy(self.transition)
        active_before=copy.deepcopy({'plan':self.rt.plan,'candidates':self.rt.candidates,
                                     'memory_id':self.active_memory_id})
        recent=(episode['healthy_recent'] if episode else self.model_recent()).rstrip('\n')
        plan=self.rt.plan if self.rt.remaining else None
        pending=None;transition_result=None
        if self.rt.needs_plan() or self.force_refresh or episode:
            query_text=self.retrieval_recent()[-1500:]
            query=embed.embed('query',[query_text])[0]
            candidate,retrieval=ranked_candidate(bank,vectors,query,self.blocked)
            retrieval.update(query_text=query_text,query_vector=query)
            self.blocked=None;self.force_refresh=False
            inp=planner_input(recent,candidate,self.rt.plan,self.history,self.improved,self.rt.candidates)
            proposed,plan_attempts=get_plan(models,inp,self.control,self.improved)
            if episode:
                # A schema-valid proposal is not yet active: speech must connect
                # to a different Memory before commit.
                eligible=(proposed is not None and proposed['use_memory'] and
                          proposed['memory_id']!=episode['old_memory_id'])
                if eligible:
                    self.store.stage(proposed,candidate);pending=copy.deepcopy(self.store.pending);plan=proposed
                else:
                    plan=None;transition_result={'status':'failed','reason':'no_valid_different_memory_plan',
                                                 'attempts':[],'episode':episode}
                    self.restore_transition(episode)
            elif self.control:
                if proposed:
                    self.store.stage(proposed,candidate);self.install(self.store.commit());plan=self.rt.plan
                else:
                    bundle=self.store.fallback();fallback=bundle is not None
                    if bundle:self.install(bundle,1);candidate=self.rt.candidates;plan=self.rt.plan
                    else:plan=None
            else:
                self.rt.candidates=candidate
                if proposed:self.rt.set_plan(proposed,candidate)
                plan=self.rt.plan if self.rt.remaining else None
                self.active_memory_id=plan['memory_id'] if plan and plan['use_memory'] else None
        prompt=speech_prompt(recent,candidate,plan,self.history,episode,self.improved) if plan or not episode else None
        attempts=[];accepted=None;intervened=False;failure=None;observed_loop=False
        checks=[]
        # CONTROL with no prior valid Plan cannot fabricate a fallback. Do not
        # speak an uncontrolled NONE prompt; log this unavailable initial state.
        can_speak=prompt is not None and not (self.control and plan is None)
        if can_speak:
            retry_note=''
            for retry in range(2):
                actual_prompt=retry_note+prompt
                generated=models.generate('v4',actual_prompt,recent,SEED+self.turn+retry*10000)
                generated.update(recent_measure(models.tok,actual_prompt,recent,generated['context_cut_tokens']))
                failure=hard_failure(generated['text'])
                vector=embed.embed('passage',[generated['text']])[0]
                loop=detect(generated['text'],vector,self.played,failure)
                generated.update(hard_failure=failure,loop=loop,semantic_vector=vector)
                attempts.append(generated);observed_loop|=loop['loop']
                if self.improved:
                    from consistency import check_speech,feedback
                    check=check_speech(generated['text'],candidate,plan)
                    generated['memory_consistency']=check
                    if not check['accepted']:
                        failure='memory_consistency'
                        retry_note='【整合性の注意】\n'+feedback(check)+'\n\n'
                        continue
                if episode:
                    index={m['id']:i for i,m in enumerate(bank)}
                    old_vector=vectors[index[episode['old_memory_id']]] if episode['old_memory_id'] in index else None
                    check=transition_check(vector,vectors[index[plan['memory_id']]],old_vector)
                    check.update(attempt=retry,hard_failure=failure,detector_loop=loop['loop'])
                    check['accepted']=check['valid'] and failure is None and not loop['loop']
                    generated['transition_validation']=check;checks.append(check)
                    if check['accepted']:
                        self.install(self.store.commit());candidate=self.rt.candidates;plan=self.rt.plan
                        self.transition=None;accepted=generated
                        transition_result={'status':'success','attempts':checks,'episode':episode,
                                           'new_memory_id':plan['memory_id']};break
                    continue
                if loop['loop']:
                    intervened=True;self.interventions+=1
                    self.blocked=(plan['memory_id'] if plan and plan['use_memory'] else candidate[0]['id'] if candidate else None)
                    # Keep the legacy retrieval view in every arm. HISTORY does
                    # not expose this Compact to either LLM.
                    excluded={p['turn'] for p in self.played if p['loop']}
                    self.compacted,compact_audit=compact(self.initial,self.played,excluded)
                    self.context_after_compact=[]
                    compact_audit.update(compact_text=self.compacted,discarded_candidate=generated['text'],
                                         llm_exposed=not self.history)
                    if self.transition_enabled:
                        self.transition={'trigger_turn':self.turn,'old_plan':copy.deepcopy(plan),
                            'old_candidates':copy.deepcopy(candidate),'old_memory_id':self.blocked,
                            'old_topic':plan['topic'] if plan else '直前の話題',
                            'healthy_recent':healthy_tail(self.initial,self.played)}
                        self.rt.remaining=0;self.force_refresh=True
                    elif self.control:
                        self.force_refresh=True;self.rt.remaining=0
                    else:
                        self.rt.plan=None;self.rt.remaining=0;self.rt.candidates=[];self.active_memory_id=None
                    break
                if failure is None:accepted=generated;break
        elif transition_result is None:
            failure='no_valid_plan_available' if self.control else 'transition_plan_invalid'
        if episode and accepted is None and transition_result is None:
            transition_result={'status':'failed','reason':'speech_transition_validation_failed',
                               'attempts':checks,'episode':episode}
            self.restore_transition(episode)
        if observed_loop:
            if self.first_loop is None:self.first_loop={'turn':self.turn,'modeled_seconds':before}
            self.loop_streak+=1
            if self.collapse is None and (self.loop_streak>=POLICY['collapse_consecutive_candidates'] or
                                         any(a['hard_failure']=='repetition' for a in attempts)):
                self.collapse={'turn':self.turn,'modeled_seconds':before,
                               'definition':'three detected-loop candidate turns or within-output exact collapse'}
        else:self.loop_streak=0
        played_chars=0
        if accepted:
            played_chars=min(len(accepted['text']),TARGET-self.total)
            self.rt.commit_playback(accepted['text'],played_chars)
            played_text=accepted['text'][:played_chars]
            self.played.append({'turn':self.turn,'text':played_text,'vector':embed.embed('passage',[played_text])[0],
                               'loop':accepted['loop']['loop'],'plan':copy.deepcopy(plan),
                               'memory_id':plan['memory_id'] if plan and plan['use_memory'] else None})
            if self.compacted is not None:self.context_after_compact.append(played_text)
            self.total+=played_chars;self.zero=0
        else:
            self.zero+=1
            if not episode and not intervened:
                if self.control:self.force_refresh=True;self.rt.remaining=0
                else:self.rt.plan=None;self.rt.remaining=0;self.active_memory_id=None
        # Candidate, pending Plan and old active bundle are independently logged.
        record={'arm':self.name,'turn':self.turn,'seed':SEED+self.turn,'modeled_seconds_before':before,
                'candidate':candidate,'retrieval':retrieval,'plan':copy.deepcopy(plan),
                'planner_attempts':plan_attempts,'speech_attempts':attempts,
                'accepted_attempt':len(attempts)-1 if accepted else None,
                'played_text':accepted['text'][:played_chars] if accepted else '',
                'played_chars':played_chars,'intervened':intervened,'compact':compact_audit,
                'failure':failure,'recent_after':self.retrieval_recent(),'authoritative_recent_after':self.rt.recent(),
                'modeled_seconds_after':self.total/4.5,
                'runtime_factors':{'control':self.control,'history':self.history,'transition':self.transition_enabled},
                'recent_input_text':recent,'recent_input_chars':len(recent),
                'recent_input_tokens':len(models.tok.encode(recent,add_special_tokens=False).ids),
                'recent_utterance_turns':[p['turn'] for p in self.played[:-1][-HISTORY_N:]] if self.history and accepted else
                                         [p['turn'] for p in self.played[-HISTORY_N:]] if self.history else None,
                'last_valid_plan_fallback':fallback,'active_bundle_before':active_before,
                'pending_bundle':pending,'active_bundle_after':{'plan':self.rt.plan,'candidates':self.rt.candidates,
                                                              'memory_id':self.active_memory_id},
                'active_memory_id':self.active_memory_id,'transition':transition_result,
                'played_semantic_vector':self.played[-1]['vector'] if played_chars else None,
                'transition_pending':self.transition,'mode':'transition' if episode else 'normal',
                'recent_source_mode':'last_two_healthy_sentences' if episode else 'last_three_utterances' if self.history else 'legacy_R2_view',
                'factual_grounding':'unchanged original Memory; generated speech is unverified'}
        self.log.write(json.dumps(record,ensure_ascii=False)+'\n');self.log.flush()
        self.turn+=1
        if self.total>=TARGET:self.status='complete'
        elif self.zero>=30:self.status='stalled_zero_playback'
        elif self.turn>=1200:self.status='turn_limit_unmet'
        write(self.dir/'state.json',self.state());return record
