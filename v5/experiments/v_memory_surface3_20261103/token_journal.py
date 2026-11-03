from common import *
class TokenJournal:
 def __init__(self,path,prompt_ids,decode,case_id):
  self.path=Path(path);self.prompt_ids=prompt_ids;self.case_id=case_id;self.ids=[];self.prompt_seen=False;self.flushed=0;self.started=time.perf_counter();self.stream=self.path.open('x',encoding='utf-8')
 def put(self,value):
  ids=value.tolist()
  if ids and isinstance(ids[0],list):ids=ids[0]
  if not self.prompt_seen:
   assert ids==self.prompt_ids;self.prompt_seen=True;return
  self.ids.extend(ids)
  if len(self.ids)-self.flushed>=16:self.flush()
 def flush(self):
  if len(self.ids)==self.flushed:return
  self.stream.write(json.dumps(dict(call_id=self.case_id,ids=self.ids[self.flushed:],total_tokens=len(self.ids),seconds=round(time.perf_counter()-self.started,3)))+'\n');self.stream.flush();self.flushed=len(self.ids)
 def end(self):self.flush()
 def close(self):self.flush();self.stream.close()

