"""Persistent HTTP facade, exactly one owned simulator child per episode.

Only explicit operator reset replaces the child. Audio reconnect, QA, pause and
new tasks preserve it. This process never calls env.step or generates actions.
"""
import argparse,hashlib,hmac,json,os,signal,socket,sqlite3,subprocess,threading,time,urllib.request,urllib.error
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
B=Path(__file__).resolve().parents[1]
class Service:
 def __init__(self,args):
  self.args=args;self.out=args.out;self.out.mkdir(parents=True,exist_ok=True);self.original=json.loads(args.spec.read_text());self.token=(B/'freeze/voice/private/robot.token').read_text().strip()
  self.lock=threading.RLock();self.changed=threading.Event();self.stop=threading.Event();self.resetting=False;self.generation=0;self.api_epoch=0;self.proc=None;self.last=None;self.logfile=None
  self.pending_spec=dict(self.original);self.pending_spec.setdefault('reset_count',1)
  self.child_port=args.child_port or args.port+10000
  self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  self.db=sqlite3.connect(self.out/'reset_receipts.sqlite',check_same_thread=False);self.db.execute('CREATE TABLE IF NOT EXISTS resets(id TEXT PRIMARY KEY,digest TEXT,result TEXT)');self.db.commit()
 def log(self,kind,**fields):
  with(self.out/'supervisor.jsonl').open('a')as f:f.write(json.dumps(dict(time=time.time(),kind=kind,generation=self.generation,api_epoch=self.api_epoch,**fields),ensure_ascii=False)+'\n')
 def start_child(self):
  with socket.socket()as s:
   if s.connect_ex(('127.0.0.1',self.child_port))==0:raise RuntimeError('child_port_already_owned_by_another_process')
  directory=self.out if self.generation==0 else self.out/'episodes'/('generation_%05d'%self.generation);directory.mkdir(parents=True,exist_ok=True)
  spec=dict(self.pending_spec,process_generation=self.generation);path=directory/'live_spec.json';path.write_text(json.dumps(spec,indent=2,ensure_ascii=False));self.logfile=(directory/'child.console.log').open('a')
  env=dict(os.environ,VOICE_PRIORITY_STOP='1',PYTHONDONTWRITEBYTECODE='1',HYBRID_POLICY_NAMESPACE='F28D_LIVE:'+str(self.out)+':'+str(self.generation))
  command=[self.args.python,'-u',str(B/'continuation/live_gateway.py'),'--spec',str(path),'--out',str(directory),'--port',str(self.child_port),'--gpu',str(self.args.gpu),'--policy-port',str(self.args.policy_port)]
  self.proc=subprocess.Popen(command,env=env,stdout=self.logfile,stderr=self.logfile,start_new_session=True);self.log('simulator_child_started',pid=self.proc.pid,directory=str(directory),reset_count=spec['reset_count'])
 def stop_child(self):
  p=self.proc
  if p and p.poll()is None:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(12)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(5)
  if self.logfile:self.logfile.close();self.logfile=None
 def forward(self,path,body=None,method='GET',timeout=10):
  epoch=self.api_epoch
  req=urllib.request.Request('http://127.0.0.1:'+str(self.child_port)+path,data=body,method=method,headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
  try:
   with self.opener.open(req,timeout=timeout)as r:data=r.read();status=r.status;mime=r.headers.get('Content-Type','application/json')
  except urllib.error.HTTPError as e:status=e.code;data=e.read();mime=e.headers.get('Content-Type','application/json')
  if epoch!=self.api_epoch:return (409 if method!='GET'else 503),json.dumps(dict(error='stale_service_generation_response',executed=None if method!='GET'else False,retry='read current status; do not replay old mutation')).encode(),'application/json'
  if path=='/status'and status==200:
   state=json.loads(data);state['service_generation']=self.generation;state['execution_service']='f28d_async_single_owner';state['execution_service_revision']='R5';self.last=state;data=json.dumps(state).encode()
  return status,data,mime
 def unavailable(self):
  state=dict(self.last or{});state.update(ready=False,state='resetting'if self.resetting else'loading'if self.proc and self.proc.poll()is None else'needs_review',service_generation=self.generation,execution_service='f28d_async_single_owner')
  if self.resetting:state.update(task_id=None,instruction='',task=None,scene_memory={'state':'awaiting_episode_initialization'})
  state['failure_detail']=dict(code='reset_initialization'if self.resetting else'execution_child_unavailable',detail='仿真与视觉记忆正在初始化；本次请求未下发。'if self.resetting else'执行器暂不可用；未自动重放旧任务。')
  return state
 def reset(self,raw):
  body=json.loads(raw);rid=body.get('request_id');digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  if not isinstance(rid,str)or not rid:return 400,json.dumps({'error':'request_id required'}).encode(),'application/json'
  with self.lock:
   prior=self.db.execute('SELECT digest,result FROM resets WHERE id=?',(rid,)).fetchone()
   if prior:
    if not hmac.compare_digest(prior[0],digest):return 409,b'{"error":"request_id_reused_with_different_arguments"}','application/json'
    return 202,prior[1].encode(),'application/json'
   if self.resetting:return 409,b'{"error":"reset_already_pending","executed":false}','application/json'
   status,data,mime=self.forward('/reset',raw,'POST')
   if status!=202:return status,data,mime
   receipt=json.loads(data);self.db.execute('INSERT INTO resets VALUES(?,?,?)',(rid,digest,data.decode()));self.db.commit();self.resetting=True;self.api_epoch+=1
   self.pending_spec=dict(self.original,reset_count=receipt.get('reset_count',1)+1,initial_version=receipt.get('task_version',0)+1,previous_episode_id=receipt.get('episode_id'))
   self.changed.set();self.log('operator_reset_accepted',request_id=rid,previous_episode_id=receipt.get('episode_id'));return status,data,mime
 def run(self):
  self.start_child()
  while not self.stop.wait(.1):
   if self.changed.is_set():
    self.changed.clear();self.stop_child();self.generation+=1;self.start_child()
   if self.resetting and not self.changed.is_set()and self.proc and self.proc.poll()is None:
    try:
     status,data,_=self.forward('/status',timeout=1)
     if status==200 and json.loads(data).get('ready'):self.resetting=False;self.log('reset_ready_new_episode')
    except(OSError,ValueError,TimeoutError):pass
  self.stop_child()
class Server(ThreadingHTTPServer):request_queue_size=128;daemon_threads=True
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*args):pass
 def respond(self,status,data,mime='application/json'):
  self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
 def handle_request(self):
  service=self.server.service
  if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+service.token):return self.respond(401,b'{"error":"authentication_required"}')
  raw=None
  if self.command=='POST':
   size=int(self.headers.get('Content-Length','0'))
   if not 0<=size<=16384:return self.respond(400,b'{"error":"invalid_request_size"}')
   raw=self.rfile.read(size)
  try:
   if service.original.get('serve_live') and self.path.split('?',1)[0].startswith('/evaluator/'):
    reply=(404,b'{"error":"not_found"}','application/json')
   elif self.command=='POST'and self.path=='/reset':reply=service.reset(raw)
   elif service.resetting:
    reply=(200,json.dumps(service.unavailable()).encode(),'application/json')if self.path=='/status'else(503,b'{"error":"reset_initialization_no_dispatch","executed":false}','application/json')
   else:reply=service.forward(self.path,raw,self.command)
  except (OSError,ValueError,TimeoutError):
   reply=(200,json.dumps(service.unavailable()).encode(),'application/json')if self.path=='/status'else(503,b'{"error":"execution_child_unavailable_no_automatic_retry","executed":false}','application/json')
  self.respond(*reply)
 do_GET=handle_request
 do_POST=handle_request

def main():
 p=argparse.ArgumentParser();p.add_argument('--spec',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--port',type=int,default=8801);p.add_argument('--child-port',type=int);p.add_argument('--gpu',type=int,default=5);p.add_argument('--policy-port',type=int,default=19867);p.add_argument('--python',default='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python');a=p.parse_args();service=Service(a);server=Server(('127.0.0.1',a.port),Handler);server.service=service
 signal.signal(signal.SIGTERM,lambda *_:service.stop.set());signal.signal(signal.SIGINT,lambda *_:service.stop.set());signal.signal(signal.SIGHUP,lambda *_:service.stop.set());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:service.run()
 finally:server.shutdown();server.server_close();service.db.close()
if __name__=='__main__':main()
