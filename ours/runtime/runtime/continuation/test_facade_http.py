"""Exercise actual HTTP serialization, including evaluator's empty POST body."""
import json, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from types import SimpleNamespace
from continuation.service_r5 import Service, Server, Handler

class FacadeHTTP(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();p=Path(self.tmp.name);(p/'spec.json').write_text('{}')
  self.s=Service(SimpleNamespace(out=p,spec=p/'spec.json',child_port=30001,port=20001));self.calls=[]
  def forward(path,body=None,method='GET',timeout=10):
   self.calls.append((path,body,method));return 200,b'{"accepted":true}','application/json'
  self.s.forward=forward;self.http=Server(('127.0.0.1',0),Handler);self.http.service=self.s
  self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.http.shutdown();self.http.server_close();self.s.db.close();self.tmp.cleanup()
 def post(self,path):
  request=urllib.request.Request('http://127.0.0.1:'+str(self.http.server_port)+path,data=b'',headers={'Authorization':'Bearer '+self.s.token})
  return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=3)
 def test_evaluator_empty_post_is_forwarded(self):
  with self.post('/evaluator/hold')as r:self.assertEqual(r.status,200)
  self.assertEqual(self.calls,[('/evaluator/hold',b'','POST')])
 def test_production_never_exposes_private_evaluator(self):
  self.s.original['serve_live']=True
  with self.assertRaises(urllib.error.HTTPError)as error:self.post('/evaluator/hold')
  self.assertEqual(error.exception.code,404);self.assertFalse(self.calls)
if __name__=='__main__':unittest.main()
