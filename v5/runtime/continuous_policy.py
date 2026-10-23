from common import *
from runtime import *
SEED_CUE='手袋 忘れ物'
BROAD_CUE='買い物 メモ 忘れ物 駅 時計 傘 雨 公園 猫 本 図書館 ベランダ 植物 洗濯 台所 お茶 手紙 ノート 文房具 映画'
SID='continuous10'
def count_chars(text):return sum(not x.isspace() for x in text)
def signature(a):
 return {t:digest(json.dumps([list(r) for r in a.con.execute('SELECT * FROM '+t+' ORDER BY 1,2,3')],ensure_ascii=False)) for t in ('memories','links')}
def history(es):return [dict(text=x['text'],memory_id=x['memory_id'],origin='offline text delivered, semantically unverified') for x in es.recent()]
def choose(a,recent,eligible,index):
 queries=[('actual_generated_recent',recent),('broad_fallback',BROAD_CUE)] if recent else [('initial_seed',SEED_CUE),('broad_fallback',BROAD_CUE)]
 traces=[];seen=set(a.state(SID)['mentioned'])
 for kind,query in queries:
  c=a.cue(SID,query,event_id=f'choice-{index}-{kind}');p=c['proposal'];traces.append(dict(kind=kind,query=query,result=c))
  mids=p.get('memory_ids',[])
  if p['decision']=='sandbox_propose' and len(mids)==1 and mids[0] in eligible and mids[0] not in seen:
   m=a.get(mids[0]);assert m['authority']=='synthetic_fixture' and m['namespace']=='fixtures'
   return m,traces
 return None,traces

def observe_alpha(a,m,p,delivered):
 s=a.state(SID);s['event_seq']+=1
 n=sum(f['presentations'] for f in p.facts.values());pending=p.pending()
 s['thread'].update(current_memory_id=m['id'] if pending else None,current_topic=m['title'] if pending else None,beat_index=n if pending else 0,next_beat=None)
 if not pending and m['id'] not in s['mentioned']:s['mentioned'].append(m['id'])
 a._update_activation(s,{m['id']:.72} if delivered else {})
 a._save(SID,s,'offline_text_presentation_observation',dict(memory_id=m['id'],presented_fact_count=n,pending=pending,actual_tts=False,verified_coverage=False,source_fact_promotion=False))

def make_planner_request(m,recent,previous,progress):
 from context_runtime import planner_input
 from planner_policy import planner_prompt
 s=dict(id=m['id'],body=m['body']);i=planner_input(recent,[s],previous,s,'post_actual_offline_text_delivery')
 i['current_state'].update(progress=progress,unused_fact_ids=progress['pending_target_ids'],external_event=None,progress_warning='提示済み/模擬再生済みは意味確認済みではない。再提示せず未提示のFactから次の焦点を選ぶ。')
 return dict(prompt=planner_prompt(i),recent=i['recent'],candidate_ids=[m['id']]),dict(memory_id=m['id'],reason='actual_text_feedback',planner_input=i)

def relation(previous,m):
 shared=sorted((set(previous['tags'])&set(m['tags']))-{'昔','朝','夜','青','赤','白','黒'}) if previous else []
 summary='共通要素「'+'、'.join(shared)+'」を参考に別の経験へ移る。同日や因果にまとめない。' if shared else '別の話題へ移る。根拠のない共通経験や因果を作らない。' if previous else '同じ出来事の未提示の続き。'
 return shared,summary
