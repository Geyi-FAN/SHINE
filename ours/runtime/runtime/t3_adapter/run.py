"""T3: two owned GPU workers, shared audio lease, immutable per-round source."""
import argparse,copy,fcntl,hashlib,json,os,shutil,signal,socket,subprocess,sys,time,urllib.request
from pathlib import Path
B=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102');A=Path(__file__).resolve().parent
W=Path('/mnt/disk_2/geyi/t3_c3r_zh10_20261102');O=Path('/mnt/disk_4/geyi/t3_c3r_zh10_20261102')
OLD=Path('/mnt/disk_2/geyi/audio_t3_ZH_v2_eval_20261102');V=B/'freeze/voice'
PY='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python';NODE=str(V/'runtime/node-v22.23.3-linux-x64/bin/node')
SLOTS=[dict(gpu=1,policy=28800,gateway=28881,web=28887,voice=28889,child=38881),dict(gpu=2,policy=28801,gateway=28981,web=28987,voice=28989,child=38981)]
LEASE=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102/R9/parallel21/single_voice.lock')
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,d):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');t.replace(p)

def freeze(label):
 root=O/label;root.mkdir(parents=True,exist_ok=False);snap=W/'source_archives'/label/'t3_adapter';shutil.copytree(A,snap,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','reports'))
 files={}
 for src in [B/'run_data/FREEZE.json',OLD/'data/FREEZE.json']:
  for p,h in read(src)['files'].items():assert sha(p)==h,('parent changed',p);files[p]=h
 for directory in [snap,B/'native_prefetch',W/'policies',W/'receipt_audio']:
  for p in directory.rglob('*'):
   if p.is_file()and not p.is_symlink()and not any(x in p.parts for x in ['node_modules','__pycache__']):
    if p.suffix in ['.py','.mjs','.js','.json','.md']and not p.name.startswith(('POLIC','NUMERICAL','MODEL')):files[str(p)]=sha(p)
 for p in [W/'data/cases.private.json',W/'data/PROTOCOL.json',W/'data/network_route.json',W/'data/instruction_prompt.txt']:files[str(p)]=sha(p)
 put(root/'FREEZE.json',dict(time=time.time(),files=files,snapshot_adapter=str(snap),policy='one attempt per original ID; no source retries; no splicing rounds'))
 put(root/'REGISTERED.json',dict(time=time.time(),planned=10,case_ids=[c['case_id']for c in read(W/'data/cases.private.json')],environment_parallelism=2,audio_parallelism=1,slots=SLOTS,method='C3r recovery + R7-T3.2 + NativePrefetch + R8/T2-v3 + T3 guard repairs',source_snapshot=str(snap)))
 print('FROZEN',label,len(files),flush=True)

def check_freeze(root):
 drift=[p for p,h in read(root/'FREEZE.json')['files'].items()if not Path(p).exists()or sha(p)!=h];assert not drift,drift

def stop_owned(procs):
 for p in reversed(procs):
  if p.poll()is None:
   try:os.killpg(p.pid,signal.SIGTERM)
   except ProcessLookupError:pass
 for p in procs:
  try:p.wait(60)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(5)

def run_case(c,slot,root,engineering=False):
 check_freeze(root);out=root/'runs'/c['case_id'];out.mkdir(parents=True,exist_ok=False);fast=Path('/tmp/geyi_t3_c3r')/hashlib.sha256(str(out).encode()).hexdigest()[:20]
 for n in ['gateway','voice','review_history']:(fast/n).mkdir(parents=True,exist_ok=False);(out/n).symlink_to(fast/n,target_is_directory=True)
 fixture=next(x for x in read(OLD/'data/initial_states.json')if x['state_id']==c['scene_binding']['state_id'])
 spec=dict(c,fixture=fixture,run_scope=root.name,context_turns=[c['source_text']],serve_live=False,reset_count=1,initial_version=0,
           state_directory=str(fast/'gateway'),task_control_budget=1200,task_wall_budget=600,gateway_port=slot['gateway'],web_port=slot['web'],
           audio_manifest=str(OLD/'data/audio.json'),protocol=read(W/'data/PROTOCOL.json'),rules=read(OLD/'data/physical_rules.json'))
 put(out/'spec.json',spec);conf=read(V/'data/harness/config.json');conf.update(port=slot['voice'],backends=[]);put(fast/'voice/config.json',conf);(fast/'voice/config.json').chmod(0o600)
 env=dict(os.environ,C3R_PROFILE='recovery',VOICE_ROBOT_DATA_DIR=str(fast/'gateway'),VOICE_EVAL_RECORD_DIR=str(out/'recordings'),VOICE_DISCOVERY_FILE=str(fast/'voice/run/daemon.json'),
          VOICE_HISTORY_DIR=str(fast/'review_history'),VOICE_ROBOT_PORT=str(slot['gateway']),VOICE_WEB_PORT=str(slot['web']),VOICE_HARNESS_RUNTIME_CONFIG=str(V/'configs/runtime.local.json'),
          VOICE_NETWORK_ROUTE_FILE=str(W/'data/network_route.json'),HYBRID_POLICY_NAMESPACE='T3_C3R:'+root.name+':'+c['case_id'],PYTHONDONTWRITEBYTECODE='1',VOICE_PRIORITY_STOP='1',
          OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
 ve=dict(env,DASHSCOPE_API_KEY=(V/'private/dashscope.key').read_text().strip(),QWEN_LIVE_HARNESS_DATA_DIR=str(fast/'voice'),QWEN_LIVE_HARNESS_DISCOVERY_DIR=str(fast/'voice'),
         ROBOT_GATEWAY_URL=f'http://127.0.0.1:{slot["gateway"]}',ROBOT_GATEWAY_TOKEN_FILE=str(V/'private/robot.token'),ROBOT_AUDIO_BENCHMARK_HOST='1',ROBOT_BROWSER_HOST='1',
         ROBOT_FAST_STOP='1',ROBOT_AUDIO_RELISTEN='1',ROBOT_RECEIPT_AUDIO_DIR=str(W/'receipt_audio'),ROBOT_INSTRUCTION_PROMPT_FILE=str(W/'data/instruction_prompt.txt'),ROBOT_AUDIO_RECEIVE_LOG=str(out/'audio_received.jsonl'))
 processes=[];lease=None;error=None;started=time.time()
 def status():return json.load(urllib.request.urlopen(f'http://127.0.0.1:{slot["web"]}/api/status',timeout=4))
 try:
  for key in ['gateway','web','voice','child']:
   with socket.socket()as sock:assert sock.connect_ex(('127.0.0.1',slot[key]))!=0,('port busy',slot[key])
  route=read(W/'data/network_route.json');assert route['expires_at']>time.time()+120
  with (out/'services.log').open('w')as log:
   commands=[([NODE,str(A/'daemon/dist/index.js'),'--daemon-only'],ve),([PY,'-u',str(A/'service.py'),'--spec',str(out/'spec.json'),'--out',str(out),'--port',str(slot['gateway']),'--child-port',str(slot['child']),'--gpu',str(slot['gpu']),'--policy-port',str(slot['policy'])],env),([NODE,str(V/'web_host/server.mjs')],env)]
   for cmd,e in commands:processes.append(subprocess.Popen(cmd,cwd=V,env=e,stdout=log,stderr=log,start_new_session=True))
   for _ in range(240):
    if any(p.poll()is not None for p in processes):raise RuntimeError('private_service_startup_failed')
    try:
     ready=status()
     if ready.get('ready'):break
    except(OSError,ValueError):pass
    time.sleep(.5)
   else:raise TimeoutError('C3r readiness')
   assert ready['execution_kernel']=='C3r'and ready['c3r_profile']=='recovery'and ready['native_scheduler']=='prefetch-frame-aligned-v1'
   assert ready['t3_evaluation_adapter']=='ZH2C10-original-contract-v1';put(out/'readiness.json',ready)
   image=urllib.request.urlopen(f'http://127.0.0.1:{slot["web"]}/api/frame.jpg',timeout=4).read();(out/'initial.jpg').write_bytes(image)
   scene=read(out/'initial_scene.json');assert scene['maximum_channel_delta']<=2
   print('READY',c['case_id'],slot['gpu'],flush=True)
   lease=LEASE.open('r+b');fcntl.flock(lease,fcntl.LOCK_EX);lease.seek(0);last=float(lease.read().strip()or b'0');time.sleep(max(0.,30-(time.time()-last)))
   put(out/'AUDIO_LEASE.json',dict(time=time.time(),path=str(LEASE),audio_concurrency=1,environment_concurrency=2))
   if engineering:
    subprocess.run([NODE,str(B/'t1_adapter/connection_probe.mjs'),str(slot['web']),str(out)],env=env,stdout=log,stderr=log,check=True,timeout=60)
    assert status()['policy_action_steps']==0;put(out/'ENGINEERING_READY.json',dict(time=time.time(),no_task_audio=True))
   else:
    if(root/'CLOUD_BLOCK.json').exists():raise InterruptedError('cloud account blocked')
    p=subprocess.Popen([NODE,str(A/'client.mjs'),str(out/'spec.json'),str(out)],env=env,cwd=B,stdout=log,stderr=log,start_new_session=True);processes.append(p);p.wait(1900)
    if p.returncode:raise RuntimeError('audio client exit '+str(p.returncode))
 except BaseException as e:error=repr(e)
 finally:
  stop_owned(processes)
  if lease:
   lease.seek(0);lease.truncate();lease.write(str(time.time()).encode());lease.flush();fcntl.flock(lease,fcntl.LOCK_UN);lease.close()
  shutil.copytree(fast,out/'state_archive',dirs_exist_ok=True)
  for n in ['gateway','voice','review_history']:(out/n).unlink();(out/n).symlink_to(Path('state_archive')/n,target_is_directory=True)
  put(out/'PROCESS.json',dict(started=started,finished=time.time(),error=error,returncodes=[p.returncode for p in processes]))
 if engineering:
  assert(out/'ENGINEERING_READY.json').exists(),error
  put(out/'CASE_COMPLETE.json',dict(engineering=True,time=time.time()));return
 if not(out/'result.json').exists():put(out/'result.json',dict(case_id=c['case_id'],turns=[],messages=[],errors=[error],finished=dict(time=time.time())))
 subprocess.run([NODE,str(B/'repair/audit_audio.mjs'),str(out)],cwd=B,check=False)
 sys.path.insert(0,str(OLD));from acoustic_eval.score import evaluate
 v=evaluate(out,spec,spec['rules']);put(out/'CASE_COMPLETE.json',dict(time=time.time(),case_id=c['case_id'],metrics={k:v[k]for k in ['interaction','target','instruction']}))
 denied=any('Access denied'in f.read_text()or'good standing'in f.read_text()for f in(out/'voice/sessions').glob('*.jsonl'))
 if denied:put(root/'CLOUD_BLOCK.json',dict(case_id=c['case_id'],time=time.time()))
 print('SCORED',c['case_id'],{k:v[k]for k in ['interaction','target','instruction']},v.get('failures'),flush=True)

def report(root):
 rows=[]
 for c in read(W/'data/cases.private.json'):
  p=root/'runs'/c['case_id'];v=read(p/'verdict.json')if(p/'CASE_COMPLETE.json').exists()and(p/'verdict.json').exists()else{}
  rows.append(dict(case_id=c['case_id'],script_number=c['script_number'],**{k:v.get(k,'pending')for k in ['interaction','target','instruction']},failures=v.get('failures',[])))
 totals={k:dict(success=sum(x[k]=='pass'for x in rows),denominator=10)for k in ['interaction','target','instruction']}
 put(root/'SUMMARY.json',dict(time=time.time(),completed=sum(x['interaction']!='pending'for x in rows),planned=10,totals=totals,cases=rows));return rows,totals

def main():
 p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--freeze',action='store_true');p.add_argument('--worker',type=int);p.add_argument('--engineering',action='store_true');args=p.parse_args();root=O/args.label
 if args.freeze:freeze(args.label);return
 if args.worker is not None:
  cases=read(W/'data/cases.private.json');cases=cases[:2]if args.engineering else cases
  for c in cases[args.worker::2]:
   if(root/'CLOUD_BLOCK.json').exists():break
   run_case(c,SLOTS[args.worker],root,args.engineering)
  return
 snapshot=Path(read(root/'FREEZE.json')['snapshot_adapter']);logs=[];children=[]
 for w in [0,1]:
  log=(root/f'worker{w}.console.log').open('w');logs.append(log);cmd=[PY,'-u',str(snapshot/'run.py'),'--label',args.label,'--worker',str(w)]
  if args.engineering:cmd.append('--engineering')
  children.append(subprocess.Popen(cmd,stdout=log,stderr=log,cwd=B))
 while any(c.poll()is None for c in children):
  if not args.engineering:rows,totals=report(root);put(W/'PROGRESS.json',dict(label=args.label,completed=sum(x['interaction']!='pending'for x in rows),planned=10,totals=totals,time=time.time()))
  time.sleep(10)
 for f in logs:f.close()
 check_freeze(root);codes=[c.returncode for c in children]
 if args.engineering:completed=len(list((root/'runs').glob('*/ENGINEERING_READY.json')));planned=2
 else:rows,totals=report(root);completed=sum(x['interaction']!='pending'for x in rows);planned=10
 put(root/'COMPLETED.json',dict(finished=completed==planned and codes==[0,0],completed=completed,planned=planned,worker_exit_codes=codes,time=time.time()))
 assert completed==planned and codes==[0,0],('Incomplete',completed,codes)

if __name__=='__main__':main()
