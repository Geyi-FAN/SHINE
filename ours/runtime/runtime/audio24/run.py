"""Two isolated real-PCM sessions. First outcomes only, no method updates/retries."""
import argparse,concurrent.futures,hashlib,json,os,signal,socket,subprocess,threading,time,urllib.request
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=B/'freeze/voice';OUT=Path('/mnt/disk_4/geyi/audio_switch24_F28d_G22_20261102');DATA=OUT/'dataset'
SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python';NODE=str(ROOT/'runtime/node-v22.23.3-linux-x64/bin/node')
lock=threading.Lock()
def emit(kind,**data):
 row=dict(time=time.time(),kind=kind,**data)
 with lock:
  with (OUT/'progress.jsonl').open('a')as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
  print(json.dumps(row,ensure_ascii=False),flush=True)
def check_freeze():
 path=OUT/'FREEZE_v3.json'
 if not path.exists():raise RuntimeError('Formal run requires freeze manifest')
 for p,h in json.loads(path.read_text())['files'].items():
  if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise RuntimeError('FROZEN_FILE_DRIFT '+p)
def case_run(authored,slot,runlabel,probe=False):
 if not probe:check_freeze()
 directory=OUT/runlabel/'cases'/authored['case_id'];directory.mkdir(parents=True,exist_ok=False);voice=directory/'voice';voice.mkdir(mode=0o700)
 gp,wp,dp=(19081+slot*100,19087+slot*100,19089+slot*100)
 for port in [gp,wp,dp]:
  with socket.socket()as sock:assert sock.connect_ex(('127.0.0.1',port))!=0,port
 conf=json.loads((ROOT/'data/harness/config.json').read_text());conf.update(port=dp,backends=[]);(voice/'config.json').write_text(json.dumps(conf));os.chmod(voice/'config.json',0o600)
 states=json.loads((DATA/'initial_states.json').read_text());fixture=next(s for s in states if s['state_id']==authored['scene_binding']['state_id']);pre=authored['category']not in ('T1','T5');target={'T1':1,'T2':1,'T3':8,'T4':1,'T5':6,'T6':1,'T7':6,'T8':1}[authored['category']]
 spec=dict(case_id=authored['case_id'],authored=authored,fixture=fixture,source_task=1,target_task=target,preserve_bowl=authored['category']=='T7',phase='M2'if pre else None,context_turns=['Please put the bowl on the stove.']if pre else [],task_control_budget=1200,restore='bowl'if authored['category']=='T4'else None,gateway_port=gp,web_port=wp,audio_manifest=str(DATA/'audio.json'),protocol=json.loads((DATA/'PROTOCOL.json').read_text()))
 (directory/'spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2));env=dict(os.environ,VOICE_ROBOT_DATA_DIR=str(directory/'gateway'),VOICE_EVAL_RECORD_DIR=str(directory/'recordings'),VOICE_DISCOVERY_FILE=str(voice/'run/daemon.json'),VOICE_HISTORY_DIR=str(directory/'review_history'),VOICE_ROBOT_PORT=str(gp),VOICE_WEB_PORT=str(wp),VOICE_HARNESS_RUNTIME_CONFIG=str(ROOT/'configs/runtime.local.json'),HYBRID_POLICY_NAMESPACE='AUDIO24:'+runlabel+':'+authored['case_id'],PYTHONDONTWRITEBYTECODE='1')
 ve=dict(env,DASHSCOPE_API_KEY=(ROOT/'private/dashscope.key').read_text().strip(),QWEN_LIVE_HARNESS_DATA_DIR=str(voice),QWEN_LIVE_HARNESS_DISCOVERY_DIR=str(voice),ROBOT_GATEWAY_URL=f'http://127.0.0.1:{gp}',ROBOT_GATEWAY_TOKEN_FILE=str(ROOT/'private/robot.token'),ROBOT_AUDIO_BENCHMARK_HOST='1',ROBOT_BROWSER_HOST='1',ROBOT_RECEIPT_AUDIO_DIR='/mnt/disk_2/geyi/voice_pi05_harness/data/receipt_audio',ROBOT_INSTRUCTION_PROMPT_FILE=str(ROOT/'configs/instruction_prompt.txt'))
 processes=[];emit('case_start',case_id=authored['case_id'],slot=slot,scope=runlabel)
 try:
  with (directory/'services.log').open('w')as log:
   for cmd,e in [([NODE,str(B/'artifacts/G22_audio_daemon/dist/index.js'),'--daemon-only'],ve),([SIM,'-u',str(B/'audio24/gateway.py'),'--spec',str(directory/'spec.json'),'--out',str(directory),'--port',str(gp),'--gpu',str(5+slot),'--policy-port',str(19867+slot)],env),([NODE,str(ROOT/'web_host/server.mjs')],env)]:processes.append(subprocess.Popen(cmd,env=e,stdout=log,stderr=log,start_new_session=True))
   for _ in range(180):
    if any(p.poll()is not None for p in processes):raise RuntimeError('isolated_service_exited')
    try:
     response=json.load(urllib.request.urlopen(f'http://127.0.0.1:{wp}/api/status',timeout=2))
     if response.get('ready'):
      image=urllib.request.urlopen(f'http://127.0.0.1:{wp}/api/frame.jpg',timeout=3).read();assert image[:2]==b'\xff\xd8';break
    except (OSError,ValueError):pass
    time.sleep(1)
   else:raise TimeoutError('isolated_readiness')
   (directory/'readiness.json').write_text(json.dumps(response,indent=2))
   if probe=='source':
    subprocess.run([NODE,str(B/'audio24/probe_source.mjs'),str(directory/'spec.json'),str(directory)],env=env,stdout=log,stderr=log,timeout=230,check=True)
   elif probe:
    token=(ROOT/'private/robot.token').read_text().strip();req=urllib.request.Request(f'http://127.0.0.1:{gp}/evaluator/inspect',headers={'Authorization':'Bearer '+token});a=json.load(urllib.request.urlopen(req));time.sleep(1.2);b=json.load(urllib.request.urlopen(req));assert b['sample']['step']>=a['sample']['step'];assert 'measurements'in b['sample'];(directory/'ENGINEERING.json').write_text(json.dumps(dict(before=a,after=b,no_audio_sent=True),indent=2))
   else:subprocess.run([NODE,str(B/'audio24/client.mjs'),str(directory/'spec.json'),str(directory)],env=env,stdout=log,stderr=log,timeout=1900,check=True)
   if not probe:
    try:processes[1].wait(30)
    except subprocess.TimeoutExpired:pass
 except BaseException as e:
  (directory/'RUNNER_ERROR.txt').write_text(repr(e));emit('case_runner_error',case_id=authored['case_id'],error=repr(e));
  if not (directory/'result.json').exists():(directory/'result.json').write_text(json.dumps(dict(case_id=authored['case_id'],turns=[],messages=[],precondition_validated=False,errors=[repr(e)],finished=dict(time=time.time(),monotonic=time.monotonic())),indent=2))
 finally:
  for p in reversed(processes):
   if p.poll()is None:
    try:os.killpg(p.pid,signal.SIGTERM)
    except ProcessLookupError:pass
  for p in processes:
   try:p.wait(15)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL)
 emit('case_finished',case_id=authored['case_id'],slot=slot,scope=runlabel)
 if not probe:subprocess.run([SIM,str(B/'audio24/score.py'),'--partial'],cwd=B,check=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('--probe',action='store_true');p.add_argument('--probe-source',action='store_true');a=p.parse_args();cases=json.loads((DATA/'selected.private.json').read_text())
 if a.probe:case_run(cases[0],0,'engineering_no_audio',True);return
 if a.probe_source:case_run(next(c for c in cases if c['script_id']=='T2_01'),0,'engineering_source_pause_v3b','source');return
 check_freeze();runlabel='formal24_v3';root=OUT/runlabel;root.mkdir(exist_ok=False);(root/'STARTED.json').write_text(json.dumps(dict(time=time.time(),cases=24,first_attempts=True,earlier_v1_v2='aborted evaluator trigger/monitor faults; no results pooled',cloud_sessions=1)))
 # Fixed assignment/order declared before outcomes: even/odd case indices per worker.
 # Provider explicitly returned Requests rate limit exceeded with two sessions.
 # Fixed single-session ordering and between-case cooling are not scored delays.
 for c in cases:
  case_run(c,0,runlabel);time.sleep(30)
 subprocess.run([SIM,str(B/'audio24/score.py')],cwd=B,check=True)
 (root/'COMPLETED.json').write_text(json.dumps(dict(time=time.time(),cases=24,results=len(list((root/'cases').glob('*/result.json'))),first_attempts=True),indent=2));emit('round_completed',cases=24)
if __name__=='__main__':main()
