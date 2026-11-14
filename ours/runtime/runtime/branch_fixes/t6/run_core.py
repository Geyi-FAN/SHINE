"""G22 private T6 lifecycle: real setup, independent gate, real audio, no re-answer."""
import fcntl,argparse,concurrent.futures,copy,hashlib,json,os,shutil,signal,socket,sqlite3,subprocess,threading,time,urllib.request,uuid
from pathlib import Path

BASE=Path('/mnt/disk_2/geyi/t6_c3r_20_20261103');ROOT=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102');ADAPTER=Path(__file__).resolve().parent;VOICE=ROOT/'freeze/voice'
NODE='/mnt/disk_2/geyi/voice_pi05_harness/runtime/node/bin/node'
SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
OUT=Path('/mnt/disk_4/geyi/t6_c3r_20_20261103')
LEASE=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102/R9/parallel21/single_voice.lock')
TASKS={0:'Open the middle drawer of the cabinet.',1:'Put the bowl on the stove.',2:'Put the wine bottle on top of the cabinet.',3:'Open the top drawer and put the bowl inside.',4:'Put the bowl on top of the cabinet.',6:'Put the cream cheese in the bowl.',7:'Turn on the stove.',8:'Put the bowl on the plate.',9:'Put the wine bottle on the rack.'}
LOCK=threading.Lock();HALT=threading.Event()
VOICE_SLOT=threading.Semaphore(1)

def account_denial(folder):
 p=Path(folder)/'client/events.jsonl'
 if p.exists():
  for line in p.read_text().splitlines():
   event=json.loads(line)
   if event.get('type')!='host.state':continue
   message=str(event.get('status',{}).get('message','')).lower()
   if '1007' in message and 'access denied' in message:return dict(code='realtime_1007_access_denied',source=str(p))
 for p in (Path(folder)/'voice/sessions').glob('*.jsonl'):
  for line in p.read_text().splitlines():
   event=json.loads(line);payload=event.get('payload',{})
   if event.get('type')=='error' and isinstance(payload,dict) and (payload.get('code')=='Arrearage' or 'access denied, please make sure your account' in str(payload.get('message','')).lower()):return dict(code='provider_account_denial',source=str(p))
 return None


def save(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)


