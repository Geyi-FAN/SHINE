"""Sequential true-PCM engineering preflight, original 32 cases and budgets.
No model/score reference text is injected, except declared T6 controlled setup.
"""
import os,sys,json,time,subprocess,signal,fcntl,traceback,hashlib,urllib.request,shutil,uuid,socket
from pathlib import Path
R=Path('/mnt/disk_4/geyi/audio_switch_benchmark/regressions/c3r_pi05_70_serial_20261108');D=Path('/mnt/disk_4/geyi/audio_switch_benchmark')
W=Path(__file__).resolve().parents[1]/'code/runtime_v12'
SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python';NODE='/mnt/disk_2/geyi/voice_pi05_harness/runtime/node-v22.23.3-linux-x64/bin/node'
ROUND=R/'round2';TOKEN=(R/'private/robot.token').read_text().strip();OP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def read(p):return json.loads(Path(p).read_text())
def write(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(v,indent=2,ensure_ascii=False));q.replace(p)
def get(port,path,body=None):
 q=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'})
 with OP.open(q,timeout=6)as f:return json.load(f)
def wait(fn,seconds,label):
 end=time.monotonic()+seconds;last=None
 while time.monotonic()<end:
  case=globals().get('CURRENT_CASE')
  if case is not None:
   from provider_failure import provider_failure
   if provider_failure(case,globals().get('CURRENT_START',0),time.time()):
    raise RuntimeError('realtime_provider_access_denied_1007; stop dispatch, do not retry benchmark audio')
  try:
   last=fn()
   if last:return last
  except (OSError,ValueError):pass
  time.sleep(.2)
 raise TimeoutError(label)
def state_fixture(branch,state_id):
 if branch=='T1':rows=read(R/'data/T1/initial_states.json')
 elif branch=='T4':rows=read(R/'data/T4/data/initial_states.json')
 elif branch=='T5':rows=read(R/'data/T5/initial_states.json')
 elif branch=='T7':rows=read(R/'data/T7/initial_states.json')
 elif branch=='T8':rows=read(R/'data/T8/data/initial_states.json')
 else:raise ValueError(branch)
 return next(s for s in rows if s['state_id']==state_id)
