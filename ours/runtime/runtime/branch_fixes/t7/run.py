"""T7: two owned GPU workers, shared audio lease, immutable per-round source."""
import argparse,copy,fcntl,hashlib,json,os,shutil,signal,socket,subprocess,sys,time,urllib.request
from pathlib import Path
B=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102');A=Path(__file__).resolve().parent
W=Path(os.environ['T7_LATENCY_WORK_ROOT']).resolve();O=W/'runs'
T08_ROUTE=json.loads((W/'PRIVATE_ROLE_ROUTE.json').read_text())
assert T08_ROUTE['model_url']=='http://127.0.0.1:18687/v1' and T08_ROUTE['same_model'] is True
os.environ['T7_LATENCY_MODEL_URL']=T08_ROUTE['model_url']
os.environ['T7_POOL_RUN_ROOT']=T08_ROUTE['pool_root']
OLD=W;V=B/'freeze/voice'
PY='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python';NODE=str(V/'runtime/node-v22.23.3-linux-x64/bin/node')
SLOTS=[dict(gpu=6,policy=29200,gateway=29281,web=29287,voice=29289,child=39281),dict(gpu=7,policy=29201,gateway=29381,web=29387,voice=29389,child=39381)]
from voice_account import VoiceAccount
ACCOUNT_CONFIG=Path(os.environ['T7_VOICE_ACCOUNT_CONFIG']).resolve()
ACCOUNT=VoiceAccount.load(ACCOUNT_CONFIG)
LEASE=ACCOUNT.lease_file
POLICIES=Path(os.environ['T7_POLICY_RUN_ROOT']).resolve()
DATA=Path(os.environ['T7_DATA_ROOT']).resolve()
POOL_ROOT=Path(os.environ['T7_POOL_RUN_ROOT']).resolve()
ROUTE=Path(os.environ.get('T7_NETWORK_ROUTE_FILE',str(DATA/'network_route_latency.json'))).resolve()
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,d):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');t.replace(p)

