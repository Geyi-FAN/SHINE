"""Fixed-catalog, browser-free pure ASR branch coordinator. No score selection."""
import argparse,datetime,hashlib,json,os,signal,subprocess,sys,time,traceback,urllib.request
from collections import Counter
from pathlib import Path
from branch_config import config_for
R=Path(__file__).resolve().parents[1]
SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
NODE='/mnt/disk_2/geyi/voice_pi05_harness/runtime/node-v22.23.3-linux-x64/bin/node'
TOKEN=(R/'private/robot.token').read_text().strip();OP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
SETTINGS=dict(gpu=6,asr='ws://127.0.0.1:49440',policy='http://127.0.0.1:49441',port=54301)
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
 spec.update(target_task=target,policy_seed=int(item.get('policy_seed',7)),runtime_revision='asr-direct-T2-T8-v1',task_control_budget=1200,service_lifetime_s=2100,independent_termination_contract=c.get('private_judge',p))
 write(case/'spec.json',spec)
 return spec,client,env
def run_attempt(item,run,port,attempt=1):
 cid=item['public_case_id'];uid=item.get('trial_uid')or item.get('trial_id')or cid
 case=run/'cases'/uid
 if item['branch']=='T6':case=case/'preparation_attempts'/f'A{attempt:02d}'
 case.mkdir(parents=True,exist_ok=False)
 outcome=dict(branch=item['branch'],case_id=cid,trial_uid=uid,repeat_id=item.get('repeat_id'),policy_seed=item.get('policy_seed',7),started_at=time.time(),method='ASR_direct_pi05',formal_trial=item.get('formal_trial',False),status='starting',preparation_attempt=attempt)
 processes=[];logs=[]
 def spawn(cmd,env,name):
  f=(case/(name+'.console.log')).open('w');logs.append(f);p=subprocess.Popen(cmd,env=env,stdout=f,stderr=f,start_new_session=True);processes.append(p);return p
 env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PURE_ASR_BASELINE='1',RAW_ASR_URL=SETTINGS['asr'],TMPDIR=str(R/'cache/tmp'),NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost')
 # The actor and audio process have no cloud credentials.
 for k in list(env):
  if any(w in k.upper()for w in ['API_KEY','API_TOKEN','ACCESS_TOKEN']):env.pop(k,None)
 try:
  spec,client,ce=prepare_spec(item,case,port);write(case/'ATTEMPT.json',outcome)
  robot=spawn([SIM,'-B','-u',str(R/'code/raw_gateway.py'),'--spec',str(case/'spec.json'),'--out',str(case),'--port',str(port),'--gpu',str(SETTINGS['gpu']),'--policy',SETTINGS['policy']],env,'robot')
  def ready():
   if robot.poll()is not None:raise RuntimeError('raw_engine_exit_before_ready:'+str(robot.returncode))
   return request(port,'/status')
  status=wait(ready,100,'pure gateway readiness');assert status['runtime_revision']=='asr-direct-T2-T8-v1'
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
  except OSError:pass
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
   v['method']='ASR_direct_pi05';v['runtime_revision']='asr-direct-T2-T8-v1';v['formal_trial']=bool(item.get('formal_trial'));v['trial_uid']=uid;v['policy_seed']=int(item.get('policy_seed',7));v['test_mode']='actual_PCM_to_Whisper_literal_text_to_pi05; benchmark_truth_for_setup_and_scoring_only';write(result,v)
  else:outcome['audio_played']=False
  if(case/'client/events.jsonl').exists():
   try:
    from audit_pcm import audit
    service=Path(os.environ['RAW_ASR_EVIDENCE_ROOT'])
    quality=audit(case,service);outcome['audio_quality_passed']=quality['passed']
   except Exception as e:outcome['audio_audit_error']=repr(e)
  if item['branch']=='T6':
   asked=(case/'COMMIT.json').exists()
   # No audio output exists in this method, so every legally asked QA fails.
   score=dict(case_id=cid,method='ASR_direct_pi05',asked=asked,planned_eligible=True,qa_denominator=1 if asked else 0,qa_success=False if asked else None,reason='no_answer_audio_in_pure_ASR_architecture'if asked else'not_asked_preparation_or_gate_failed',expected_answers_used=False)
   write(case/'SCORE.json',score);outcome['score']=score
  elif result.exists():
   f=(case/'scoring.console.log').open('w');q=subprocess.run([SIM,'-B',str(R/'code/score_one.py'),cid,str(case),str(case/'SCORE.json')],stdout=f,stderr=subprocess.STDOUT);f.close();outcome['scoring_returncode']=q.returncode
   if q.returncode==0:outcome['score']=read(case/'SCORE.json')
  outcome.update(finished_at=time.time(),elapsed_seconds=time.time()-outcome['started_at'],engine_error=(case/'ENGINE_ERROR.json').exists(),directory=str(case));write(case/'ATTEMPT_OUTCOME.json',outcome)
 return outcome