def config_for(item,ports,case):
 b=item['branch'];cid=item['public_case_id'];c=item['case'];gp,wp,vp=ports
 proto=None;audio=None;client=None;env={};spec=dict(case_id=cid,source_task=0,target_task=999,context_turns=[],serve_live=False,task_control_budget=1200,reset_count=1,initial_version=0,service_lifetime_s=3600,evaluation_family=b)
 if b=='T1':
  spec['fixture']=state_fixture(b,item['state_id']);proto=R/'data/T1/protocol.json';env=dict(AUDIO_BENCH_DATA=str(R/'data/T1'),T1_BROWSER_TOKEN_FILE=str(R/'private/browser.token'),T1_COMMON_AUDIO_CLIENT=str(R/'adapter/shared/t8_adapter/audio-client.mjs'));client=[NODE,str(D/'T1/current/adapter/client.mjs')]
 elif b=='T2':
  c=next(x for x in read(R/'data/T2_ALL.json') if x['case_id']==cid);c.update(robot_port=gp,gateway_port=gp,web_port=wp);spec['fixture']=c['fixture'];spec['source_task']=c['source_task'];proto=D/'T2/current/dataset/PROTOCOL.json';env={'T2_BROWSER_TOKEN_FILE':str(R/'private/browser.token'),'T2_ROBOT_TOKEN_FILE':str(R/'private/robot.token')};p=case/'client_spec.private.json';write(p,c);client=[NODE,str(R/'adapter/T2/client/t2_client.mjs'),str(case),f'http://127.0.0.1:{wp}',str(p)]
 elif b=='T3':
  c=read(R/'data/T3/specs'/(cid+'.json'));spec.update(c);spec.update(case_id=cid,evaluation_family=b,gateway_port=gp,web_port=wp);proto=None;p=case/'client_spec.private.json';write(p,dict(c,gateway_port=gp,web_port=wp));client=[NODE,str(R/'adapter/T3/client.mjs'),str(p),str(case)]
 elif b=='T4':
  data=R/'data/T4/data';c=next(x for x in read(data/'selected.private.json')if x['case_id']==cid);contract=c['private_contract'];spec.update(fixture=state_fixture(b,item['state_id']),source_task=contract['source_task_id'],phase=contract['source_stage'],context_turns=[t['text']for t in c['context_turns']]);proto=data/'PROTOCOL.json';p=case/'client_spec.private.json';write(p,dict(case=c,budgets=read(proto)['budgets'],audio=read(data/'audio_manifest.json'),web_port=wp,robot_port=gp,delivery_stage='full'));env={'T4_ROBOT_TOKEN_FILE':str(R/'private/robot.token'),'T4_BROWSER_TOKEN_FILE':str(R/'private/browser.token')};client=[NODE,str(R/'adapter/T4/client.mjs'),str(p),str(case)]
 elif b=='T5':
  spec['fixture']=state_fixture(b,item['state_id']);proto=R/'data/T5/PROTOCOL.json';audio=R/'data/T5/audio_manifest.json';env={'AUDIO_BENCH_DATA':str(R/'data/T5'),'AUDIO_BENCH_AUDIO':str(audio),'T5_BROWSER_TOKEN_FILE':str(R/'private/browser.token'),'T5_ALLOW_UNREVIEWED_AUDIO':'1'};client=[NODE,str(R/'adapter/T5/client/client.mjs')]
 elif b=='T6':
  cards=read(D/'T6/current/dataset/scene_cards.private.json');card=next(x for x in cards if x['scene_card_id']==c['scene_card_id']);spec.update(fixture=read(R/'data/T6/fixture.private.json'),source_task=c['preparation'][0]if c['preparation']and isinstance(c['preparation'][0],int)else c['active_task_id'],target_task=c['active_task_id'],t6_card=card,context_turns=['reference preparation']if c['preparation']else[]);client=None
 elif b=='T7':
  spec['fixture']=state_fixture(b,item['state_id']);mapping=next(x for x in read(D/'T7/current/dataset/CASE_ID_MAP.json')if x['case_id']==cid);folder=R/'data/T7'/mapping['condition'];c=next(x for x in read(folder/'cases.private.json')if x['case_id']==mapping['runtime_case_id']);p=case/'client_spec.private.json';write(p,dict(authored=c,protocol=read(folder/'PROTOCOL.json'),audio_manifest=str(folder/'audio.json'),dataset_dir=str(folder),gateway_url=f'http://127.0.0.1:{gp}',robot_token_file=str(R/'private/robot.token'),discovery_file=str(case/'voice/run/daemon.json'),probe_policy=False));client=[NODE,str(R/'adapter/T7/client/client.mjs'),str(p),str(case)]
 elif b=='T8':
  data=R/'data/T8/data';c=next(x for x in read(data/'selected.private.json')if x['case_id']==cid);spec['fixture']=state_fixture(b,item['state_id']);proto=data/'PROTOCOL.json';p=case/'client_spec.private.json';t8_protocol=read(proto);t8_protocol['budgets'].update(precondition_wall_s=t8_protocol['budgets']['setup_wall_s'],per_physical_goal_wall_s=t8_protocol['budgets']['source_wall_s'],qa_complete_answer_from_audio_end_s=t8_protocol['budgets']['qa_complete_audio_s']);write(p,dict(authored=c,protocol=t8_protocol,audio_manifest=str(data/'audio_manifest.json'),web_port=wp,gateway_port=gp));client=[NODE,str(R/'adapter/shared/t8_adapter/client.mjs'),str(p),str(case)]
 else:raise ValueError(b)
 env.update(AUDIO_BENCH_OUT=str(case),AUDIO_BENCH_BASE=f'http://127.0.0.1:{wp}',AUDIO_BENCH_CASE=cid)
 if proto:env['AUDIO_BENCH_PROTOCOL']=str(proto)
 return spec,client,env

def aliases(case,episode,branch=None):
 p=case/'recordings'/episode;p.mkdir(parents=True,exist_ok=True)
 if branch in ('T2','T3'):
  tick=p/'control_ticks.jsonl'
  wait(lambda:tick.is_file() and not tick.is_symlink() and tick.stat().st_size>0,10,'independent branch physical recorder')
  return
 for name,target in [('control_ticks.jsonl','physical.jsonl'),('environment.mp4','gateway_environment.mp4')]:
  q=p/name
  if not q.exists()and not q.is_symlink():q.symlink_to(case/target)

