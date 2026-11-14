import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from continuation.serve import Service
class ServiceLifecycle(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();p=Path(self.tmp.name);(p/'spec.json').write_text('{}');self.s=Service(SimpleNamespace(out=p,spec=p/'spec.json',child_port=30001,port=20001));self.calls=[]
  def forward(path,body=None,method='GET',timeout=10):
   self.calls.append(path);return 202,json.dumps(dict(status='accepted',reset_count=1,task_version=8,episode_id='old')).encode(),'application/json'
  self.s.forward=forward
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def test_reset_retry_does_not_replace_child_twice(self):
  a={'request_id':'reset1','args':{'episode_id':'old','expected_task_version':7}}
  b={'args':{'expected_task_version':7,'episode_id':'old'},'request_id':'reset1'}
  self.assertEqual(self.s.reset(json.dumps(a).encode())[0],202)
  self.assertEqual(self.s.reset(json.dumps(b).encode())[0],202)
  self.assertEqual(self.calls,['/reset']);self.assertEqual(self.s.api_epoch,1);self.assertEqual(self.s.pending_spec['initial_version'],9)
 def test_reused_id_different_arguments_rejected(self):
  a={'request_id':'reset1','args':{'episode_id':'old','expected_task_version':7}};self.s.reset(json.dumps(a).encode());a['args']['expected_task_version']=8
  self.assertEqual(self.s.reset(json.dumps(a).encode())[0],409);self.assertEqual(len(self.calls),1)
 def test_loading_after_reset_exposes_no_old_current_task(self):
  self.s.last={'task_id':'oldTask','instruction':'put the bowl on the stove','state':'running','ready':True};self.s.resetting=True
  x=self.s.unavailable();self.assertFalse(x['ready']);self.assertIsNone(x['task_id']);self.assertEqual(x['instruction'],'')
 def test_reset_epoch_discards_old_images_and_receipts(self):
  del self.s.forward
  service=self.s
  class Response:
   status=200;headers={'Content-Type':'application/json'}
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self):service.api_epoch+=1;return b'{"ready":true,"episode_id":"old"}'
  self.s.opener=SimpleNamespace(open=lambda *a,**kw:Response())
  self.assertEqual(self.s.forward('/status')[0],503);self.assertIsNone(self.s.last)
  self.assertEqual(self.s.forward('/tool',b'{}','POST')[0],409)
if __name__=='__main__':unittest.main()