def run_case(item,run,port):
 if item['branch']!='T6':return run_attempt(item,run,port)
 attempts=[]
 for index in range(1,4):
  outcome=run_attempt(item,run,port,index);attempts.append(outcome)
  # Only fresh pre-question preparation failures are retryable. A sent first
  # question packet permanently fixes this trial, including later errors.
  if outcome.get('score',{}).get('asked')or outcome['status']!='setup_unavailable':break
 uid=outcome['trial_uid'];canonical=run/'cases'/uid;actual=Path(outcome['directory'])
 outcome=dict(outcome,preparation_attempts=[dict(directory=x['directory'],status=x['status'],asked=x.get('score',{}).get('asked'),error=x.get('error'))for x in attempts],canonical_directory=str(canonical),total_elapsed_seconds=sum(x['elapsed_seconds']for x in attempts))
 for name in ['result.json','SCORE.json','spec.json','recordings','policy_inputs','gateway.jsonl','task_events.jsonl','client','voice','t6_physics.private.jsonl','COMMIT.json','TRIAL.json','ENGINE_FINISHED.json','ENGINE_ERROR.json','initial.png','policy_input.mp4']:
  if(actual/name).exists():(canonical/name).symlink_to(actual/name,target_is_directory=(actual/name).is_dir())
 write(canonical/'ATTEMPT_OUTCOME.json',outcome);return outcome

def refresh(run,planned,phase,active=None):
 rows=[read(p)for p in sorted((run/'cases').glob('*/ATTEMPT_OUTCOME.json'))];counts={}
 for branch in ['T2','T3','T4','T5','T6','T7','T8']:
  xs=[x for x in rows if x['branch']==branch];scores=[x.get('score',{})for x in xs]
  counts[branch]=dict(planned=sum(x['branch']==branch for x in planned),finished=len(xs),audio_played=sum(bool(x.get('audio_played'))for x in xs),engineering_errors=sum(x.get('engine_error',False)or x['status']=='technical_or_setup_failure'or x.get('scoring_returncode',0)!=0 for x in xs),scored=sum(bool(x.get('score'))for x in xs))
  for metric in ['interaction','target','instruction','qa_success']:
   values=[]
   for score in scores:
    if isinstance(score.get('rows'),list):score=score['rows'][0]if score['rows']else{}
    v=score.get(metric)
    if type(v)is bool:values.append(v)
    elif v in ['pass','fail']:values.append(v=='pass')
   counts[branch][metric]=dict(success=sum(values),evaluated=len(values))
 progress=dict(updated_beijing=datetime.datetime.now().astimezone().isoformat(),method='ASR_direct_pi05',phase=phase,planned=len(planned),finished=len(rows),active=active,by_branch=counts,scope='only_T2_T8; ASR_Agent_and_Ours_not_launched')
 write(run/'PROGRESS.json',progress);(run/'PROGRESS.md').write_text('# 纯 ASR＋π0.5 T2–T8\n\n'+f"状态：{phase}；完成 {len(rows)}/{len(planned)}。\n\n"+'| 类别 | 计划 | 已结束 | 已评分 | 工程错误 |\n|---|---:|---:|---:|---:|\n'+''.join(f"| {b} | {v['planned']} | {v['finished']} | {v['scored']} | {v['engineering_errors']} |\n"for b,v in counts.items())+'\n当前案例：'+str(active)+'\n\n未完成时不报告最终成功率。原音频、实际转写、策略输入、物理轨迹、视频及逐例评分保存在 cases/。\n')
 return progress