def freeze(label):
 root=O/label;root.mkdir(parents=True,exist_ok=False);snap=W/'source_archives'/label/'t7_adapter';shutil.copytree(A,snap,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','reports'))
 files={}
 for fixture in read(DATA/'initial_states.json'):
  for asset in fixture['assets'].values():
   assert sha(asset['path'])==asset['sha256'];files[asset['path']]=asset['sha256']
 for src in [B/'run_data/FREEZE.json']:
  for p,h in read(src)['files'].items():assert sha(p)==h,('parent changed',p);files[p]=h
 for directory in [snap,B/'native_prefetch',POLICIES,W/'receipt_audio']:
  for p in directory.rglob('*'):
   if p.is_file()and not p.is_symlink()and not any(x in p.parts for x in ['node_modules','__pycache__']):
    if p.suffix in ['.py','.mjs','.js','.json','.md','.wav','.txt']and not p.name.startswith(('POLIC','NUMERICAL','MODEL')):files[str(p)]=sha(p)
 for source in [W/'latency_pool.py',W/'routing_decision.py',W/'model_metrics.py',W/'routing_policy.json',W/'profiling/SUMMARY.json',W/'REPAIR_DESIGN.json',W/'EXPERIMENT_CHANGE_MANIFEST.json',W/'tests/CORE_HTTP_RETRY.json',W/'test_deferred_version_retry.mjs',W/'test_core_http_retry.py',W/'service_benchmark/SUMMARY.json',POOL_ROOT/'READY.json']:
  files[str(source)]=sha(source)
 for testfile in [W.parent/'tests/test_cancel_relisten.mjs',W.parent/'tests/test_cancel_proof.py',W.parent/'tests/RESULT.json']:
  files[str(testfile)]=sha(testfile)
 for item in [W.parent/'METHOD_FREEZE.json',W.parent/'API_ISOLATION.json',W/'AUDIO_CONDITION_MANIFEST.json',W/'PRIVATE_ROLE_ROUTE.json',W/'role_routing.py',W.parent/'tests/test_role_routing.py',W.parent/'tests/ROLE_ROUTING_TESTS.json',W.parent/'tests_v2/RESULT.json']:
  files[str(item)]=sha(item)
 
 for extra in [W.parent/'tests/test_cancel_clarification.py',W.parent/'tests/test_cancel_clarification.mjs',W.parent/'reports/TESTS.json']:files[str(extra)]=sha(extra)
 
 for extra in [W.parent/'tests/test_cancel_audible_v2.mjs',W.parent/'reports/TESTS_audible_v2.json']:files[str(extra)]=sha(extra)
 
 if os.environ.get('T7_DIAGNOSTIC_CONFIRM_AUDIO'):
  diagnostic=Path(os.environ['T7_DIAGNOSTIC_CONFIRM_AUDIO']);files[str(diagnostic)]=sha(diagnostic)
  wave=Path(read(diagnostic)['file']);files[str(wave)]=sha(wave)
  if read(diagnostic).get('negative_control'):
   negative=Path(read(diagnostic)['negative_control']['file']);files[str(negative)]=sha(negative)
 files[str(ACCOUNT_CONFIG)]=sha(ACCOUNT_CONFIG)
 for p in [DATA/'cases.private.json',DATA/'PROTOCOL.json',ROUTE,DATA/'instruction_prompt.txt',DATA/'audio.json',DATA/'physical_rules.json',DATA/'initial_states.json']:files[str(p)]=sha(p)

 for r in read(DATA/'audio.json'):files[r['file']]=sha(r['file'])
 data=root/'dataset';data.mkdir()
 for name in ['PROTOCOL.json','physical_rules.json','initial_states.json']:shutil.copyfile(DATA/name,data/name)
 put(data/'selected.private.json',read(DATA/'cases.private.json'))
 put(root/'FREEZE.json',dict(time=time.time(),files=files,snapshot_adapter=str(snap),policy='one attempt per original ID; no source retries; no splicing rounds'))
 put(root/'REGISTERED.json',dict(time=time.time(),planned=len(read(DATA/'cases.private.json')),case_ids=[c['case_id']for c in read(DATA/'cases.private.json')],environment_parallelism=2,audio_parallelism=1,slots=SLOTS,method='C3r recovery + R7-T3.2 + NativePrefetch + R8/T2-v3 + T3 guard repairs',source_snapshot=str(snap),network_route=str(ROUTE),private_model_url=os.environ['T7_LATENCY_MODEL_URL'],latency_revision='same observed-load routing + deferred-version-refresh-v2',speech_audio_and_physical_thresholds_unchanged=True))
 put(root/'VOICE_ACCOUNT.json',ACCOUNT.public_metadata())
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
 check_freeze(root)
 assert(POLICIES/'POLICIES_READY.json').exists(),'Owned models must be ready before simulator launch'
 out=root/'cases'/c['case_id'];out.mkdir(parents=True,exist_ok=False);fast=Path('/tmp/geyi_t7_c3r')/hashlib.sha256(str(out).encode()).hexdigest()[:20]
 for n in ['gateway','voice','review_history']:(fast/n).mkdir(parents=True,exist_ok=False);(out/n).symlink_to(fast/n,target_is_directory=True)
 fixture=next(x for x in read(OLD/'data/initial_states.json')if x['state_id']==c['scene_binding']['state_id'])
 spec=dict(case_id=c['case_id'],authored=c,fixture=fixture,source_task=c['private_contract']['predecessor_task_id'],target_task=999,preserve_bowl=False,phase=None,
           context_turns=[c['turns'][0]['text']],source_audio_setup=True,task_control_budget=1200,task_wall_budget=600,serve_live=False,reset_count=1,initial_version=0,
           state_directory=str(fast/'gateway'),gateway_port=slot['gateway'],web_port=slot['web'],dataset_dir=str(root/'dataset'),
           audio_manifest=str(DATA/'audio.json'),protocol=read(root/'dataset/PROTOCOL.json'),probe_policy=False,service_lifetime_s=8*3600)
 put(out/'spec.json',spec);conf=ACCOUNT.configure_providers(read(V/'data/harness/config.json'));conf.update(port=slot['voice'],backends=[]);put(fast/'voice/config.json',conf);(fast/'voice/config.json').chmod(0o600)
 put(out/'VOICE_ACCOUNT.json',ACCOUNT.public_metadata())
 env=dict(os.environ,C3R_PROFILE='recovery',VOICE_ROBOT_DATA_DIR=str(fast/'gateway'),VOICE_EVAL_RECORD_DIR=str(out/'recordings'),VOICE_DISCOVERY_FILE=str(fast/'voice/run/daemon.json'),
          VOICE_HISTORY_DIR=str(fast/'review_history'),VOICE_ROBOT_PORT=str(slot['gateway']),VOICE_WEB_PORT=str(slot['web']),VOICE_HARNESS_RUNTIME_CONFIG=str(V/'configs/runtime.local.json'),
          VOICE_NETWORK_ROUTE_FILE=str(ROUTE),HYBRID_POLICY_NAMESPACE='T7_C3R:'+root.name+':'+c['case_id'],PYTHONDONTWRITEBYTECODE='1',VOICE_PRIORITY_STOP='1',
          OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
 ve=dict(env,DASHSCOPE_API_KEY=ACCOUNT.credential(),QWEN_LIVE_HARNESS_DATA_DIR=str(fast/'voice'),QWEN_LIVE_HARNESS_DISCOVERY_DIR=str(fast/'voice'),
         ROBOT_GATEWAY_URL=f'http://127.0.0.1:{slot["gateway"]}',ROBOT_GATEWAY_TOKEN_FILE=str(V/'private/robot.token'),ROBOT_AUDIO_BENCHMARK_HOST='1',ROBOT_BROWSER_HOST='1',
         ROBOT_FAST_STOP='1',ROBOT_AUDIO_RELISTEN='1',ROBOT_RECEIPT_AUDIO_DIR=str(W/'receipt_audio'),ROBOT_INSTRUCTION_PROMPT_FILE=str(DATA/'instruction_prompt.txt'),ROBOT_AUDIO_RECEIVE_LOG=str(out/'audio_received.jsonl'),VOICE_AUDIO_FRAME_LOG=str(out/'audio_received.jsonl'))
 processes=[];lease=None;lease_acquired=False;error=None;started=time.time()
 def status():
  req=urllib.request.Request(f'http://127.0.0.1:{slot["gateway"]}/status',headers={'Authorization':'Bearer '+(V/'private/robot.token').read_text().strip()})
  return json.load(urllib.request.urlopen(req,timeout=4))
 try:
  for key in ['gateway','web','voice','child']:
   with socket.socket()as sock:assert sock.connect_ex(('127.0.0.1',slot[key]))!=0,('port busy',slot[key])
  route=read(ROUTE);assert route['expires_at']>time.time()+120
  with (out/'services.log').open('w')as log:
   commands=[([NODE,str(A/'daemon/dist/index.js'),'--daemon-only'],ve),([PY,'-u',str(A/'service.py'),'--spec',str(out/'spec.json'),'--out',str(out),'--port',str(slot['gateway']),'--child-port',str(slot['child']),'--gpu',str(slot['gpu']),'--policy-port',str(slot['policy'])],env)]
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
   assert ready['policy_metadata']['weights_sha256']=='30a620085ba28b8faec160ae68a9276d705ec0fb6d2fc9237e706379d0c5eebc'
   assert ready['policy_metadata']['normalization_sha256']=='d4e03a22ef5d89a910e32c233a509465ad0d265381a06745917d69fd8924a635'
   assert ready['t7_evaluation_adapter']=='Goal10-waiting-C3r-v10-evidence-latency';put(out/'readiness.json',ready)
   scene=read(out/'initial_scene.json');assert scene['maximum_channel_delta']<=2
   print('READY',c['case_id'],slot['gpu'],flush=True)
   lease=LEASE.open('r+b');fcntl.flock(lease,fcntl.LOCK_EX);lease_acquired=True;lease.seek(0);last=float(lease.read().strip()or b'0');time.sleep(max(0.,30-(time.time()-last)))
   current=status();assert current.get('ready')and current.get('state')=='idle'and not current.get('task_id'),'pre_audio_scene_unavailable_after_queue'
   assert read(ROUTE)['expires_at']>time.time()+120,'network_route_expired_while_queued; do not reuse stale addresses'
   put(out/'AUDIO_LEASE.json',dict(time=time.time(),path=str(LEASE),audio_concurrency=1,environment_concurrency=2))
   if engineering:
    subprocess.run([NODE,str(A/'connection_probe.mjs'),str(out/'spec.json'),str(out)],env=env,stdout=log,stderr=log,check=True,timeout=60)
    assert status()['policy_action_steps']==0;put(out/'ENGINEERING_READY.json',dict(time=time.time(),no_task_audio=True))
   else:
    if(root/'CLOUD_BLOCK.json').exists()or(root/'HALT.json').exists():raise InterruptedError('evaluation scheduling halted before test audio')
    p=subprocess.Popen([NODE,str(A/'client.mjs'),str(out/'spec.json'),str(out)],env=env,cwd=B,stdout=log,stderr=log,start_new_session=True);processes.append(p);p.wait(1900)
    if p.returncode:raise RuntimeError('audio client exit '+str(p.returncode))
 except BaseException as e:error=repr(e)
 finally:
  stop_owned(processes)
  if lease:
   if lease_acquired:
    lease.seek(0);lease.truncate();lease.write(str(time.time()).encode());lease.flush();fcntl.flock(lease,fcntl.LOCK_UN)
   lease.close()
  shutil.copytree(fast,out/'state_archive',dirs_exist_ok=True)
  for n in ['gateway','voice','review_history']:(out/n).unlink();(out/n).symlink_to(Path('state_archive')/n,target_is_directory=True)
  put(out/'PROCESS.json',dict(started=started,finished=time.time(),error=error,returncodes=[p.returncode for p in processes]))
 if engineering:
  assert(out/'ENGINEERING_READY.json').exists(),error
  put(out/'CASE_COMPLETE.json',dict(engineering=True,time=time.time()));return
 if not(out/'result.json').exists():put(out/'result.json',dict(case_id=c['case_id'],turns=[],messages=[],errors=[error],finished=dict(time=time.time())))
 subprocess.run([NODE,str(B/'repair/audit_audio.mjs'),str(out)],cwd=B,check=False)
 put(out/'RUN_FINISHED.json',dict(time=time.time(),case_id=c['case_id']))
 with(root/'score.lock').open('a+b')as scoring_lock:
  fcntl.flock(scoring_lock,fcntl.LOCK_EX);subprocess.run([PY,str(A/'score_one.py'),'--root',str(root)],check=True,cwd=A)
 v=read(out/'verdict.json');put(out/'CASE_COMPLETE.json',dict(time=time.time(),case_id=c['case_id'],metrics={k:v[k]for k in ['interaction45','target','instruction']}))
 denied=any('Access denied'in f.read_text()or'good standing'in f.read_text()for f in(out/'voice/sessions').glob('*.jsonl'))
 if denied:put(root/'CLOUD_BLOCK.json',dict(case_id=c['case_id'],time=time.time()))
 print('SCORED',c['case_id'],{k:v[k]for k in ['interaction45','target','instruction']},v.get('failures'),flush=True)

def report(root):
 rows=[]
 for c in read(DATA/'cases.private.json'):
  p=root/'cases'/c['case_id'];v=read(p/'verdict.json')if(p/'CASE_COMPLETE.json').exists()and(p/'verdict.json').exists()else{}
  rows.append(dict(case_id=c['case_id'],script_number=c['script_id'],**{k:v.get(k,'pending')for k in ['interaction45','target','instruction']},failures=v.get('failures',[])))
 totals={k:dict(success=sum(x[k]=='pass'for x in rows),denominator=len(read(DATA/'cases.private.json')))for k in ['interaction45','target','instruction']}
 put(root/'SUMMARY.json',dict(time=time.time(),completed=sum(x['interaction45']!='pending'for x in rows),planned=len(read(DATA/'cases.private.json')),totals=totals,cases=rows));return rows,totals

def main():
 p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--freeze',action='store_true');p.add_argument('--worker',type=int);p.add_argument('--engineering',action='store_true');args=p.parse_args();root=O/args.label
 if args.freeze:freeze(args.label);return
 if args.worker is not None:
  cases=read(DATA/'cases.private.json');cases=cases[:1]if args.engineering else cases
  for c in cases[args.worker::len(SLOTS)]:
   if(root/'CLOUD_BLOCK.json').exists()or(root/'HALT.json').exists():break
   run_case(c,SLOTS[args.worker],root,args.engineering)
  return
 snapshot=Path(read(root/'FREEZE.json')['snapshot_adapter']);logs=[];children=[]
 for w in range(len(SLOTS)):
  log=(root/f'worker{w}.console.log').open('w');logs.append(log);cmd=[PY,'-u',str(snapshot/'run.py'),'--label',args.label,'--worker',str(w)]
  if args.engineering:cmd.append('--engineering')
  children.append(subprocess.Popen(cmd,stdout=log,stderr=log,cwd=B))
 while any(c.poll()is None for c in children):
  if not args.engineering:rows,totals=report(root);put(W/'PROGRESS.json',dict(label=args.label,completed=sum(x['interaction45']!='pending'for x in rows),planned=len(read(DATA/'cases.private.json')),totals=totals,time=time.time()))
  time.sleep(10)
 for f in logs:f.close()
 check_freeze(root);codes=[c.returncode for c in children]
 if args.engineering:completed=len(list((root/'cases').glob('*/ENGINEERING_READY.json')));planned=1
 else:rows,totals=report(root);completed=sum(x['interaction45']!='pending'for x in rows);planned=len(read(DATA/'cases.private.json'))
 put(root/'COMPLETED.json',dict(finished=completed==planned and codes==[0,0],completed=completed,planned=planned,worker_exit_codes=codes,time=time.time()))
 assert completed==planned and codes==[0,0],('Incomplete',completed,codes)

if __name__=='__main__':main()
