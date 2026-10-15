"""Version-4 planning contracts; no model inference or semantic label generation."""
import json

PLAN_KEYS={'use_memory','memory_id','topic','flow'}
INPUT_KEYS={'recent','current_state','memory_candidates','previous_plan'}


def validate_plan(plan,candidate_ids):
    if not isinstance(plan,dict) or set(plan)!=PLAN_KEYS:
        raise ValueError('Plan must contain exactly four fields')
    if type(plan['use_memory']) is not bool:raise ValueError('use_memory must be bool')
    if plan['use_memory']:
        if not isinstance(plan['memory_id'],str) or plan['memory_id'] not in candidate_ids:
            raise ValueError('Unknown selected memory')
    elif plan['memory_id'] is not None:raise ValueError('Unused memory_id must be null')
    if not isinstance(plan['topic'],str) or not plan['topic'].strip():raise ValueError('Empty topic')
    beats=plan['flow']
    if not isinstance(beats,list) or not 2<=len(beats)<=4:
        raise ValueError('Flow requires 2 to 4 beats')
    if any(not isinstance(x,str) or not x.strip() for x in beats):raise ValueError('Empty beat')
    return plan


def parse_plan(raw,candidate_ids):
    def strict(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('Duplicate JSON key')
            result[k]=v
        return result
    return validate_plan(json.loads(raw,object_pairs_hook=strict),candidate_ids)


def validate_input(data):
    if not isinstance(data,dict) or set(data)!=INPUT_KEYS:raise ValueError('Planner input fields')
    if not isinstance(data['recent'],str) or not isinstance(data['current_state'],dict):raise ValueError('Input types')
    candidates=data['memory_candidates']
    if not isinstance(candidates,list) or len(candidates)>1:raise ValueError('Initial retrieval must be 0 or 1')
    for c in candidates:
        if not isinstance(c,dict) or set(c)!={'id','body'}:raise ValueError('Memory fields')
        if not all(isinstance(c[k],str) and c[k].strip() for k in ['id','body']):raise ValueError('Empty memory')
    if data['previous_plan'] is not None:
        # An earlier plan may reference an earlier memory; membership is checked
        # against its own referenced ID, never treated as a currently selected one.
        p=data['previous_plan'];validate_plan(p,[p.get('memory_id')])
    return data


def planner_prompt(data):
    validate_input(data)
    mem='なし' if not data['memory_candidates'] else '\n'.join(
        'id: '+c['id']+'\nbody: '+c['body'] for c in data['memory_candidates'])
    previous='なし' if data['previous_plan'] is None else json.dumps(data['previous_plan'],ensure_ascii=False,separators=(',',':'))
    return '【直近の確定発話】\n'+data['recent'].rstrip('\n')+'\n\n【現在状態】\n'+json.dumps(
        data['current_state'],ensure_ascii=False,separators=(',',':'))+'\n\n【Memory候補】\n'+mem+'\n\n【前回Plan】\n'+previous+'\n'


def talk_prompt(recent,candidates,plan):
    validate_plan(plan,[c['id'] for c in candidates])
    memory=next(c['body'] for c in candidates if c['id']==plan['memory_id']) if plan['use_memory'] else 'なし'
    return '【記憶】\n'+memory+'\n\n【話題】\n'+plan['topic']+'\n\n【流れ】\n'+''.join(
        '- '+b+'\n' for b in plan['flow'])+'\n【直前の発話】\n'+recent.rstrip('\n')+'\n'


def fallback_prompt(recent,memory='なし'):
    return '【記憶】\n'+memory+'\n\n【話題】\nなし\n\n【流れ】\nなし\n\n【直前の発話】\n'+recent.rstrip('\n')+'\n'
