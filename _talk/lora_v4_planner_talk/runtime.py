"""Small synchronous runtime. Playback is explicitly simulated in this harness."""
import json
import re
import sqlite3
from contracts import parse_plan,validate_plan

def hard_failure(text):
    if not text.strip():return 'empty'
    if re.search(r'【|<\s*\w+|^\s*[\[{]|^\s*(?:Topic|Flow|話題|流れ)\s*[:：]',text,re.I):return 'markup_or_plan'
    if len(text.strip())<6:return 'too_short'
    if any(text.count(text[i:i+12])>=3 for i in range(max(0,len(text)-11))):return 'repetition'
    return None

class Runtime:
    def __init__(self,path,initial_recent=''):
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS memory(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL UNIQUE, body TEXT NOT NULL)')
        self.db.commit();self.initial_recent=initial_recent;self.plan=None;self.candidates=[];self.remaining=0
    def recent(self):
        speeches=[json.loads(body)['played_text'] for (body,) in self.db.execute("SELECT body FROM events WHERE kind='played_speech' ORDER BY id")]
        return self.initial_recent+'\n'+''.join(speeches)
    def event(self,kind,body):
        if kind in {'plan','generated_speech'}:raise ValueError('Ephemeral/candidate data must not enter authoritative events')
        cur=self.db.execute('INSERT INTO events(kind,body) VALUES(?,?)',(kind,json.dumps(body,ensure_ascii=False)))
        self.db.commit();return cur.lastrowid
    def strong_event(self,kind,body):
        eid=self.event(kind,body);self.plan=None;self.remaining=0;return eid
    def set_plan(self,plan,candidates,turns=3):
        validate_plan(plan,[c['id'] for c in candidates]);self.plan=plan;self.candidates=candidates;self.remaining=turns
    def commit_playback(self,candidate,played_chars):
        if type(played_chars) is not int or not 0<=played_chars<=len(candidate):raise ValueError('Invalid playback range')
        if not played_chars:return None
        text=candidate[:played_chars]
        eid=self.event('played_speech',{'played_text':text,'playback':'simulated','candidate_chars':len(candidate),'played_chars':played_chars,'complete':played_chars==len(candidate)})
        # What was said is authoritative, not the factual truth of its claims.
        body={'kind':'speech_record','played_text':text,'source_event_id':eid,'facts_verified':False}
        self.db.execute('INSERT INTO memory(event_id,body) VALUES(?,?)',(eid,json.dumps(body,ensure_ascii=False)));self.db.commit()
        self.remaining=max(0,self.remaining-1)
        if played_chars<len(candidate):self.plan=None;self.remaining=0
        return eid
    def needs_plan(self):return self.plan is None or self.remaining==0
    def close(self):self.db.close()

def obtain_plan(generate,inp):
    attempts=[]
    for retry in range(2):
        out=generate(inp,retry);attempts.append(out)
        try:
            plan=parse_plan(out['text'],[c['id'] for c in inp['memory_candidates']])
            return plan,attempts
        except (ValueError,KeyError,TypeError):pass
    return None,attempts

def obtain_speech(generate):
    attempts=[]
    for retry in range(2):
        out=generate(retry);attempts.append(out)
        reason=hard_failure(out['text'])
        if reason is None:return out,attempts,None
    return None,attempts,reason