def run_case(index,item):
 global CURRENT_CASE,CURRENT_START
 cid=item['public_case_id'];case=ROUND/'cases'/cid;case.mkdir(parents=True,exist_ok=False)
 from port_lease import allocate
 port_lease=allocate(LANE,D/'leases/ours_full930_readiness_ports')
 gp=port_lease.port
 wp=gp+2;vp=gp+3;ports=gp,wp,vp;write(case/'PORT_ALLOCATION.json',dict(ports=ports,lane=LANE,all_bind_probed=True,ephemeral_range=port_lease.ephemeral,port_claim_lifetime='whole_case'));own_ready=False;procs=[];logs=[];start=time.time();outcome=dict(lane=LANE,trial_uid=item.get('trial_uid'),repetition_index=item.get('repetition_index'),preflight_id=item['preflight_id'],case_uid=item['case_uid'],branch=item['branch'],case_id=cid,started_at=start,core_revision=read(W/'FREEZE.json')['runtime_revision'],status='starting',formal_trial=IS_FORMAL_TRIAL)
 CURRENT_CASE=case;CURRENT_START=start
 def spawn(cmd,env,name):
  f=(case/(name+'.console.log')).open('w');logs.append(f);p=subprocess.Popen(cmd,env=env,stdout=f,stderr=f,start_new_session=True);procs.append(p);return p
 env=dict(os.environ,PYTHONPATH=str(W/'runtime'),PYTHONDONTWRITEBYTECODE='1',HARNESS_ROBOT_TOKEN_FILE=str(R/'private/robot.token'),HYBRID_POLICY_NAMESPACE=('C3R_CLOUD04_FORMAL:'if IS_FORMAL_TRIAL else'C3R_CLOUD04_PREFLIGHT:')+str(case),ROBOT_GATEWAY_URL=f'http://127.0.0.1:{gp}',ROBOT_GATEWAY_TOKEN_FILE=str(R/'private/robot.token'),ROBOT_AUDIO_BENCHMARK_HOST='1',ROBOT_BROWSER_HOST='1',PF_DISCOVERY_FILE=str(case/'voice/run/daemon.json'),PF_GATEWAY_URL=f'http://127.0.0.1:{gp}',PF_ROBOT_TOKEN_FILE=str(R/'private/robot.token'),XDG_CACHE_HOME=str(R/'cache'),CUDA_CACHE_PATH=str(R/'cache/cuda'),TMPDIR=str(R/'cache/tmp'),NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost')
 env['C3R_RUNTIME_ROOT']=str(W)
 # EGL enumeration and CUDA UUIDs have different numbering; only YOLO inherits a UUID restriction.
 env['HYBRID_YOLO_CUDA_VISIBLE_DEVICES']=os.environ['CUDA_VISIBLE_DEVICES']
 env['CUDA_VISIBLE_DEVICES']=''
 if item['branch']=='T2':env['VOICE_BENCHMARK_TICK_LOG']='1'
 env.pop('DASHSCOPE_API_KEY',None);env.pop('QWEN_LIVE_HARNESS_REALTIME_API_KEY',None)
 for p in [R/'cache',R/'cache/cuda',R/'cache/tmp']:p.mkdir(parents=True,exist_ok=True)
 try:
  sys.path.insert(0,str(W/'tools'));from voice_profile import activate
  env.update(activate(W,case))
  spec,client,ce=config_for(item,ports,case);write(case/'spec.json',spec)
  env['HYBRID_POLICY_PORT']=str(POLICY_PORT)
  spawn([SIM,'-u',str(PREFIX_GATEWAY if item['branch']=='T6' else R/'adapter/eval_gateway70.py'),'--spec',str(case/'spec.json'),'--out',str(case),'--port',str(gp),'--gpu',str(RENDER_GPU),'--policy-port',str(POLICY_PORT)],env,'robot')
  prep_started=time.monotonic()
  prep_polls=0
  last_prep_note=0.
  def robot_ready():
   nonlocal prep_polls,last_prep_note
   if procs[0].poll() is not None:raise RuntimeError('robot process exited during preparation: '+str(procs[0].returncode))
   try:snapshot=get(gp,'/status')
   except (OSError,ValueError):snapshot={}
   prep_polls+=1
   if time.monotonic()-last_prep_note>=5:
    last_prep_note=time.monotonic()
    write(case/'PREPARATION_PROGRESS.json',dict(time=time.time(),polls=prep_polls,elapsed_s=time.monotonic()-prep_started,deadline_s=600,ready=snapshot.get('ready',False),execution_readiness=snapshot.get('execution_readiness'),failure_detail=snapshot.get('failure_detail'),audio_not_started=True))
   return snapshot if snapshot.get('ready')else False
  ready=wait(robot_ready,600,'robot readiness')
  write(case/'PREPARATION_PROGRESS.json',dict(polls=prep_polls,elapsed_s=time.monotonic()-prep_started,deadline_s=600,finished=time.time(),passed=True,ready_identity=ready,audio_not_started=True))
  if ready.get('runtime_revision')!=read(W/'FREEZE.json')['runtime_revision']:raise RuntimeError('wrong runtime identity')
  own_ready=True
  aliases(case,ready['episode_id'],item['branch']);write(case/'READY_IDENTITY.json',ready)
  if os.environ.get('REPAIR_PREP_ONLY')=='1':
   outcome.update(status='preparation_preflight_passed',audio_played=False,ready_at=time.time())
   return outcome
  gate_only=item['branch']=='T6' and os.environ.get('T6_GATE_ONLY')=='1'
  if not gate_only:
   voice=case/'voice';voice.mkdir(mode=0o700);(voice/'config.json').write_bytes(VOICE_CONFIG.read_bytes());(voice/'config.json').chmod(0o600)
   ve=dict(env,QWEN_LIVE_HARNESS_DATA_DIR=str(voice),QWEN_LIVE_HARNESS_DISCOVERY_DIR=str(voice),QWEN_LIVE_HARNESS_PORT=str(vp),QWEN_LIVE_HARNESS_CWD=str(W))
   voice_process=spawn([NODE,str(W/'voice/dist/index.js'),'--daemon-only'],ve,'voice')
   def voice_ready():
    if voice_process.poll() is not None:raise RuntimeError('voice_daemon_exited_before_ready; inspect voice.console.log and voice/logs/runtime-errors*.jsonl')
    return (voice/'run/daemon.json').exists()
   wait(voice_ready,30,'voice discovery')
   pe=dict(env,VOICE_WEB_PORT=str(wp),VOICE_ROBOT_PORT=str(gp),VOICE_DISCOVERY_FILE=str(voice/'run/daemon.json'),VOICE_WEB_STATIC_DIR=str(R/'adapter/web_root/empty_static'),VOICE_HISTORY_DIR=str(case/'history'),VOICE_ROBOT_DATA_DIR=str(case/'gateway'))
   spawn([NODE,str(R/'adapter/web_root/web_host/server.mjs')],pe,'transport_api')
   wait(lambda:urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f'http://127.0.0.1:{wp}/api/status',timeout=2).status==200,30,'readonly API readiness')
  outcome.update(status='audio_running',ready_at=time.time());write(case/'ATTEMPT.json',outcome);refresh()
  if item['branch']=='T6':
   sys.path.insert(0,str(R/'adapter'));from t6_cached_setup import Runtime
   obj=Runtime.__new__(Runtime);obj.folder=case;obj.case=item['case'];obj.robot=gp;obj.token=TOKEN
   def connect_voice():
    source=D/'T6/current';manifest=next(x for x in read(source/'manifest.json')if x['case_id']==cid)
    cfg=dict(case_id=cid,out=str(case),pcm_file=str(source/manifest['pcm_path']),audio_sha256=manifest['audio_sha256'],browser_token_file=str(R/'private/browser.token'),robot_token_file=str(R/'private/robot.token'),web_url=f'http://127.0.0.1:{wp}',robot_url=f'http://127.0.0.1:{gp}');write(case/'qa_client.private.json',cfg)
    obj.client=spawn([NODE,str(R/'adapter/T6/scripts/audio_switch_benchmark/run_one_cli.mjs'),str(case/'qa_client.private.json')],env,'client')
    wait(lambda:(case/'VOICE_READY.json').exists(),60,'QA voice readiness')
   obj.connect_voice=connect_voice;obj.setup()
   if obj.client.returncode not in (None,0):raise RuntimeError('T6 audio client failed')
  else:
   cli=spawn(client,dict(env,**ce),'client');wait(lambda:cli.poll() is not None,2100,'audio client process')
   if cli.returncode:raise RuntimeError('audio client exit '+str(cli.returncode))
  outcome.update(status='finished',audio_client_returned=True)
 except BaseException as error:
  outcome.update(status='failed',error_type=type(error).__name__,error=str(error),traceback=traceback.format_exc());write(case/'SETUP_ABORT.json',outcome)
 finally:
  try:
   if own_ready and procs and procs[0].poll() is None:outcome['final_status']=get(gp,'/status');get(gp,'/evaluator/finish',{})
  except OSError:pass
  deadline=time.monotonic()+15
  while procs and procs[0].poll()is None and time.monotonic()<deadline:time.sleep(.1)
  for p in reversed(procs):
   if p.poll()is None:
    try:os.killpg(p.pid,signal.SIGTERM)
    except ProcessLookupError:pass
  for p in procs:
   try:p.wait(timeout=12)
   except subprocess.TimeoutExpired:
    os.killpg(p.pid,signal.SIGKILL);p.wait()
  for f in logs:f.close()
  outcome.update(finished_at=time.time(),elapsed_seconds=time.time()-start)
  result=case/'result.json'
  if result.exists():
   r=read(result);outcome['audio_played']=bool(r.get('audio_played')or r.get('turns')or r.get('question_send_started'));outcome['client_errors']=r.get('errors',[]);outcome['turns']=len(r.get('turns',[]));outcome['terminal_state']=(r.get('final')or{}).get('state',r.get('terminal_state'))
  else:outcome['audio_played']=False
  if item['branch']=='T6' and (case/'TRIAL.json').exists():
   qa=read(case/'TRIAL.json');outcome['audio_played']=bool(qa.get('qa_started') and (case/'COMMIT.json').exists() and (case/'audio_received.jsonl').exists() and (case/'audio_received.jsonl').stat().st_size)
   outcome['audio_accounting_source']='TRIAL.qa_started + COMMIT + actual received PCM log'
  from provider_failure import provider_failure,delivered_audio
  finish=r.get('finished') if result.exists()else None
  cutoff=finish.get('time',outcome['finished_at']) if isinstance(finish,dict)else outcome['finished_at']
  outcome['provider_failure']=provider_failure(case,start,cutoff)
  outcome['audio_delivery_evidence']=delivered_audio(case)
  outcome['audio_played']=outcome['audio_delivery_evidence']['started']
  if outcome['provider_failure']:outcome['status']='infrastructure_failed'
  write(case/'PREFLIGHT_OUTCOME.json',outcome);refresh();port_lease.close()
 return outcome

