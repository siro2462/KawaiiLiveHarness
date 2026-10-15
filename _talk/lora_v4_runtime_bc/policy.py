"""Frozen experimental interventions; no model or factual Memory mutation."""
import copy,json,re
from bootstrap import parse_plan,validate_plan,planner_prompt,talk_prompt,fallback_prompt

HISTORY_N=3
HISTORY_GUARD='直前の発話は話のつながりにだけ使う。発話内の具体的事実は未確認。確かな事実は記憶から使う。'
TRANSITION_MIN_COSINE=.80
TRANSITION_MIN_MARGIN=.02

def recent_measure(tok,prompt,recent,cut):
    enc=tok.encode(prompt,add_special_tokens=False);start=prompt.index(recent);end=start+len(recent)
    offsets=getattr(enc,'offsets',[])
    spans=[(a,b) for a,b in offsets if a>=start and b<=end]
    skipped=max(0,spans[cut-1][1]-start) if cut and spans else 0
    return {'recent_view_text':recent,'recent_view_chars':len(recent),
            'recent_tokens_in_prompt':len(spans) if spans else None,
            'recent_tokens_after_cut':max(0,len(spans)-cut) if spans else None,
            'recent_chars_after_cut':len(recent)-skipped,
            'recent_text_after_cut':recent[skipped:]}

def balanced_objects(raw):
    # Scan every opening brace, so a broken outer object cannot hide a later
    # balanced valid one. Quoted braces and escaped quotes do not affect depth.
    for start,ch in enumerate(raw):
        if ch!='{':continue
        depth=0;quoted=False;escaped=False
        for end in range(start,len(raw)):
            c=raw[end]
            if quoted:
                if escaped:escaped=False
                elif c=='\\':escaped=True
                elif c=='"':quoted=False
            elif c=='"':quoted=True
            elif c=='{':depth+=1
            elif c=='}':
                depth-=1
                if depth==0:
                    yield start,end+1,raw[start:end+1];break

def rescue_plan(raw,ids):
    failures=[]
    for start,end,obj in balanced_objects(raw):
        try:
            plan=parse_plan(obj,ids)
            return plan,{'selected_span':[start,end],'selected_json':obj,
                         'ignored_prefix':raw[:start],'ignored_suffix':raw[end:],
                         'rejected_objects':failures}
        except (ValueError,TypeError,KeyError) as exc:
            failures.append({'span':[start,end],'error':str(exc)})
    return None,{'selected_span':None,'rejected_objects':failures}

def get_plan(models,inp,control,improved=False):
    attempts=[];ids=[c['id'] for c in inp['memory_candidates']]
    current=copy.deepcopy(inp)
    for retry in range(2):
        rec=models.plan_control(current,retry) if control else models.plan(current,retry)
        rec=copy.deepcopy(rec)
        if 'input_text' in rec:
            rec.update(recent_measure(models.tok,rec['input_text'],inp['recent'],rec['context_cut_tokens']))
        try:parse_plan(rec['text'],ids);strict=True;strict_error=None
        except (ValueError,TypeError,KeyError) as exc:
            strict=False;strict_error=str(exc)
        try:json.loads(rec['text']);parse_failure=False
        except (ValueError,TypeError):parse_failure=True
        if control:plan,rescue=rescue_plan(rec['text'],ids)
        else:
            try:plan=parse_plan(rec['text'],ids)
            except (ValueError,TypeError,KeyError):plan=None
            rescue=None
        rec.update(schema_valid=plan is not None,strict_schema_valid=strict,
                   json_parse_failure=parse_failure,strict_schema_error=strict_error,
                   rescue=rescue,planner_retry=retry)
        if improved and plan:
            from consistency import check_plan,feedback
            check=check_plan(plan,inp['memory_candidates'],inp['current_state'].get('previous_memory_reference'))
            rec['memory_consistency']=check
            if not check['accepted']:
                plan=None
                current['current_state']['plan_validation_feedback']=feedback(check)
        attempts.append(rec)
        if plan:return plan,attempts
    return None,attempts

class PlanStore:
    def __init__(self):self.active=None;self.pending=None;self.last_valid=None
    def stage(self,plan,candidates):
        validate_plan(plan,[c['id'] for c in candidates])
        self.pending=copy.deepcopy({'plan':plan,'candidates':candidates})
    def commit(self):
        if self.pending is None:raise ValueError('No schema-valid pending Plan')
        self.active=copy.deepcopy(self.pending);self.last_valid=copy.deepcopy(self.active)
        self.pending=None;return copy.deepcopy(self.active)
    def fallback(self):
        self.pending=None
        if self.last_valid is None:return None
        self.active=copy.deepcopy(self.last_valid);return copy.deepcopy(self.active)

def recent_window(initial,played):
    return '\n'.join(p['text'] for p in played[-HISTORY_N:]) if played else initial+'\n'

def healthy_tail(initial,played):
    texts=[p['text'] for p in played if not p.get('loop',False)]
    all_text='\n'.join(texts[-2:]) if texts else initial
    sentences=re.findall(r'[^。！？!?\n]+[。！？!?]?|\n',all_text)
    sentences=[s.strip() for s in sentences if s.strip()]
    return ''.join(sentences[-2:])

def planner_input(recent,candidate,previous,history,improved=False,previous_candidates=None):
    state={'speech_history_status':'unverified generated speech; factual grounding is original Memory'} if history else {}
    if improved:
        from consistency import PLANNER_RULES
        state['memory_consistency_rules']=PLANNER_RULES
        if previous and previous['use_memory']:
            reference=next((c for c in previous_candidates or [] if c['id']==previous['memory_id']),None)
            if reference:state['previous_memory_reference']=copy.deepcopy(reference)
    return {'recent':recent,'current_state':state,'memory_candidates':candidate,'previous_plan':previous}

def speech_prompt(recent,candidate,plan,history=False,transition=None,improved=False):
    prompt=talk_prompt(recent,candidate,plan) if plan else fallback_prompt(recent)
    if history:prompt='【履歴の扱い】\n'+HISTORY_GUARD+'\n\n'+prompt
    if improved:
        from consistency import TALK_RULES
        prompt='【出来事の扱い】\n'+TALK_RULES+'\n\n'+prompt
    if transition:
        prompt=('【接続】\n旧話題: '+transition['old_topic']+
                '\n直前の発話から、新しい記憶を連想して自然につなぐ。固定の話題変更宣言は使わない。'+
                '\n新しい記憶に沿う具体的な一歩を話す。\n\n'+prompt)
    return prompt

def transition_check(vector,new_vector,old_vector):
    new=sum(a*b for a,b in zip(vector,new_vector))
    old=sum(a*b for a,b in zip(vector,old_vector)) if old_vector is not None else None
    margin=new-old if old is not None else None
    valid=new>=TRANSITION_MIN_COSINE and (margin is None or margin>=TRANSITION_MIN_MARGIN)
    return {'valid':valid,'new_memory_cosine':new,'old_memory_cosine':old,'margin':margin,
            'minimum_cosine':TRANSITION_MIN_COSINE,'minimum_margin':TRANSITION_MIN_MARGIN,
            'meaning':'minimum relatedness proxy; not a fact or naturalness guarantee'}
