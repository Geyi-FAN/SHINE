import sys,threading,time,types,unittest
from unittest.mock import patch
from types import SimpleNamespace
from repair6.waiting_prefetch import install
BASE=[];DIRECT=[]
def request_json(raw,context):BASE.append(raw);return dict(raw_user_message=raw,output=dict(execution_task=raw,semantic_changes=[]),attempts=[],seconds=0)
def normalize(planner,raw,context=None):return request_json(raw,context)
def direct(raw,context):DIRECT.append((raw,context));return dict(raw_user_message=raw,output=dict(execution_task=raw,semantic_changes=[]),attempts=[],seconds=0)
class State:
 def __init__(self):self.lock=threading.RLock();self.episode='e';self.task_id='old';self.instruction='put the bowl on the stove';self.deferred_task=None;self.actions=0
 def command(self,name,slot=None):
  if name=='schedule':self.deferred_task=slot
  if name=='cancel':self.deferred_task=None
  return {'accepted':True}
 def _run_deferred(self):
  if self.deferred_task:self.task_id='new';self.instruction=self.deferred_task['instruction'];self.deferred_task=None
class Prefetch(unittest.TestCase):
 def setUp(self):
  BASE.clear();DIRECT.clear();self.state=State();self.logs=[];self.bridge=SimpleNamespace(log=lambda kind,**kw:self.logs.append((kind,kw)),close=lambda:None)
  self.lang=SimpleNamespace(normalize=normalize,wording_errors=lambda raw,text:[])
  self.patch=patch.dict(sys.modules,task_language=self.lang,text_transport=SimpleNamespace(request_json=direct,connection=lambda role:({'model':'m','chat_url':'u'},'test')),instructions=SimpleNamespace(normalize_instruction=lambda raw,prev:(raw,'existing')));self.patch.start();self.cache=install(self.bridge,self.state)
 def tearDown(self):self.bridge.close();self.patch.stop()
 def schedule(self):self.state.command('schedule',dict(deferred_id='q1',instruction='put the cheese in the bowl'))
 def test_readonly_prefetch_does_not_start_task_and_reuses_only_consumed_slot(self):
  self.schedule();self.assertEqual(self.state.task_id,'old');self.assertEqual(self.state.actions,0);self.state._run_deferred();r=self.lang.normalize(None,'put the cheese in the bowl',{'ignored':'at runtime'});self.assertEqual(r['output']['execution_task'],'put the cheese in the bowl');self.assertEqual(len(DIRECT),1);self.assertFalse(BASE)
 def test_cancelled_queue_result_cannot_bind_to_new_task(self):
  self.schedule();self.state.command('cancel');self.state.task_id='unrelated';self.lang.normalize(None,'put the cheese in the bowl');self.assertEqual(BASE,['put the cheese in the bowl'])
if __name__=='__main__':unittest.main()