class Runtime:
 def __init__(self,folder,case,worker):
  self.folder=Path(folder);self.case=case;self.worker=worker;self.processes=[];self.robot=29081+worker*100;self.web=self.robot+1;self.voice=self.robot+2
  self.token=(VOICE/'private/robot.token').read_text().strip()
 def req(self,path,body=None,timeout=10):
  request=urllib.request.Request('http://127.0.0.1:%d'%self.robot+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
  with urllib.request.urlopen(request,timeout=timeout) as r:return json.load(r)
 def status(self):return self.req('/status')
 def inspect(self):return self.req('/eval/t6',{'op':'inspect'})
 def tool(self,name,instruction=None):
  s=self.status();args=dict(episode_id=s['episode_id'],expected_task_version=s['task_version'])
  if instruction is not None:args['instruction']=instruction
  return self.req('/tool',dict(name=name,args=args,request_id='t6-setup-'+uuid.uuid4().hex))
 def start(self):
  f=self.folder;f.mkdir(parents=True,exist_ok=True)
  for port in [self.robot,self.web,self.voice]:
   with socket.socket() as s:assert s.connect_ex(('127.0.0.1',port))!=0,'Isolated port occupied'
  fixture=json.loads(Path('/mnt/disk_2/geyi/T6_dataset/scenes/LIVE8787_I00/fixture.json').read_text())
  prep=self.case['preparation'];source=prep[0] if prep and isinstance(prep[0],int) else 0
  card=next(c for c in json.loads((BASE/'data/scene_cards.private.json').read_text()) if c['scene_card_id']==self.case['scene_card_id'])
  spec=dict(case_id=self.case['case_id'],fixture=fixture,source_task=source,target_task=self.case['active_task_id'],context_turns=['reference preparation'] if prep else[],t6_card=card,setup_non_native=bool(prep and prep[0]=='open_top'),task_control_budget=1200)
  save(f/'spec.private.json',spec)
  v=f/'voice';v.mkdir(mode=0o700)
  config=json.loads((VOICE/'data/harness/config.json').read_text());config.update(port=self.voice,backends=[]);save(v/'config.json',config);os.chmod(v/'config.json',0o600)
  db=Path('/tmp/t6_c3r20_20261103')/hashlib.sha256(str(f).encode()).hexdigest()[:20]/'gateway';db.mkdir(parents=True,exist_ok=True);self.db=db
  env=dict(os.environ,VOICE_ROBOT_DATA_DIR=str(db),T6_DB_DIRECTORY=str(db),VOICE_EVAL_RECORD_DIR=str(f/'recordings'),VOICE_DISCOVERY_FILE=str(v/'run/daemon.json'),VOICE_HISTORY_DIR=str(f/'review_history'),VOICE_ROBOT_PORT=str(self.robot),VOICE_WEB_PORT=str(self.web),VOICE_T6_QA_AUDIT=str(f/'qa_input_audit.jsonl'),VOICE_AUDIO_FRAME_LOG=str(f/'audio_received.jsonl'),VOICE_HARNESS_RUNTIME_CONFIG=str(VOICE/'configs/runtime.local.json'),ROBOT_T6_BOUNDED_SPEECH='1',C3R_PROFILE='recovery',VOICE_NETWORK_ROUTE_FILE=str(BASE/'data/network_route.json'),HYBRID_POLICY_NAMESPACE='T6_C3R:'+str(f),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
  ve=dict(env,DASHSCOPE_API_KEY=(VOICE/'private/dashscope.key').read_text().strip(),QWEN_LIVE_HARNESS_DATA_DIR=str(v),QWEN_LIVE_HARNESS_DISCOVERY_DIR=str(v),ROBOT_GATEWAY_URL='http://127.0.0.1:%d'%self.robot,ROBOT_GATEWAY_TOKEN_FILE=str(VOICE/'private/robot.token'),ROBOT_AUDIO_BENCHMARK_HOST='1',ROBOT_BROWSER_HOST='1',ROBOT_RECEIPT_AUDIO_DIR=str(BASE/'receipt_audio'),ROBOT_INSTRUCTION_PROMPT_FILE=str(BASE/'data/instruction_prompt.txt'))
  self.log=(f/'services.log').open('w')
  commands=[([NODE,str(ADAPTER/'daemon/dist/index.js'),'--daemon-only'],ve),([SIM,'-u',str(ADAPTER/'gateway.py'),'--spec',str(f/'spec.private.json'),'--out',str(f),'--port',str(self.robot),'--gpu',str(1+self.worker),'--policy-port',str(29000+self.worker)],env),([NODE,str(ADAPTER/'web_host/server.mjs')],env)]
  for cmd,e in commands:self.processes.append(subprocess.Popen(cmd,cwd=ROOT,env=e,stdout=self.log,stderr=self.log,start_new_session=True))
  save(f/'processes.json',dict(pids=[p.pid for p in self.processes],ports=[self.robot,self.web,self.voice],temporary_database=str(db),execution_core='C3r_recovery_T6_MV20_v1'))
  began=time.monotonic()
  while time.monotonic()-began<150:
   if any(p.poll() is not None for p in self.processes):raise RuntimeError('Service exited: see services.log')
   try:
    s=self.status()
    if s.get('ready') and (v/'run/daemon.json').exists():break
   except (OSError,ValueError):pass
   time.sleep(.25)
  else:raise TimeoutError('isolated service readiness')
  assert s.get('execution_kernel')=='C3r' and s.get('c3r_profile')=='recovery' and s.get('native_scheduler')=='prefetch-frame-aligned-v1'
  save(f/'readiness.json',s)
  self.env=env
  return self
 def connect_voice(self):
  f=self.folder;began=time.monotonic();self.voice_lease=LEASE.open('r+b');fcntl.flock(self.voice_lease,fcntl.LOCK_EX);self.voice_slot_acquired=True
  self.voice_lease.seek(0);last=float(self.voice_lease.read().strip()or b'0');time.sleep(max(0.,30-(time.time()-last)))
  if HALT.is_set():raise RuntimeError('global_voice_admission_stopped')
  save(f/'voice_slot.json',dict(wait_seconds=time.monotonic()-began,max_our_active_voice_sessions=1,acquired=time.time()))
  audio=next(a for a in json.loads((BASE/'data/PCM_MANIFEST.json').read_text()) if a['utterance_id']==self.case['question_utterance_id'])
  cfg=dict(out=str(f),case_id=self.case['case_id'],pcm_file=audio['file'],audio_sha256=audio['source_sha256'],browser_token_file=str(VOICE/'private/browser.token'),robot_token_file=str(VOICE/'private/robot.token'),web_url='http://127.0.0.1:%d'%self.web,robot_url='http://127.0.0.1:%d'%self.robot)
  save(f/'client_config.private.json',cfg)
  self.client=subprocess.Popen([NODE,str(ADAPTER/'scripts/audio_switch_benchmark/run_one_cli.mjs'),str(f/'client_config.private.json')],cwd=BASE,env=self.env,stdout=self.log,stderr=self.log,start_new_session=True);self.processes.append(self.client)
  began=time.monotonic()
  while not (f/'VOICE_READY.json').exists() and time.monotonic()-began<55:
   if self.client.poll() is not None:raise RuntimeError('Voice client exited before readiness')
   time.sleep(.1)
  if not (f/'VOICE_READY.json').exists():raise TimeoutError('real voice readiness')
 def wait(self,predicate,seconds,label):
  began=time.monotonic()
  while time.monotonic()-began<seconds:
   p=self.inspect()
   if predicate(p):return p
   time.sleep(.08)
  raise TimeoutError(label)
 def setup(self):
  prep=self.case['preparation']
  if prep:
   task=prep[0]
   text=TASKS[task] if isinstance(task,int) else 'Open the top drawer.' if task=='open_top' else TASKS[0]
   self.tool('robot_start_task',text)
   if task=='middle_partial_prefix':
    self.wait(lambda p:.045<=p['drawer_gaps']['middle']<=.075,180,'partial drawer preparation')
   elif task=='open_top':self.wait(lambda p:p['physical']['drawers']['top']['open'],180,'open top preparation')
   else:
    names={0:'open_middle',1:'bowl_stove',2:'bottle_cabinet',3:'bowl_drawer',4:'bowl_cabinet',6:'cheese_bowl',7:'turn_on_stove',8:'bowl_plate',9:'bottle_rack'}
    self.wait(lambda p:p['physical']['native_goal_relations'][names[task]] and (p['state'] in ['completed','needs_review'] or (not p['physical']['objects'].get({1:'bowl',2:'wine_bottle',3:'bowl',4:'bowl',6:'cheese',8:'bowl',9:'wine_bottle'}.get(task,''),{}).get('robot_contact',False))),180,'source preparation goal')
   # Stop the setup source through its real control path, then retire all IO.
   self.tool('robot_cancel_task')
   began=time.monotonic()
   while True:
    try:self.req('/eval/t6',{'op':'reference_home'});break
    except OSError:
     if time.monotonic()-began>30:raise
     time.sleep(.2)
   self.wait(lambda _:not self.req('/eval/t6',{'op':'reference_status'})['busy'],90,'reference physical home')
  self.connect_voice()
  self.tool('robot_start_task',TASKS[self.case['active_task_id']])
  p=self.wait(lambda p:self.req('/eval/t6',{'op':'gate'})['passed'],180,'correct execution gate')
  g=self.req('/eval/t6',{'op':'gate'});save(self.folder/'QA_READY.json',dict(identity=g['identity'],gate=g,time=time.time()))
  self.client.wait(timeout=65)
 def close(self):
  if not hasattr(self,'log'):return
  if self.processes and all(p.poll() is None for p in self.processes[:2]):
   try:self.req('/evaluator/finish',{},timeout=2);self.processes[1].wait(60)
   except (OSError,subprocess.TimeoutExpired):pass
  for p in reversed(self.processes):
   if p.poll() is None:
    try:os.killpg(p.pid,signal.SIGTERM)
    except ProcessLookupError:pass
  for p in self.processes:
   try:p.wait(60)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL)
  self.log.close()
  if account_denial(self.folder):HALT.set()
  if getattr(self,'voice_slot_acquired',False):
   self.voice_lease.seek(0);self.voice_lease.truncate();self.voice_lease.write(str(time.time()).encode());self.voice_lease.flush();fcntl.flock(self.voice_lease,fcntl.LOCK_UN);self.voice_lease.close();self.voice_slot_acquired=False
  if hasattr(self,'db') and (self.db/'episodes.sqlite').exists():
   target=self.folder/'gateway_archive';target.mkdir(exist_ok=True)
   with sqlite3.connect(str(self.db/'episodes.sqlite')) as src:
    with sqlite3.connect(str(target/'episodes.sqlite')) as dst:src.backup(dst)
   for name in ['robot.token']:
    if (self.db/name).exists():shutil.copy2(self.db/name,target/name)


def execute(case,run,worker,max_attempts=3):
 home=run/'cases'/case['case_id'];home.mkdir(parents=True,exist_ok=True)
 result=dict(case_id=case['case_id'],question_family=case['question_family'],condition_id=case['condition_id'],question_text=case['question_text'],qa_started=False,attempts=[])
 for i in range(1,max_attempts+1):
  if HALT.is_set():break
  f=home/('attempt%02d'%i);runtime=Runtime(f,case,worker);attempt=dict(attempt=i,directory=str(f),started=time.time())
  try:
   runtime.start();runtime.setup()
   save(f/'OBSERVATION_END.json',dict(time=time.time(),status=runtime.status(),private_physics=runtime.inspect()))
  except Exception as error:
   attempt.update(error_type=type(error).__name__,error=str(error)[:700]);save(f/'SETUP_ABORT.json',attempt)
  finally:runtime.close()
  events=(f/'client/events.jsonl').read_text() if (f/'client/events.jsonl').exists() else ''
  attempt['qa_started']=any(json.loads(l).get('type')=='client.input_clip_start' for l in events.splitlines() if l.strip())
  denial=account_denial(f)
  if denial:attempt['global_infrastructure_failure']=denial;HALT.set()
  attempt['finished']=time.time();result['attempts'].append(attempt)
  if attempt['qa_started']:result.update(qa_started=True,committed_directory=str(f));break
 save(home/'CASE.json',result);print('CASE',case['case_id'],'qa',result['qa_started'],'attempts',len(result['attempts']),flush=True)
 return result

