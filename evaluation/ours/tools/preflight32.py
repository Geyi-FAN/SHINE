"""Prespecified development regression; never starts a formal cohort automatically."""
import concurrent.futures,fcntl,hashlib,json,os,signal,socket,subprocess,sys,threading,time,urllib.request
from pathlib import Path
N=Path(__file__).resolve().parents[1];B=N.parents[1];RUNTIME=os.environ.get('READINESS_RUNTIME_NAME','runtime');assert RUNTIME in('runtime','runtime_v2','runtime_v3','runtime_v4','runtime_v5','runtime_v6','runtime_v7','runtime_v8');W=N/'code'/RUNTIME;O=N.parent/'ours_final_c3r_20261110'
PLAN_FILE=os.environ.get('READINESS_PREFLIGHT_PLAN','PREFLIGHT32.json');assert PLAN_FILE in('PREFLIGHT32.json','PREFLIGHT8_FINAL.json');PLANNED=32 if PLAN_FILE=='PREFLIGHT32.json'else 8
SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
POLICY='/mnt/disk_1/geyi/audio_switch_asr_direct_pi05_20261108/python/bin/python3.11'
NODE='/mnt/disk_2/geyi/voice_pi05_harness/runtime/node-v22.23.3-linux-x64/bin/node'
TAG=os.environ.get('READINESS_PREFLIGHT_TAG','preflight32_v1')
assert TAG.replace('_','').isalnum(),'Invalid isolated run tag'
ROOT=N/'runs'/TAG;leases=[];models=[];logs=[];results=[];lock=threading.RLock();stopped=threading.Event()
sys.path.insert(0,str(N/'tools'))
from provider_failure import must_stop_dispatch
from service_identity import validate_policy,validate_provider
from legacy_scoring import score
def read(p):return json.loads(Path(p).read_text())
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');q.replace(p)
def fetch(port,path):
 op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with op.open('http://127.0.0.1:'+str(port)+path,timeout=5)as f:return json.load(f)
def verify():
 for name,digest in read(N/'SOURCE_LOCK.json')['files'].items():
  assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,'Frozen dependency changed: '+name
def acquire():
 while True:
  acquired=[]
  try:
   for lane in range(4):
    for p in[B/'deployments/our_T3_T1_T6_repair_20261109/locks'/f'realtime_lane{lane}.lock',O/'locks'/f'lane{lane}.lock',N/'locks'/f'lane{lane}.lock']:
     p.parent.mkdir(parents=True,exist_ok=True);f=p.open('ab');acquired.append(f);fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
   leases.extend(acquired);return
  except BlockingIOError:
   for f in acquired:f.close()
   save(N/'STATUS.json',dict(phase='waiting_public_voice_leases',time=time.time()));time.sleep(10)
def metadata(lane):
 m=fetch(28010+lane,'/metadata');g=read(N/'reports/GPU_MAP.json');c=read(W/'config/model.json')
 validate_policy(m,c['policy_actor_revision'],g['gpu_uuids'][lane]);assert m['complete_task_input_supported']is True;return m
def probe_policy_port(port):
 # Same reuse policy as ThreadingHTTPServer: a closed connection in TIME_WAIT
 # is not a live service. SO_REUSEPORT is deliberately never enabled.
 with socket.socket()as probe:
  probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
  probe.bind(('127.0.0.1',port))
def cleanup_models():
 # Stop every owned process before waiting, then reap. Never search/kill shared
 # actors by port or process name. Each object was spawned by this run.
 for process in models:
  if process.poll()is None:
   try:os.killpg(process.pid,signal.SIGTERM)
   except ProcessLookupError:pass
 for process in models:
  try:process.wait(timeout=10)
  except subprocess.TimeoutExpired:
   if process.poll()is None:
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass
   process.wait(timeout=5)
 for handle in logs+leases:handle.close()
