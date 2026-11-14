"""One EMA server and one simulator worker per GPU, disjoint case shards."""
import argparse,json,os,subprocess,time,socket,signal
from pathlib import Path
from common import ROOT,sha256,write_json
from schema import ROOT as DATA

def main():
 p=argparse.ArgumentParser();p.add_argument('--variant',required=True,choices=list('ABCD'));p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--gpus',default='0,1,2,3,4,5,6,7');p.add_argument('--out',type=Path,required=True);p.add_argument('--smoke',action='store_true');p.add_argument('--port-base',type=int,default=18200);a=p.parse_args()
 assert (a.checkpoint/'params').is_dir();gpus=a.gpus.split(',');cases=[json.loads(l) for l in (DATA/'mini/cases.jsonl').read_text().splitlines()]
 if a.smoke:
  all_cases=cases
  cases=[next(c for c in cases if c['group']==g and (g!='normal_libero' or c['suite']=='libero_goal')) for g in ('new_training_scene','legacy_explicit_return','current_bowl_location','close_then_switch','direct_switch','normal_libero')]
  cases += [next(c for c in all_cases if c.get('task_label')==label and c.get('layout')==layout) for label,layout in [('E','P2'),('C','P3')]]
 gpus=gpus[:len(cases)];a.out.mkdir(parents=True,exist_ok=True);pid=__import__('evaluation_identity').protocol_id()
 identity=dict(variant=a.variant,checkpoint=str(a.checkpoint.resolve()),protocol_id=pid,case_ids=[c['case_id'] for c in cases],smoke=a.smoke)
 if (a.out/'identity.json').exists():assert json.loads((a.out/'identity.json').read_text())==identity
 else:write_json(a.out/'identity.json',identity)
 processes=[];workers=[];logs=[]
 def cleanup(*_):
  for p in processes:
   if p.poll() is None:p.terminate()
  for p in processes:
   try:p.wait(timeout=10)
   except subprocess.TimeoutExpired:p.kill();p.wait()
  for f in logs:f.close()
 signal.signal(signal.SIGTERM,lambda *x:(_ for _ in ()).throw(KeyboardInterrupt()))
 try:
  next_index=0;pending=[]
  while next_index<len(gpus) or pending:
   while next_index<len(gpus) and len(pending)<2:
    i=next_index;gpu=gpus[i];port=a.port_base+i;next_index+=1
    with socket.socket() as sock:sock.bind(('127.0.0.1',port))
    env={**os.environ,'CUDA_VISIBLE_DEVICES':gpu,'MEMORY_VARIANT':a.variant,'MUJOCO_EGL_DEVICE_ID':gpu,'XLA_PYTHON_CLIENT_MEM_FRACTION':'0.80','JAX_PLATFORMS':'cuda'}
    jobs=a.out/f'jobs_{i}.json';write_json(jobs,cases[i::len(gpus)])
    lf=(a.out/f'server_{i}.log').open('a');logs.append(lf)
    server=subprocess.Popen([os.environ['TRAIN_PYTHON'],str(ROOT/'src/serve.py'),'--checkpoint',str(a.checkpoint),'--port',str(port),'--protocol-id',pid],env=env,stdout=lf,stderr=subprocess.STDOUT);processes.append(server)
    item=(i,gpu,port,jobs,env,server);workers.append(item);pending.append((item,time.monotonic()+1200))
   for item,deadline in pending[:]:
    i,gpu,port,jobs,env,server=item
    if server.poll() is not None:raise RuntimeError(f'Server {i} exited; inspect server_{i}.log')
    if time.monotonic()>deadline:raise TimeoutError('Policy server startup')
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.1):pass
    except OSError:continue
    lf=(a.out/f'worker_{i}.log').open('a');logs.append(lf)
    cmd=[os.environ['SIM_PYTHON'],str(ROOT/'src/mini_runner.py'),'--variant',a.variant,'--port',str(port),'--jobs',str(jobs),'--out',str(a.out/'results')]
    if a.smoke:cmd+=['--smoke','--no-video']
    worker=subprocess.Popen(cmd,env=env,stdout=lf,stderr=subprocess.STDOUT);processes.append(worker);server._mini_worker=worker;pending.remove((item,deadline))
   for *_,server in workers:
    worker=getattr(server,'_mini_worker',None)
    if worker is not None and worker.poll() not in (None,0):raise RuntimeError('Evaluation worker failed during server startup')
   time.sleep(2)
  while True:
   done=True
   for *_,server in workers:
    worker=server._mini_worker
    if worker.poll() is None:done=False
    elif worker.returncode:raise RuntimeError('Evaluation worker failed; inspect worker logs')
   if done:break
   if any(s.poll() is not None for *_,s in workers):raise RuntimeError('Policy server stopped')
   time.sleep(5)
  rows=[json.loads((a.out/'results'/(c['case_id']+'.json')).read_text()) for c in cases]
  def stats(rs):return dict(total=len(rs),native_success=sum(x['native_success'] for x in rs),sgs=sum(x['sgs'] for x in rs),complete=sum(x['complete'] for x in rs),runtime_errors=sum(x['status']=='runtime_error' for x in rs),restore_required=sum(x['restore_required'] for x in rs),restore25=sum(x['restore25'] for x in rs),restore35=sum(x['restore35'] for x in rs),withdraw=sum(x['withdraw'] for x in rs),complete_rate=sum(x['complete'] for x in rs)/len(rs) if rs else None)
  summary=dict(identity=identity,**stats(rows),groups={g:stats([r for r in rows if r['group']==g]) for g in sorted({c['group'] for c in cases})})
  assert not summary['runtime_errors'];write_json(a.out/'summary.json',summary);write_json(a.out/'COMPLETED.json',dict(passed=True,smoke_only=a.smoke,case_count=len(rows)))
 finally:cleanup()
if __name__=='__main__':main()
