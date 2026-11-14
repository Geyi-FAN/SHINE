"""Exercise frozen current pool HTTP handler with in-memory, zero-network IO."""
import importlib.util,io,json,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
B=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('frozen_pool',B/'freeze/deployment/fp8_pool.py');poolmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(poolmod)
class FakePool:
 key='unit-test-only';upstream_timeout=230
 def __init__(self):self.acquired=[];self.released=[];self.logs=[]
 def acquire(self,**kw):self.acquired.append(kw);return dict(id='fake-local',base='http://127.0.0.1:28174/v1',key='unit-test-only')
 def release(self,b):self.released.append(b)
 def record(self,r):self.logs.append(r)
class Response:
 status=200
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def read(self):return b'{"choices":[{"message":{"content":"test"}}]}'
class PoolTransport(unittest.TestCase):
 def setUp(self):
  self.pool=FakePool();cls=poolmod.handler(self.pool);self.handler=object.__new__(cls);self.handler.path='/v1/chat/completions';self.emits=[];self.handler.emit=lambda *a,**kw:self.emits.append(a)
  self.body=dict(model=poolmod.MODEL,messages=[dict(role='system',content='original prompt'),dict(role='user',content='user words')],temperature=0,response_format={'type':'json_object'})
 def prepare(self,body=None,role='planning'):
  self.raw=json.dumps(self.body if body is None else body).encode();self.handler.headers={'Authorization':'Bearer unit-test-only','Content-Length':str(len(self.raw)),'X-Agent-Role':role};self.handler.rfile=io.BytesIO(self.raw)
 def test_byte_identical_forwarding(self):
  self.prepare();seen=[]
  class Opener:
   def open(_,request,**kw):seen.append(request);return Response()
  with patch.object(poolmod.urllib.request,'build_opener',return_value=Opener()):self.handler.do_POST()
  self.assertEqual(len(seen),1);self.assertEqual(seen[0].data,self.raw);self.assertEqual(self.emits[0][1],Response().read());self.assertEqual(self.pool.acquired,[{'role':'planning'}]);self.assertEqual(self.pool.logs[0]['retries'],0)
 def test_single_failure_no_retry_or_cloud(self):
  self.prepare();seen=[]
  class Opener:
   def open(_,request,**kw):seen.append(request);raise urllib.error.URLError('injected failure')
  with patch.object(poolmod.urllib.request,'build_opener',return_value=Opener()):self.handler.do_POST()
  self.assertEqual(len(seen),1);self.assertEqual(self.emits[0][0],503);self.assertEqual(len(self.pool.released),1);self.assertEqual(self.pool.logs[0]['cloud_requests'],0)
 def test_wrong_model_rejected(self):
  self.prepare(dict(self.body,model='cloud-model'));self.handler.do_POST();self.assertEqual(self.emits[0][0],400);self.assertFalse(self.pool.acquired)
 def test_streaming_not_silently_changed(self):
  self.prepare(dict(self.body,stream=True));self.handler.do_POST();self.assertEqual(self.emits[0][0],400);self.assertFalse(self.pool.acquired)
 def test_bad_auth_no_upstream(self):
  self.prepare();self.handler.headers['Authorization']='wrong';self.handler.do_POST();self.assertEqual(self.emits[0][0],401);self.assertFalse(self.pool.acquired)
 def test_role_router_not_subgoal_author(self):
  for role in ['wording','planning','verifier','recovery']:
   with self.subTest(role=role):
    self.prepare(role=role)
    class Opener:
     def open(_,request,**kw):self.assertEqual(request.data,self.raw);return Response()
    with patch.object(poolmod.urllib.request,'build_opener',return_value=Opener()):self.handler.do_POST()
    self.assertEqual(self.pool.acquired[-1],{'role':role})
if __name__=='__main__':unittest.main(verbosity=2)