def refresh():
 plan=read(R/'data/SELECTED32.private.json');done=[];active=[]
 for item in plan:
  case=ROUND/'cases'/item['public_case_id'];p=case/'PREFLIGHT_OUTCOME.json'
  if p.exists():done.append(read(p))
  elif (case/'ATTEMPT.json').exists():active.append(read(case/'ATTEMPT.json'))
 status=dict(planned=32,completed_attempts=len(done),audio_played=sum(x.get('audio_played',False)for x in done),active=[x['case_uid']for x in active],finished=done,main_service_switched=False,gate='NOT_ACCEPTED_YET')
 write(ROUND/'LIVE_STATUS.json',status)
 lines=['# r4完整32例真实音频＋动作回归','',f"已完成尝试 {len(done)}/32；其中已有音频输入 {status['audio_played']}。主8787尚未切换。",'', '| 案例 | 分支 | 状态 | 音频输入 | 客户端错误 |','|---|---|---|---|---|']
 for x in done:lines.append('|'+ '|'.join([x['case_id'],x['branch'],x['status'],str(x.get('audio_played',False)),str(x.get('error')or x.get('client_errors')or'')[:180].replace('|','/')])+'|')
 lines+=['','正在运行：'+str(status['active']),'','未进行正式930试次；首试与修复诊断单独保存，未拼分。'];(ROUND/'LIVE_PROGRESS.md').write_text('\n'.join(lines)+'\n')

