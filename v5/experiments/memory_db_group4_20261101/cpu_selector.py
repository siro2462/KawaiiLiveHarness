from common import *
sys.path.insert(0,str(OUT/'reference'))
from v5.memory_db.selector_adapter import select_episode
from v5.memory_db.projection import project_episode

def select(sample,seed=17):
 assert seed==17
 snapshot=read(OUT/'reference/validation_snapshot.json')
 projected=project_episode(snapshot,sample['revision']['revision_id'])
 assert projected==sample['db_sample']
 plan=select_episode(projected,backend='rhythm')
 return json.loads(json.dumps(plan,ensure_ascii=False))