def main():
 p=argparse.ArgumentParser();p.add_argument('--preflight',action='store_true');p.add_argument('--branch');p.add_argument('--run-name');p.add_argument('--continue-existing',action='store_true');p.add_argument('--limit',type=int);p.add_argument('--lane',type=int,default=0);p.add_argument('--lanes',type=int,default=1);p.add_argument('--gpu',type=int,default=6);p.add_argument('--asr',default='ws://127.0.0.1:49440');p.add_argument('--policy',default='http://127.0.0.1:49441');p.add_argument('--port',type=int,default=54301);a=p.parse_args()
 SETTINGS.update(gpu=a.gpu,asr=a.asr,policy=a.policy,port=a.port)
 if not a.preflight:
  assert read(R/'reports/PREFLIGHT_ACCEPTANCE.json')['engineering_ready']is True
  frozen=read(R/'config/FROZEN_SHA256.json')
  for relative,expected in frozen['sha256'].items():
   if hashlib.sha256((R/relative).read_bytes()).hexdigest()!=expected:raise RuntimeError('frozen_source_changed:'+relative)
 items=read(R/('data/PREFLIGHT7.private.json'if a.preflight else'data/FORMAL810.private.json'))
 if a.branch:items=[x for x in items if x['branch']in a.branch.split(',')]
 if not a.preflight:
  groups={b:[x for x in items if x['branch']==b]for b in ['T2','T3','T4','T5','T6','T7','T8']}
  items=[groups[b][i]for i in range(max(map(len,groups.values())))for b in groups if i<len(groups[b])]
 if a.lanes>1:items=[x for i,x in enumerate(items)if i%a.lanes==a.lane]
 if a.limit:items=items[:a.limit]
 run=R/'runs'/(a.run_name or('preflight_v1'if a.preflight else'formal810'));run.mkdir(parents=True,exist_ok=True);(run/'cases').mkdir(exist_ok=True)
 write(run/'REGISTERED.json',items);write(run/'COORDINATOR.json',dict(pid=os.getpid(),started=time.time(),method='ASR_direct_pi05',preflight=a.preflight))
 state='running';consecutive=0
 try:
  for index,item in enumerate(items):
   uid=item.get('trial_uid')or item.get('trial_id')or item['public_case_id']
   if(run/'cases'/uid/'ATTEMPT_OUTCOME.json').exists():
    if a.continue_existing:continue
    raise RuntimeError('refuse_duplicate_trial:'+uid)
   refresh(run,items,state,dict(branch=item['branch'],case_id=item['public_case_id'],trial_uid=uid));print('START',item['branch'],uid,flush=True)
   v=run_case(item,run,SETTINGS['port']);brief={k:v.get('score',{}).get(k)for k in ['interaction','target','instruction','qa_success']};print('END',v['branch'],uid,v['status'],brief,flush=True);consecutive=consecutive+1 if v.get('engine_error')or v['status']=='technical_or_setup_failure'or v.get('scoring_returncode',0)!=0 else 0
   refresh(run,items,state)
   if consecutive>=3:raise RuntimeError('three_consecutive_engineering_failures_circuit_breaker')
  state='completed'
 except BaseException as e:state='stopped_with_error';write(run/'COORDINATOR_ERROR.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
 finally:refresh(run,items,state)

if __name__=='__main__':main()
