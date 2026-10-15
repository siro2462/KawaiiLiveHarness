"""Canonical Memory, recent window, source binding and expiring validated Plans."""
import copy
from runtime_state import PlanStore, memory_reference
from planner_policy import CONTRACT, SCHEMA_INSTRUCTION
from fact_gate import VERSION
from generation_errors import ContextBudgetError

_CURRENT = object()

HISTORY_GUARD='直前の発話は話のつながりにだけ使う。発話内の具体的事実は未確認。確かな事実は記憶から使う。'


def original(ref):
    return {'id':ref['id'],'body':ref['body']} if ref else None


class MemoryStore:
    def __init__(self, bank):
        self.bank={m['id']:copy.deepcopy(m) for m in bank}
        if len(self.bank)!=len(bank): raise ValueError('Duplicate canonical Memory IDs')
        self.current=None;self.previous=None

    def preview(self, candidate):
        if len(candidate)>1:raise ValueError('v5 selects at most one original Memory')
        memory=candidate[0] if candidate else None
        if memory and (memory['id'] not in self.bank or self.bank[memory['id']]!=memory):
            raise ValueError('Candidate is not the original immutable Memory')
        return copy.deepcopy(memory)

    def references(self, proposed=_CURRENT):
        # Archived/available Memories are not implicit evidence for this turn.
        memory=original(self.current) if proposed is _CURRENT else proposed
        if memory and self.bank.get(memory['id'])!=memory:raise ValueError('Unknown factual source')
        return [copy.deepcopy(memory)] if memory else []

    def commit(self, memory):
        if memory is None:
            if self.current:self.previous=copy.deepcopy(self.current)
            self.current=None
            return
        if self.bank.get(memory['id'])!=memory:raise ValueError('Unknown canonical Memory')
        if self.current and self.current['id']!=memory['id']:self.previous=copy.deepcopy(self.current)
        self.current=memory_reference(memory)


class GroundedPlanStore(PlanStore):
    def stage(self, plan, memory, turn, fact_check, lifetime=3):
        if fact_check.get('version')!=VERSION:
            raise ValueError('Expected the admitted fact validator')
        expected=[memory_reference(memory)] if memory else []
        if fact_check['source_references']!=expected:
            raise ValueError('Fact validation and Talk must use exactly the same original Memory')
        super().stage(plan,memory,turn,fact_check,lifetime)

    def usable(self, turn, memory):
        if self.active is None:return None
        if turn>=self.active['expires_before_turn'] or self.active['grounding']!=memory_reference(memory):return None
        return copy.deepcopy(self.active)


def recent_view(initial, played):
    return '\n'.join(p['text'] for p in played[-3:]) if played else initial


def planner_input(recent, candidate, previous, memory, reason):
    return {'recent':recent,'memory_candidates':copy.deepcopy(candidate),'previous_plan':copy.deepcopy(previous),
            'current_state':{'speech_history_status':'unverified generated speech; original Memory is factual grounding',
                             'factual_grounding_memory_id':memory['id'] if memory else None,
                             'plan_refresh_reason':reason,
                             'memory_rules':'具体的経験・物・数量・時点は元Memoryを根拠にする。話を続ける、掘り下げる、関連する方向へ変える判断は自由。'}}


def speech_context(initial, played, memory, plan):
    recent=recent_view(initial,played).rstrip('\n')
    ref=memory_reference(memory)
    if plan:CONTRACT['validate_plan'](plan,[ref['id']] if ref else [])
    topic=plan['topic'] if plan else 'なし'
    flow=''.join('- '+beat+'\n' for beat in plan['flow']) if plan else 'なし\n'
    prefix=('【履歴の扱い】\n'+HISTORY_GUARD+'話題と流れは方向づけ。出来事の事実は記憶から使う。\n\n'
            '【記憶】\n'+(ref['body'] if ref else 'なし')+'\n\n【話題】\n'+topic+
            '\n\n【流れ】\n'+flow+'\n【直前の発話】\n')
    prompt=prefix+recent+'\n'
    return {'prompt':prompt,'recent':recent,'recent_span':[len(prefix),len(prefix)+len(recent)],
            'grounding':ref,'mode':'planned' if plan else 'grounded_planless',
            'recent_utterance_turns':[p['turn'] for p in played[-3:]],
            'factuality':'only original Memory is a source; played history remains unverified'}


def protected_ids(tok, prompt, recent, span, budget=928):
    start,end=span
    if prompt[start:end]!=recent:raise ValueError('Recent span mismatch')
    encoded=tok.encode(prompt,add_special_tokens=False)
    removable=[i for i,(a,b) in enumerate(encoded.offsets) if a>=start and b<=end]
    cut=max(0,len(encoded.ids)-budget)
    if cut>len(removable):raise ContextBudgetError('Protected original Memory/Plan/state exceed context budget')
    gone=set(removable[:cut])
    ids=[token for i,token in enumerate(encoded.ids) if i not in gone]
    skipped=max(0,encoded.offsets[removable[cut-1]][1]-start) if cut else 0
    return ids,{'context_cut_tokens':cut,'recent_span':list(span),'recent_text_after_cut':recent[skipped:],
                'recent_tokens_before_cut':len(removable),'recent_tokens_after_cut':len(removable)-cut,
                'only_left_recent_removed':True}


def shrink_recent_context(context):
    """Retry length errors without removing or rewriting protected facts/Plan."""
    result=copy.deepcopy(context)
    start,end=result['recent_span']
    if result['prompt'][start:end]!=result['recent']:raise ValueError('Recent span mismatch')
    result['recent']=result['recent'][len(result['recent'])//2:]
    result['prompt']=result['prompt'][:start]+result['recent']+result['prompt'][end:]
    result['recent_span']=[start,start+len(result['recent'])]
    result['error_recovery_recent_only']=True
    return result
