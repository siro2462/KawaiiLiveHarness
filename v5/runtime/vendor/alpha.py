#!/usr/bin/env python3
"""ZIPちゃん Harness α: inspectable recall graph + working set + thought + DMN-lite.

Sandbox experiment. Real streamers' transcript topics are reference materials, NOT ZIP canon.
No model calls, no speech synthesis, and no promotion of generated claims to facts.
"""
from __future__ import annotations
import argparse, dataclasses, hashlib, json, math, re, sqlite3, time, zipfile
from collections import defaultdict, Counter
from pathlib import Path

import numpy as np
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT=Path(__file__).resolve().parent
DB_DEFAULT=ROOT/'outputs'/'alpha_memory.sqlite'
TERMS = [
 'ゲーム','ゲーム配信','スプラ','マイクラ','ホラー','マップ','探索','スクリーンショット','スクショ','クエスト','RPG','RTA','大会','配信','コメント','視聴者','チャット',
 '犬','猫','散歩','公園','池','植物','花','ミント','バジル','ベランダ','洗濯','洗濯ばさみ','風','雨','傘','長靴','青','赤','黄色','緑','白','黒',
 '手袋','バッグ','エコバッグ','忘れ物','メモ','スマホ','文房具','消しゴム','付箋','ノート','本棚','図書館','本','しおり','手紙','封筒','切手','友達','弟',
 '映画','旅行','電車','駅','待ち合わせ','道','迷子','車','自転車','時間','時計','仕事','学校','学生','中学','高校','小学校','昔','子ども','子供','家族',
 '食べ物','ご飯','料理','調理','食事','パン','パン屋','お茶','砂糖','コーヒー','牛乳','カレー','ラーメン','ジャム','トマト','冷蔵庫','ラベル',
 '値段','価格','高い','安い','買い物','買う','購入','失敗','間違い','気づく','見つける','探す','思い出す','比較','予定','変更','予定変更',
 '音楽','歌','ライブ','アニメ','VTuber','ぬいぐるみ','グッズ','写真','動画','編集','撮影','インターネット','パソコン','PC','スマートフォン',
 '北海道','東京','大阪','千葉','日本','外国','病院','寝る','睡眠','朝','夜','昼','夕方','昨日','明日','翌朝',
]
# No generic sentiment/tense terms here: links should be interpretable via concrete cues.
STOP_TAGS={'青','赤','白','黒','緑','高い','安い','道','本','朝','夜','昼','時間','買う','予定','間違い','失敗','気づく','見つける','探す','比較','昔'}
SYNONYMS={'スクリーンショット':'スクショ','RPG':'ゲーム','ゲーム配信':'ゲーム','スマートフォン':'スマホ','パン屋':'パン','予定変更':'変更'}


