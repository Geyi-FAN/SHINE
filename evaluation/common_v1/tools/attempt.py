"""Fixed-catalog, browser-free ASR + general Agent branch coordinator. No score selection."""
import argparse,datetime,hashlib,json,os,signal,subprocess,sys,time,traceback,urllib.request,shutil
from collections import Counter
from pathlib import Path
METHOD=os.environ['COMMON_METHOD']
Q=Path(__file__).resolve().parents[1];R=Q/'actors'/METHOD;sys.path[:0]=[str(R/'code'),str(R/'adapter'),str(R/'adapter/evaluator_v2')]
SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
NODE='/mnt/disk_2/geyi/voice_pi05_harness/runtime/node-v22.23.3-linux-x64/bin/node'
from branch_config import config_for
TOKEN=(R/'private/robot.token').read_text().strip();OP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
SETTINGS=dict(gpu=2,asr='ws://127.0.0.1:49650',policy='http://127.0.0.1:49661',port=49651)
HOT=Q/'work'/'hot'/METHOD/('lane'+os.environ['COMMON_LANE']);HOT.mkdir(parents=True,exist_ok=True)
def archive_case(case):
 hot=case.resolve();temporary=case.with_name('.'+case.name+'.archiving')
 shutil.copytree(hot,temporary,symlinks=True)
 hashes={str(p.relative_to(hot)):hashlib.sha256(p.read_bytes()).hexdigest()for p in hot.rglob('*')if p.is_file()and not p.is_symlink()}
 assert all(hashlib.sha256((temporary/rel).read_bytes()).hexdigest()==h for rel,h in hashes.items())
 case.unlink();temporary.rename(case);write(case/'SSD_ARCHIVE.json',dict(hot=str(hot),archive=str(case),sha256=hashes,all_matched=True))
def read(p):return json.loads(Path(p).read_text())
def write(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(v,indent=2,ensure_ascii=False,default=str));q.replace(p)
def request(port,path,body=None):
 q=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+TOKEN})
 try:
  with OP.open(q,timeout=10)as f:return json.load(f)
 except urllib.error.HTTPError as e:raise RuntimeError(f'{path}: HTTP {e.code}: '+e.read().decode()[:1000])from e
def wait(fn,seconds,label):
 end=time.monotonic()+seconds;last=None
 while time.monotonic()<end:
  try:
   last=fn()
   if last:return last
  except(OSError,ValueError):pass
  time.sleep(.2)
 raise TimeoutError(label)
def prepare_spec(item,case,port):
 spec,client,env=config_for(item,(port,port,port),case)
 c=item['case'];b=item['branch'];p=c.get('private_contract',{});target=p.get('final_target_task_id',p.get('final_target_task',p.get('target_task_id')))
 if b=='T2':target=spec['source_task']
 if b=='T3':target=spec['target_task']
 if b=='T7':spec['source_task']=p['predecessor_task_id']
 if b=='T8':
  spec['source_task']=1 if c['initial_mode']!='idle'else 999
  if p.get('target_eligible')and target is None:target=1
 if target is None:target=999
 spec.update(target_task=target,policy_seed=int(item.get('policy_seed',7)),runtime_revision='asr-agent-oracle-v1',task_control_budget=1200,service_lifetime_s=2100,independent_termination_contract=c.get('private_judge',p))
 if b=='T3':
  spec['t3_prepare_mode']='replay';spec['t3_bank_root']=str(Q.parents[1]/'deployments/our_t3_prepared_judge_20261109/data/T3-controlled-source-prefix-v2-20261109')
  client[1]=str(Q/'clients/t3_controlled.mjs')
 if b=='T5':client[1]=str(Q/'clients/T5/client/client.mjs')
 if b=='T8':
  cp=case/'client_spec.private.json';cfg=read(cp);bud=cfg['protocol']['budgets']
  for dst,src in {'precondition_wall_s':'setup_wall_s','per_physical_goal_wall_s':'source_wall_s','qa_complete_answer_from_audio_end_s':'qa_complete_audio_s'}.items():bud[dst]=bud.get(dst,bud.get(src))
  write(cp,cfg)
  compat=R/'tools/t8_client_compat.mjs'
  if compat.exists():client[1]=str(compat)
 env.update(COMMON_ROBOT_TOKEN_FILE=str(R/'private/robot.token'),COMMON_BROWSER_TOKEN_FILE=str(R/'private/browser.token'))
 write(case/'spec.json',spec)
 return spec,client,env