def main():
 ROUND.mkdir(parents=True,exist_ok=False);(ROUND/'cases').mkdir();write(ROUND/'RUN_PLAN.json',dict(core_root=str(W),fixed_cases=read(R/'data/PREFLIGHT32.json'),model='pi05 E3 744 30000',policy_service=47270,simulation_gpu=6,audio_concurrency=1,gate='No main switch until results reviewed',T5_human_review='not_performed; technical preflight only',typed_setup_only='T6 original controlled benchmark preparation',audio_route='direct authenticated Realtime framework; API proxy is readonly evidence only'))
 account=read(R/'reports/API_ISOLATION.json');refresh()
 with open(account['lease'],'a+b')as lease:
  fcntl.flock(lease,fcntl.LOCK_EX)
  for index,item in enumerate(read(R/'data/SELECTED32.private.json')):
   if (ROUND/'STOP_AFTER_CURRENT').exists():
    write(ROUND/'STOPPED.json',dict(time=time.time(),reason='operator requested after current case'));return
   if shutil.disk_usage(R).free<10*1024**3:raise RuntimeError('Insufficient output disk space')
   sys.path.insert(0,str(W/'tools'))
   from verify_freeze import verify
   check=verify(W)
   if not check['passed']:raise RuntimeError('Core freeze changed: '+str(check['failures']))
   print(json.dumps(dict(event='case_start',index=index+1,case_uid=item['case_uid'],time=time.time())),flush=True)
   result=run_case(index,item)
   print(json.dumps(dict(event='case_done',index=index+1,case_uid=item['case_uid'],status=result['status'],audio_played=result.get('audio_played'),time=time.time())),flush=True)
 write(ROUND/'ATTEMPTS_COMPLETED.json',dict(time=time.time(),attempts=32));refresh()
if __name__=='__main__':main()