def jdump(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'))
def jload(x):return json.loads(x) if x else None

def tags_for(text):
    tags=set()
    for term in sorted(TERMS,key=len,reverse=True):
        if term.lower() in text.lower(): tags.add(SYNONYMS.get(term,term))
    return sorted(tags)

def normalize_yaml(x):
    if isinstance(x,list):
        if x and all(isinstance(i,tuple) and len(i)==2 for i in x): return {k:normalize_yaml(v) for k,v in x}
        return [normalize_yaml(i) for i in x]
    if isinstance(x,dict):return {k:normalize_yaml(v) for k,v in x.items()}
    return x

def source_memories(zip_path):
    out=[]
    with zipfile.ZipFile(zip_path) as z:
        for filename in sorted(z.namelist()):
            if not filename.endswith(('.yaml','.yml')):continue
            data=normalize_yaml(yaml.safe_load(z.read(filename).decode('utf-8-sig')))
            if not isinstance(data,dict):continue
            source=Path(filename).name
            for ordinal,topic_data in enumerate(data.get('topics',[])):
                t=str(topic_data.get('topic') or '')
                beats=re.findall(r'\[([^\]]+)\]',t)
                if not beats:beats=[t]
                speech=[str(st.get('speak') or '') for st in (topic_data.get('styles') or []) if st.get('speak')]
                if not speech:continue
                original_id=hashlib.sha256(f'{filename}#{ordinal}'.encode()).hexdigest()[:16]
                label=beats[0].strip('「」『』 ')[:58]
                out.append({'id':'R'+original_id,'title':label,'beats':beats,
                  'text':'。'.join(beats),'source':source,'ordinal':ordinal,
                  'authority':'reference_transcript_unverified','namespace':'reference',
                  'speech_samples':speech})
    return out

def fixture_memories(path):return json.loads(Path(path).read_text(encoding='utf-8'))

class Alpha:
 def __init__(self,db=DB_DEFAULT,e5_model_dir=None):
    self.e5_model_dir=e5_model_dir
    self._e5=None
    if e5_model_dir:
      from sentence_transformers import SentenceTransformer
      self._e5=SentenceTransformer(e5_model_dir,local_files_only=True)
    self.db=Path(db);self.db.parent.mkdir(parents=True,exist_ok=True)
    self.con=sqlite3.connect(str(self.db));self.con.row_factory=sqlite3.Row
    self._schema();self._vec_cache={}
 def close(self):self.con.close()
 def _schema(self):
    self.con.executescript('''
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, namespace TEXT NOT NULL, authority TEXT NOT NULL, source TEXT NOT NULL,
       ordinal INTEGER NOT NULL DEFAULT 0,title TEXT NOT NULL,body TEXT NOT NULL,beats TEXT NOT NULL,tags TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS links(src TEXT NOT NULL,dst TEXT NOT NULL,kind TEXT NOT NULL,weight REAL NOT NULL,evidence TEXT NOT NULL,
       PRIMARY KEY(src,dst,kind),FOREIGN KEY(src) REFERENCES memories(id),FOREIGN KEY(dst) REFERENCES memories(id));
    CREATE INDEX IF NOT EXISTS links_dst ON links(dst);
    CREATE TABLE IF NOT EXISTS sessions(session_id TEXT PRIMARY KEY,namespace TEXT NOT NULL,state_json TEXT NOT NULL,updated REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL, ts REAL NOT NULL, action TEXT NOT NULL,
      payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    ''');self.con.commit()
 def populate(self, sources, fixture_file, force=False):
    n=self.con.execute('select count(*) from memories').fetchone()[0]
    if n and not force:return self.stats()
    if force:
      for table in ('audit','sessions','links','memories','meta'):self.con.execute(f'DELETE FROM {table}')
    refs=source_memories(sources);fxtures=fixture_memories(fixture_file)
    allmem=refs+fxtures
    for m in allmem:
      tags=tags_for(m['title']+' '+m['text'])
      self.con.execute('insert into memories values(?,?,?,?,?,?,?,?,?)',(m['id'],m['namespace'],m['authority'],m['source'],m.get('ordinal',0),m['title'],m['text'],jdump(m['beats']),jdump(tags)))
    self.con.commit()
    for namespace in ('reference','fixtures'):
      group=[m for m in allmem if m['namespace']==namespace]
      self._build_links(group)
    self.con.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',('vector_backend','TF-IDF char(2,4), local offline proxy; NOT E5'))
    self.con.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',('corpus_notice','reference=real streamer materials, not ZIP personal memory; fixtures=synthetic test facts'))
    self.con.commit(); self._vec_cache.clear()
    return self.stats()
 def _build_links(self, group):
    if not group:return
    ns=group[0]['namespace']; texts=[m['title']+' '+m['text'] for m in group]
    vec=TfidfVectorizer(analyzer='char',ngram_range=(2,4),min_df=1,max_features=60000,sublinear_tf=True)
    X=vec.fit_transform(texts);sims=(X@X.T).toarray()
    tagsets=[set(tags_for(t))-STOP_TAGS for t in texts]
    ids=[m['id'] for m in group]
    def edge(i,j,kind,weight,reason):
      if i==j:return
      a,b=sorted((ids[i],ids[j]))
      self.con.execute('INSERT OR REPLACE INTO links VALUES(?,?,?,?,?)',(a,b,kind,round(float(weight),5),reason))
    for i,m in enumerate(group):
      # Within a source file, neighboring topics have sequence provenance, not factual causality.
      for j in range(i+1,min(len(group),i+3)):
        if group[j]['source']==m['source'] and group[j].get('ordinal',0)-m.get('ordinal',0)==1:
          edge(i,j,'source_adjacent',.15,'same source file; neighboring topic, not asserted same experience')
      # Maximum four semantic edges, meaningful similarity only. They are association hypotheses.
      neighbors=sorted([(j,sims[i,j]) for j in range(len(group)) if j!=i],key=lambda x:-x[1])
      for j,sim in neighbors[:4]:
        if sim>=.13:edge(i,j,'semantic', min(.75,float(sim)),f'char-TFIDF cosine={sim:.3f}; hypothesis')
      # Strong tags only: overlap must be specific and ranked, to limit graph pollution.
      links=[]
      for j in range(len(group)):
        if i==j:continue
        common=tagsets[i]&tagsets[j]
        if common:
          idf=max(1.0,math.log((len(group)+1)/(2+sum(1 for ts in tagsets if any(t in ts for t in common)))))
          sc=(len(common)*idf)/max(1,len(tagsets[i]|tagsets[j]))
          links.append((j,sc,common))
      for j,score,common in sorted(links,key=lambda a:-a[1])[:4]:
        if score>=.055:edge(i,j,'shared_tag',min(.68,.18+score),','.join(sorted(common))[:120])
    self.con.commit()
 def stats(self):
    return {'counts':{x['namespace']:x['n'] for x in self.con.execute('select namespace,count(*) n from memories group by namespace')},
      'links':{x['kind']:x['n'] for x in self.con.execute('select kind,count(*) n from links group by kind')},
      'audit':self.con.execute('select count(*) from audit').fetchone()[0]}
 def get(self,mid):
    r=self.con.execute('SELECT * FROM memories WHERE id=?',(mid,)).fetchone()
    if r is None:return None
    return {**dict(r),'beats':jload(r['beats']),'tags':jload(r['tags'])}
 def all(self,ns):return [self.get(row['id']) for row in self.con.execute('SELECT id FROM memories WHERE namespace=? ORDER BY id',(ns,))]
 def neighbor_edges(self,mid,ns=None):
    rows=self.con.execute('select * from links where src=? OR dst=?',(mid,mid)).fetchall()
    out=[]
    for r in rows:
      other=r['dst'] if r['src']==mid else r['src']
      if ns and self.get(other)['namespace']!=ns:continue
      out.append({**dict(r),'target':other})
    return out
 def _vector(self,ns):
    if ns not in self._vec_cache:
      arr=self.all(ns)
      if self._e5:
        vector=None
        mat=self._e5.encode(['passage: '+m['title']+' '+m['body'] for m in arr],normalize_embeddings=True,convert_to_numpy=True)
      else:
        vector=TfidfVectorizer(analyzer='char',ngram_range=(2,4),max_features=60000,sublinear_tf=True)
        mat=vector.fit_transform([m['title']+' '+m['body'] for m in arr])
      self._vec_cache[ns]=(arr,vector,mat)
    return self._vec_cache[ns]
 def recall(self,query,namespace='fixtures',seed_memories=(),top_k=8,mentioned=(),active=None):
    """Rank fusion across vector, shared tags, and 1-hop links. No proposed factual invention."""
    arr,vec,matrix=self._vector(namespace);by_id={m['id']:m for m in arr};ids=[m['id'] for m in arr]
    query_tags=set(tags_for(query))
    if self._e5:
      qvec=self._e5.encode(['query: '+query],normalize_embeddings=True,convert_to_numpy=True)[0]
      sims=matrix@qvec
    else:
      sims=(matrix@vec.transform([query]).T).toarray()[:,0]
    routes=defaultdict(dict);evidence=defaultdict(list)
    def add(route,sorted_pairs):
      for rank,(mid,score,why) in enumerate(sorted_pairs,1):
        routes[mid][route]=rank;evidence[mid].append(why)
    vector_hits=sorted(((ids[i],float(sims[i]),'vector cosine %.3f'%sims[i]) for i in range(len(ids)) if sims[i]>.001),key=lambda z:-z[1])[:12]
    add('vector',vector_hits)
    tag_hits=[]
    for m in arr:
      overlap=query_tags & set(m['tags'])
      if overlap:
        weight=sum(2.0 if x not in STOP_TAGS else 1.0 for x in overlap)
        tag_hits.append((m['id'],weight,'shared cue '+','.join(sorted(overlap))))
    add('tags',sorted(tag_hits,key=lambda x:-x[1])[:12])
    link_candidates={}
    for seed in seed_memories:
      if seed not in by_id:continue
      for e in self.neighbor_edges(seed,namespace):
        mid=e['target'];score=e['weight']
        if mid==seed:continue
        if mid not in link_candidates or link_candidates[mid][0]<score:
          link_candidates[mid]=(score,f'1-hop from {seed} ({e["kind"]}: {e["evidence"]})')
    add('links',[(k,v[0],v[1]) for k,v in sorted(link_candidates.items(),key=lambda z:-z[1][0])[:12]])
    candidates=[]
    for mid,ranks in routes.items():
      score=sum(1.0/(20+rank) for rank in ranks.values())
      if active:score+=min(.022,.018*active.get(mid,0))
      if mid in mentioned:score*=.25
      candidates.append({'id':mid,'title':by_id[mid]['title'],'authority':by_id[mid]['authority'],
                         'score':round(score,5),'routes':ranks,'reasons':evidence[mid],
                         'mentioned':mid in mentioned})
    return sorted(candidates,key=lambda x:(-x['score'],x['id']))[:top_k]
 def _default_state(self,ns):
    return {'namespace':ns,'event_seq':0,'activation':{},'mentioned':[],'thread':{'current_topic':None,
       'current_memory_id':None,'beat_index':0,'next_beat':None,'open_threads':[],'pending_association':None},
       'last_proposal':None,'last_clock':0,'last_recall':[],'last_event_ts':0}
 def state(self,sid,ns='fixtures'):
    r=self.con.execute('select * from sessions where session_id=?',(sid,)).fetchone()
    if r:
      s=jload(r['state_json'])
      if s['namespace']!=ns:raise ValueError('Session namespace mismatch')
      return s
    return self._default_state(ns)
 def _save(self,sid,s,action,payload):
    self.con.execute('insert or replace into sessions values(?,?,?,?)',(sid,s['namespace'],jdump(s),time.time()))
    self.con.execute('insert into audit(session_id,ts,action,payload) values(?,?,?,?)',(sid,time.time(),action,jdump(payload)))
    self.con.commit()
 def _update_activation(self,s, boosts):
    old={k:float(v) for k,v in s['activation'].items()};ns=s['namespace']
    new=defaultdict(float,{k:.77*v for k,v in old.items()})
    for k,v in boosts.items():
      if self.get(k) and self.get(k)['namespace']==ns:new[k]+=v
    # Exactly one hop, old snapshot only. No loops or runaway spread.
    for mid,v in old.items():
      for e in self.neighbor_edges(mid,ns):
        scale={'shared_tag':.11,'semantic':.09,'source_adjacent':.015}[e['kind']]
        new[e['target']]+=min(.11,scale*v*e['weight'])
    new={k:round(min(1.0,v),5) for k,v in new.items() if v>.035}
    s['activation']=dict(sorted(new.items(),key=lambda z:-z[1])[:8])
 def cue(self,sid,query,ns='fixtures',kind='recent_topic',event_id='manual',external_priority=False):
    s=self.state(sid,ns);s['event_seq']+=1
    active=sorted(s['activation'],key=s['activation'].get,reverse=True)[:2]
    matches=self.recall(query,ns,seed_memories=active,mentioned=s['mentioned'],active=s['activation'])
    boosts={m['id']:.58/(1+i*.7) for i,m in enumerate(matches[:3])}
    self._update_activation(s,boosts);s['last_recall']=matches
    s['last_event_ts']=time.time()
    if external_priority:s['thread']['pending_association']=None
    choice=self.decide(s,matches,kind,event_id,mode='cue')
    s['last_proposal']=choice
    self._save(sid,s,'cue',{'query':query,'trigger':kind,'recall':matches,'proposal':choice,'active':s['activation']})
    return {'proposal':choice,'recall':matches,'state':s}
 def decide(self,s,matches,kind,event_id,mode='cue'):
    thread=s['thread'];mid=thread['current_memory_id'];complete=True
    if mid:
      m=self.get(mid);complete=thread['beat_index']>=len(m['beats'])
    # Don't steal attention while an active thread has content to deliver.
    if mid and not complete:
      return {'decision':'wait','reason':'unfinished_thread','trigger':kind,'event_id':event_id,'memory_ids':[],'topic_hint':None}
    good=[c for c in matches if not c['mentioned'] and c['score']>=.023]
    if not good:
      return {'decision':'wait','reason':'insufficient_support','trigger':kind,'event_id':event_id,'memory_ids':[],'topic_hint':None}
    selected=good[0]
    # Recall cannot establish source truth. All supplied samples are NON CANON.
    decision='sandbox_propose' if selected['authority']=='synthetic_fixture' else 'reference_only'
    return {'decision':decision,'reason':'ranked_candidate','trigger':kind,'event_id':event_id,
            'memory_ids':[selected['id']],'topic_hint':selected['title'],'source_authority':selected['authority'],
            'expires_at_seq':s['event_seq']+5}
 def ack_playback(self,sid,memory_id,ns='fixtures',text=None):
    """Only explicit playback confirmation commits progress. NEVER update factual Memory."""
    s=self.state(sid,ns);m=self.get(memory_id)
    if not m or m['namespace']!=ns:raise ValueError('Unknown memory/namespace')
    s['event_seq']+=1;t=s['thread']
    if t['current_memory_id'] != memory_id:
      if t['current_memory_id'] and t['beat_index']<len(self.get(t['current_memory_id'])['beats']):
        t['open_threads'].append({'memory_id':t['current_memory_id'],'beat_index':t['beat_index'],'topic':t['current_topic']})
        t['open_threads']=t['open_threads'][-4:]
      t.update(current_topic=m['title'],current_memory_id=memory_id,beat_index=0)
    t['beat_index']=min(len(m['beats']),t['beat_index']+1)
    t['next_beat']=m['beats'][t['beat_index']] if t['beat_index']<len(m['beats']) else None
    if t['next_beat'] is None and memory_id not in s['mentioned']:s['mentioned'].append(memory_id)
    s['mentioned']=s['mentioned'][-30:]
    self._update_activation(s,{memory_id:.72})
    s['last_event_ts']=time.time();s['last_proposal']=None
    self._save(sid,s,'playback_ack',{'memory_id':memory_id,'beat_index':t['beat_index'],'text':text,
       'facts_verified':False,'note':'speech event does not authenticate claims'})
    return s
 def interrupt(self,sid,query,ns='fixtures'):
    s=self.state(sid,ns);s['thread']['pending_association']=None
    return self.cue(sid,query,ns,'external_event','interrupt',external_priority=True)
 def dmn_tick(self,sid,ns='fixtures',idle_for=20,tts_playing=False,generating=False,priority_comment=False):
    s=self.state(sid,ns)
    if idle_for<15 or tts_playing or generating or priority_comment:
      return {'decision':'wait','reason':'not_idle_or_busy','state':s}
    s['event_seq']+=1
    active=sorted(s['activation'],key=s['activation'].get,reverse=True)[:2]
    if not active:
      self._save(sid,s,'dmn_wait',{'reason':'no_active_memory'})
      return {'decision':'wait','reason':'no_active_memory','state':s}
    main=self.get(active[0]);related=self.recall(main['title'],ns,seed_memories=active,mentioned=s['mentioned'],active=s['activation'])
    # Idle task can prime a candidate, but cannot speak, force plan, or manufacture claims.
    next_cand=next((r for r in related if r['id'] not in active and not r['mentioned'] and r['score']>=.02),None)
    if next_cand:
      s['thread']['pending_association']={'memory_id':next_cand['id'],'relation_reason':next_cand['reasons'],
         'origin_event_seq':s['event_seq'],'expires_at_seq':s['event_seq']+5,'status':'WAIT'}
      self._update_activation(s,{next_cand['id']:.18})
    else:self._update_activation(s,{})
    self._save(sid,s,'dmn_tick',{'idle_seconds':idle_for,'candidate':next_cand,'autoplay':False})
    return {'decision':'wait','reason':'prepared_only','candidate':next_cand,'state':s}
 def resume_thread(self,sid,ns='fixtures'):
    s=self.state(sid,ns);lst=s['thread']['open_threads']
    if not lst:return s
    restored=lst.pop();s['event_seq']+=1
    s['thread'].update(current_memory_id=restored['memory_id'],current_topic=restored['topic'],beat_index=restored['beat_index'])
    m=self.get(restored['memory_id']);i=restored['beat_index']
    s['thread']['next_beat']=m['beats'][i] if i<len(m['beats']) else None
    self._save(sid,s,'thread_resume',{'memory_id':restored['memory_id']});return s
 def export_v5_contract(self,proposal,kind='recent_topic',event_id='manual',allow_sandbox=False):
    """Exact alpha_contract.py v0.1 shape. Unverified reference NEVER leaves as ZIP claim."""
    mid=(proposal.get('memory_ids') or [None])[0]
    m=self.get(mid) if mid else None
    can_emit=(m and (m['authority']=='verified' or (allow_sandbox and m['authority']=='synthetic_fixture')))
    return {'version':'alpha.v0.1','decision':'propose' if can_emit else 'wait',
        'trigger':{'kind':kind if kind in ('external_event','silence','recent_topic') else 'recent_topic','event_id':event_id},
        'memory_ids':[mid] if can_emit else [],'topic_hint':proposal.get('topic_hint') if can_emit else None}


def cli():
 p=argparse.ArgumentParser(description='ZIPちゃん Harness α sandbox — ①〜⑤')
 p.add_argument('--db',default=str(DB_DEFAULT));p.add_argument('--e5-model-dir',default=None,help='optional local E5 weights; no network fetch');sub=p.add_subparsers(dest='cmd',required=True)
 init=sub.add_parser('init');init.add_argument('--force',action='store_true')
 q=sub.add_parser('recall');q.add_argument('query');q.add_argument('--ns',choices=['fixtures','reference'],default='fixtures');q.add_argument('--seeds',nargs='*',default=[])
 cu=sub.add_parser('cue');cu.add_argument('query');cu.add_argument('--ns',default='fixtures');cu.add_argument('--sid',default='demo');cu.add_argument('--kind',default='recent_topic')
 a=sub.add_parser('ack');a.add_argument('memory_id');a.add_argument('--sid',default='demo');a.add_argument('--ns',default='fixtures')
 d=sub.add_parser('dmn');d.add_argument('--sid',default='demo');d.add_argument('--ns',default='fixtures');d.add_argument('--idle',type=float,default=20)
 st=sub.add_parser('state');st.add_argument('--sid',default='demo');st.add_argument('--ns',default='fixtures')
 rs=sub.add_parser('resume');rs.add_argument('--sid',default='demo');rs.add_argument('--ns',default='fixtures')
 demo=sub.add_parser('demo');demo.add_argument('--ns',default='fixtures');demo.add_argument('--sid',default='walkthrough')
 sub.add_parser('stats')
 args=p.parse_args();obj=Alpha(args.db,e5_model_dir=args.e5_model_dir)
 if args.cmd=='init':value=obj.populate(ROOT/'sources'/'v1_2.zip',ROOT/'sources'/'fixtures_20.json',args.force)
 elif args.cmd=='recall':value=obj.recall(args.query,args.ns,args.seeds)
 elif args.cmd=='cue':value=obj.cue(args.sid,args.query,args.ns,args.kind)
 elif args.cmd=='ack':value=obj.ack_playback(args.sid,args.memory_id,args.ns)
 elif args.cmd=='dmn':value=obj.dmn_tick(args.sid,args.ns,args.idle)
 elif args.cmd=='state':value=obj.state(args.sid,args.ns)
 elif args.cmd=='resume':value=obj.resume_thread(args.sid,args.ns)
 elif args.cmd=='stats':value=obj.stats()
 elif args.cmd=='demo':
   q='手袋 忘れ物' if args.ns=='fixtures' else 'ゲーム 探索';v=[]
   v.append({'label':'CUE','result':obj.cue(args.sid,q,args.ns)})
   mid=v[0]['result']['recall'][0]['id']
   for i in range(3):v.append({'label':'PLAYBACK_ACK '+str(i+1),'state':obj.ack_playback(args.sid,mid,args.ns)})
   v.append({'label':'DMN_IDLE','result':obj.dmn_tick(args.sid,args.ns,idle_for=20)})
   v.append({'label':'CUE_CONTINUE','result':obj.cue(args.sid,q,args.ns)})
   value=v
 print(json.dumps(value,ensure_ascii=False,indent=2))
 obj.close()
if __name__=='__main__':cli()