def launch_models():
 lo,hi=map(int,Path('/proc/sys/net/ipv4/ip_local_port_range').read_text().split())
 for port in range(28010,28014):
  assert not lo<=port<=hi
  probe_policy_port(port)
 base=dict(os.environ,PYTHONPATH=str(W/'runtime')+':/mnt/disk_1/geyi/audio_switch_asr_direct_pi05_20261108/compat:/mnt/disk_2/geyi/openpi/.venv/lib/python3.11/site-packages',XLA_PYTHON_CLIENT_PREALLOCATE='false',XLA_PYTHON_CLIENT_MEM_FRACTION='.40',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
 for lane,gpu in enumerate(read(N/'reports/GPU_MAP.json')['gpu_uuids']):
  out=N/'services'/f'{TAG}_actor{lane}';out.mkdir(parents=True,exist_ok=False);f=(N/'logs'/f'{TAG}_policy{lane}.log').open('w');logs.append(f)
  models.append(subprocess.Popen([POLICY,'-B','-u',str(W/'runtime/unified/serve_policy.py'),'--port',str(28010+lane),'--out',str(out)],env=dict(base,CUDA_VISIBLE_DEVICES=gpu),stdout=f,stderr=f,start_new_session=True))
 pending=set(range(4));end=time.monotonic()+900;ready={}
 while pending and time.monotonic()<end:
  for lane in list(pending):
   if models[lane].poll()is not None:raise RuntimeError('candidate policy process exited: '+str(lane))
   try:ready[str(lane)]=metadata(lane);pending.remove(lane)
   except(OSError,ValueError):pass
  save(N/'STATUS.json',dict(phase='loading_candidate_policy',pending=sorted(pending),time=time.time()));time.sleep(2)
 assert not pending,'candidate policy loading timed out'
 save(N/'reports/POLICY_READY4.json',ready)
def progress():
 with lock:save(ROOT/'PROGRESS.json',dict(planned=PLANNED,completed=len(results),rows=results,stopped=stopped.is_set(),time=time.time(),formal_started=False))
def worker(lane,plan):
 for index,row in enumerate(plan):
  if index%4!=lane:continue
  if stopped.is_set()or(N/'STOP_AFTER_CURRENT').exists():break
  verify();metadata(lane);out=ROOT/row['case_id'];fd=leases[lane*3+2].fileno()
  with(ROOT/(row['case_id']+'.console.log')).open('w')as f:
   p=subprocess.run([SIM,'-B','-u',str(N/'tools/evaluate.py'),'--case-id',row['case_id'],'--lane',str(lane),'--index',str(row['original_index']),'--out',str(out),'--repetition','1','--lease-fd',str(fd)],stdout=f,stderr=f,pass_fds=(fd,))
  case=out/'cases'/row['case_id'];execution=read(case/'PREFLIGHT_OUTCOME.json')if(case/'PREFLIGHT_OUTCOME.json').exists()else{}
  scored=score(case,row['branch'])
  if row['branch']=='T3' and 'error'not in scored:
   from score_controlled import score as controlled_score
   scored=controlled_score(case)
  infra=bool(must_stop_dispatch(execution)or(p.returncode and not execution.get('audio_played'))or'error'in scored)
  r=dict(row,lane=lane,out=str(out),case_directory=str(case),execution=execution,scores=scored,returncode=p.returncode,infrastructure_error=infra,finished_at=time.time())
  save(out/'DISPATCH_RESULT.json',r)
  if infra:stopped.set();save(ROOT/'INFRASTRUCTURE_STOP.json',dict(case_id=row['case_id'],at=time.time(),outcome=execution,scoring=scored))
  with lock:results.append(r)
  progress();print(json.dumps(dict(done=len(results),case_id=row['case_id'],I=scored.get('interaction'),T=scored.get('target'),infra=infra)),flush=True)
def main():
 acquire();verify();ROOT.mkdir(parents=True,exist_ok=False)
 # Factual-review metadata only; no prompts/images/answers are given to this health check.
 health=fetch(18686,'/health');validate_provider(health);save(N/'reports/CLOUD04_HEALTH.json',health)
 keys=[(N/f'private/realtime_lane{i}.key').read_bytes().strip()for i in range(4)];assert len(set(keys))==4
 launch_models()
 with(N/'logs/realtime_probe.log').open('w')as f:subprocess.run([NODE,str(N/'tools/probe_realtime.mjs')],stdout=f,stderr=f,check=True)
 assert read(N/'reports/REALTIME_PROBE.json')['passed']==4,'speech service admission failed'
 plan=read(N/'plans'/PLAN_FILE)['rows'];assert len(plan)==PLANNED;save(ROOT/'RUN_PLAN.json',dict(rows=plan,runtime=read(W/'FREEZE.json'),engineering_only=True,physical_success_is_not_gate=True,unchanged_audio_triggers_deadlines=True))
 save(N/'STATUS.json',dict(phase='real_audio_action_preflight32',time=time.time(),formal_started=False));progress()
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:
  for f in[pool.submit(worker,i,plan)for i in range(4)]:f.result()
 save(ROOT/'COMPLETED.json',dict(completed=len(results),planned=PLANNED,stopped=stopped.is_set(),formal_started=False,at=time.time()))
 save(N/'STATUS.json',dict(phase='preflight_completed'if len(results)==PLANNED else'blocked_preflight',completed=len(results),planned=PLANNED,formal_started=False,at=time.time()))
if __name__=='__main__':
 try:main()
 except Exception as e:
  error=dict(type=type(e).__name__,reason=str(e)[:1500],at=time.time(),run=TAG,runtime=str(W))
  save(ROOT/'ERROR.json',error);save(N/'reports/PREFLIGHT_ERROR.json',error);raise
 finally:
  cleanup_models()