def run_attempt(item,run,port,attempt=1):
 assert item['branch']!='T6','Use dedicated frozen-prefix QA adapter'
 cid=item['public_case_id'];uid=item.get('trial_uid')or item.get('trial_id')or cid
 case=run/'cases'/uid
 if item['branch']=='T6':case=case/'preparation_attempts'/f'A{attempt:02d}'
 if shutil.disk_usage(HOT).free<10*1024**3:raise RuntimeError('SSD working directory below 10 GiB free; no registered audio sent')
 hot=HOT/'runs'/run.name/'cases'/uid;hot.mkdir(parents=True,exist_ok=False);case.parent.mkdir(parents=True,exist_ok=True);case.symlink_to(hot,target_is_directory=True)
 outcome=dict(branch=item['branch'],case_id=cid,trial_uid=uid,repeat_id=item.get('repeat_id'),policy_seed=item.get('policy_seed',7),started_at=time.time(),method='ASR_Agent_Oracle_pi05'if METHOD=='B1'else'ASR_pi05',formal_trial=item.get('formal_trial',False),status='starting',preparation_attempt=attempt)
 processes=[];logs=[]
 def spawn(cmd,env,name):
  f=(case/(name+'.console.log')).open('w');logs.append(f);p=subprocess.Popen(cmd,env=env,stdout=f,stderr=f,start_new_session=True);processes.append(p);return p
 env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PURE_ASR_BASELINE='0'if METHOD=='B1'else'1',B1_OBSERVATION_GRACE_S='75',RAW_ASR_URL=SETTINGS['asr'],TMPDIR=str(R/'cache/tmp'),NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost')
 # The actor and audio process have no cloud credentials.
 for k in list(env):
  if any(w in k.upper()for w in ['API_KEY','API_TOKEN','ACCESS_TOKEN']):env.pop(k,None)
 try:
  spec,client,ce=prepare_spec(item,case,port);write(case/'ATTEMPT.json',outcome)
  write(case/'SOURCE_IDENTITY.json',dict(freeze_sha256=hashlib.sha256((R/'config/FROZEN_SHA256.json').read_bytes()).hexdigest()if(R/'config/FROZEN_SHA256.json').exists()else None,models=read(R/'config/MODELS.json'),scoring_version='audio-logical-goal-attribution-v4-20261109'))
  robot=spawn([SIM,'-B','-u',str(R/('code/agent_gateway.py'if METHOD=='B1'else'code/raw_gateway.py')),'--spec',str(case/'spec.json'),'--out',str(case),'--port',str(port),'--gpu',str(SETTINGS['gpu']),'--policy',SETTINGS['policy']],env,'robot')
  def ready():
   if robot.poll()is not None:raise RuntimeError('raw_engine_exit_before_ready:'+str(robot.returncode))
   return request(port,'/status')
  status=wait(ready,100,'Agent gateway readiness');assert status['runtime_revision']==('asr-agent-oracle-v1'if METHOD=='B1'else'asr-direct-T2-T8-v1')
  write(case/'READY_IDENTITY.json',status);outcome.update(status='audio_running',episode_id=status['episode_id'],ready_at=time.time());write(case/'ATTEMPT.json',outcome)
  if item['branch']=='T6':
   sys.path.insert(0,str(R/'adapter'));from t6_setup_methods import Runtime
   obj=Runtime.__new__(Runtime);obj.folder=case;obj.case=item['case'];obj.robot=port;obj.token=TOKEN
   def connect_voice():
    source=Path('/mnt/disk_4/geyi/audio_switch_benchmark/T6/current');m=next(x for x in read(source/'manifest.json')if x['case_id']==cid)
    cfg=dict(case_id=cid,out=str(case),pcm_file=str(source/m['pcm_path']),audio_sha256=m['audio_sha256'],browser_token_file=str(R/'private/browser.token'),robot_token_file=str(R/'private/robot.token'),web_url=f'http://127.0.0.1:{port}',robot_url=f'http://127.0.0.1:{port}');write(case/'qa_client.private.json',cfg)
    obj.client=spawn([NODE,str(R/'adapter/T6/scripts/audio_switch_benchmark/run_one_cli.mjs'),str(case/'qa_client.private.json')],env,'client')
    wait(lambda:(case/'VOICE_READY.json').exists(),50,'QA ASR readiness')
   obj.connect_voice=connect_voice;obj.setup();outcome['status']='client_finished'
  else:
   cli=spawn(client,dict(env,**ce),'client');cli.wait(timeout=2000)
   if cli.returncode:raise RuntimeError('client_process_exit:'+str(cli.returncode))
   outcome.update(status='client_finished',client_returncode=cli.returncode)
 except BaseException as e:
  preparation_failed=item['branch']=='T6'and isinstance(e,TimeoutError)and str(e)in ['partial drawer preparation','open top preparation','source preparation goal','correct execution gate']
  outcome.update(status='setup_unavailable'if preparation_failed else'technical_or_setup_failure',error_type=type(e).__name__,error=str(e),traceback=traceback.format_exc());write(case/'SETUP_ABORT.json',outcome)
 finally:
  try:outcome['final_status']=request(port,'/status');request(port,'/evaluator/finish',{})
  except (OSError,RuntimeError)as e:outcome['shutdown_receipt_error']=str(e)
  if processes:
   try:processes[0].wait(timeout=20)
   except subprocess.TimeoutExpired:pass
  for p in reversed(processes):
   if p.poll()is None:
    try:os.killpg(p.pid,signal.SIGTERM)
    except ProcessLookupError:pass
  for p in processes:
   try:p.wait(timeout=12)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
  for f in logs:f.close()
  result=case/'result.json'
  if item['branch']=='T6'and(case/'TRIAL.json').exists():
   trial=read(case/'TRIAL.json');events=[json.loads(x)for x in(case/'client/events.jsonl').read_text().splitlines()if x.strip()];asked=trial.get('qa_started',False)
   turn=dict(turn_id=cid,text=item['case']['question_text'],audio_started_wall=trial.get('audio_started'),audio_ended_wall=trial.get('audio_ended'),audio_sha256=read(case/'qa_client.private.json')['audio_sha256'])
   write(result,dict(case_id=cid,episode_id=outcome.get('episode_id'),started=dict(time=outcome['started_at']),finished=dict(time=time.time()),question_send_started=asked,precondition_validated=asked,turns=[turn]if asked else[],messages=events,errors=[trial['error']]if trial.get('error')else[],final=outcome.get('final_status'),qa_trial=trial,typed_setup_only=True,reference_transcript_injected=False))
  if result.exists():
   v=read(result);outcome.update(audio_played=bool(v.get('turns')or v.get('question_send_started')),turns=len(v.get('turns',[])),client_errors=v.get('errors',[]),precondition_validated=v.get('precondition_validated',False))
   # Label this independent run; do not fabricate language, tools, or answers.
   v['method']='ASR_Agent_Oracle_pi05'if METHOD=='B1'else'ASR_pi05';v['runtime_revision']='common-baselines-v1-20261114:'+METHOD;v['formal_trial']=bool(item.get('formal_trial'));v['trial_uid']=uid;v['policy_seed']=int(item.get('policy_seed',7));v['observation_grace_s']=75;v['scoring_deadlines_unchanged']=True;v['test_mode']='actual_PCM_to_Whisper; historical baseline method preserved; common preparation and measurement';write(result,v)
  else:outcome['audio_played']=False
  if(case/'client/events.jsonl').exists():
   try:
    from audit_pcm import audit
    service=Q/'services'/('asr'+os.environ['COMMON_LANE'])
    quality=audit(case,service);outcome['audio_quality_passed']=quality['passed']
   except Exception as e:outcome['audio_audit_error']=repr(e)
  if item['branch']=='T6':
   asked=(case/'COMMIT.json').exists()
   # No audio output exists in this method, so every legally asked QA fails.
   score=dict(case_id=cid,method='ASR_Agent_Oracle_pi05'if METHOD=='B1'else'ASR_pi05',asked=asked,planned_eligible=True,qa_denominator=1 if asked else 0,qa_success=False if asked else None,reason='no_answer_audio_in_pure_ASR_architecture'if asked else'not_asked_preparation_or_gate_failed',expected_answers_used=False)
   write(case/'SCORE.json',score);outcome['score']=score
  elif result.exists():
   write(case/'ITEM.private.json',item)
   with(case/'scoring_common.console.log').open('w')as sf:
    q2=subprocess.run([SIM,'-B',str(Q/'common/score.py'),'--case',str(case),'--item',str(case/'ITEM.private.json'),'--out',str(case/'common_score')],stdout=sf,stderr=subprocess.STDOUT)
   outcome['scoring_returncode']=q2.returncode
   if q2.returncode==0:outcome['score']=read(case/'common_score/SCORE.json')
   else:outcome['score']={};outcome['scoring_failed']=True
  outcome.update(finished_at=time.time(),elapsed_seconds=time.time()-outcome['started_at'],engine_error=(case/'ENGINE_ERROR.json').exists()or bool(read(case/'ENGINE_FINISHED.json').get('errors'))if(case/'ENGINE_FINISHED.json').exists()else True,directory=str(case));write(case/'ATTEMPT_OUTCOME.json',outcome)
 archive_case(case)
 return outcome

