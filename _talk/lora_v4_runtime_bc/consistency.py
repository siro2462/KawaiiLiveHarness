"""Narrow, evidence-bearing checks. No content planning or semantic judge."""
import re

VERSION='explicit-memory-claims-v1'
PLANNER_RULES=(
    '元Memoryが具体的な経験の根拠。Recentと前回Planの追加情報は未確認。'
    'Memoryの出来事を話すならuse_memory=trueで候補IDを選ぶ。'
    '過去の出来事を今起きている出来事に変えず、物・否定・順序・理由を入れ替えない。'
    'Memoryにない具体的経験を起きた事実として足さない。'
    '自由な雑談はuse_memory=falseでよい。感想・冗談・関連する連想は自由。'
    '続ける・掘り下げる・切り替える判断は自分で行い、直前とのつながりを残す。')
TALK_RULES=(
    '出来事の根拠は元の記憶。過去は過去として話し、物・否定・順序・理由を変えない。'
    'RecentやPlanにだけある具体的経験を起きた事実にしない。'
    '感想・冗談・言い直し・関連する脱線は自由。話題を変えるなら直前から自然につなぐ。')

# These are linguistic predicate families, not Memory IDs or scripted topics.
EVENTS={
 'carry':r'持って(?:きた|来た|いった|行った|くるのを忘れた|いくのを忘れた|き忘れた)',
 'cook':r'作った',
 'eat':r'(?:食べた|食べちゃった)',
 'buy':r'(?:買った|購入した)',
 'visit':r'(?:行った|出かけた)',
 'enter':r'入った',
 'take':r'(?:取った|収穫した)',
 'delete':r'(?:消した|削除した)',
}
MODAL=re.compile(r'もし|例えば|たとえ|冗談|比喩|想像|今度|今でも|次は|これから|だったら|としたら|なら|かも|かな|[？?]|したい|してみたい|ようかな')
PERSONAL=re.compile(r'私|自分|この前|昨日|さっき|その時|んだ|んだよ|たよ|たの[。！!]?\Z')
NOUN=r'[一-龥々ァ-ヶーA-Za-z0-9]{1,20}'

def pieces(text):
    return [s.strip() for s in re.findall(r'[^。！？!?\n]+[。！？!?]?',text) if s.strip()]

def events(text):
    result=[]
    for clause in pieces(text):
        for family,verb in EVENTS.items():
            pattern=re.compile('(?P<object>'+NOUN+r')(?:を|に|へ)(?:[^。！？\n]{0,8}?)'+verb)
            for match in pattern.finditer(clause):
                result.append({'family':family,'object':match['object'],
                               'span':match.group(0),'clause':clause})
    return result

def related_object(a,b):
    return a==b or (min(len(a),len(b))>=2 and (a in b or b in a))

def issues_for(text,memory,planner=False):
    body=memory['body'];source_events=events(body);issues=[]
    for clause in pieces(text):
        if MODAL.search(clause):continue
        def add(code,span,evidence):
            issues.append({'code':code,'span':span,'memory_id':memory['id'],
                           'source_span':evidence,'source_body':body})
        # Require an explicit now marker, a source object and progressive verb.
        # Narrative historic-present without such a marker is not rejected.
        if re.search(r'今(?:さ|は|、|もう|ちょうど)?|いま|現在',clause) and not re.search(r'今朝|今日',clause):
            for event in source_events:
                progressive={'cook':r'作って(?:いる|る)', 'eat':r'食べて(?:いる|る)',
                             'carry':r'持って(?:きている|きてる)', 'buy':r'買って(?:いる|る)'}.get(event['family'])
                if event['family']=='cook' and '食べた' in body:progressive=r'(?:作って|食べて)(?:いる|る)'
                if progressive and event['object'] in clause and re.search(progressive,clause):
                    add('past_event_recast_as_now',clause,event['span'])
        # Explicit polarity reversal of the same named object.
        for source in re.finditer('(?P<object>'+NOUN+r')(?:が|は)なかった',body):
            opposite=re.search(re.escape(source['object'])+r'(?:が|は)(?:ちゃんと|たっぷり)?あった',clause)
            if opposite:add('source_absence_reversed',opposite.group(0),source.group(0))
        for source in re.finditer('(?P<object>'+NOUN+r')(?:が|は)あった',body):
            opposite=re.search(re.escape(source['object'])+r'(?:が|は)なかった',clause)
            if opposite:add('source_presence_reversed',opposite.group(0),source.group(0))
        # Retold concrete objects must have an original source. This gate is
        # restricted to asserted past experience, not generic advice/opinion.
        for event in events(clause):
            if event['object'] in body:continue
            same=[s for s in source_events if s['family']==event['family']]
            if any(related_object(s['object'],event['object']) for s in same):continue
            if not planner and not same and not PERSONAL.search(clause):continue
            evidence=' / '.join(s['span'] for s in same) or body
            add('unsupported_concrete_event_object',event['span'],evidence)
    unique={ (x['code'],x['span'],x['memory_id']):x for x in issues }
    return list(unique.values())

def check_plan(plan,candidates,previous_reference=None):
    parts=[plan['topic']]+plan['flow'];issues=[]
    if plan['use_memory']:
        selected=next(c for c in candidates if c['id']==plan['memory_id'])
        for part in parts:issues.extend(issues_for(part,selected,planner=True))
    else:
        references={c['id']:c for c in candidates}
        if previous_reference:references[previous_reference['id']]=previous_reference
        for memory in references.values():
            original=events(memory['body'])
            for part in parts:
                if MODAL.search(part):continue
                for event in events(part):
                    source=next((s for s in original if s['family']==event['family'] and
                                 related_object(s['object'],event['object'])),None)
                    if source:issues.append({'code':'memory_experience_without_reference','span':event['span'],
                        'memory_id':memory['id'],'source_span':source['span'],'source_body':memory['body']})
    return {'accepted':not issues,'issues':issues,'rule_version':VERSION,
            'scope':'narrow explicit claims only; acceptance is not a factuality guarantee'}

def check_speech(text,candidates,plan):
    memory=next((c for c in candidates if plan and plan['use_memory'] and c['id']==plan['memory_id']),None)
    issues=issues_for(text,memory) if memory else []
    return {'accepted':not issues,'issues':issues,'rule_version':VERSION,
            'scope':'selected original Memory only; general free-chat facts are unverified'}

def feedback(check):
    codes={x['code'] for x in check['issues']}
    notes=[]
    if 'memory_experience_without_reference' in codes:notes.append('元Memoryの具体的経験を話すならuse_memory=trueと候補IDを使う。')
    if 'past_event_recast_as_now' in codes:notes.append('過去の出来事を現在進行形に変更しない。')
    if codes & {'source_absence_reversed','source_presence_reversed'}:notes.append('元Memoryの有無・否定を反転しない。')
    if 'unsupported_concrete_event_object' in codes:notes.append('元Memoryにない物を使った具体的経験を足さない。感想や連想は自由。')
    return ''.join(notes)
