"""15 independent engineering trials, then1770 registered first attempts.

No selective outcome retry. Versioned preflight admission never uses success
rate. All started formal cases keep their first result, including infra errors.
"""
import collections,concurrent.futures,fcntl,hashlib,json,os,signal,subprocess,sys,time,threading,traceback
from pathlib import Path
from services import start,stop
Q=Path(__file__).resolve().parents[1];SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
lock=threading.Lock();halt=threading.Event()
def read(p):return json.loads(Path(p).read_text())
def write(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+'.'+str(os.getpid())+'.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n');t.replace(p)
def source_files():
 paths=[]
 for part in ['common','tools','clients','actors','t6','plans']:
  for p in(Q/part).rglob('*'):
   if p.is_file()and not p.is_symlink()and not any(k in p.parts for k in ['private','node_modules','__pycache__','cache','asr_service'])and p.suffix in ['.py','.mjs','.js','.json','.txt']and p.name!='FROZEN.json':paths.append(p)
 return {str(p.relative_to(Q)):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths}
def verify():
 frozen=read(Q/'plans/FROZEN.json')['files']
 for name,digest in frozen.items():
  if hashlib.sha256((Q/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Frozen comparison source changed:'+name)
def defect(v):
 if not v.get('audio_played')and v.get('branch')!='T6':return True
 if v.get('engine_error')or v.get('scoring_returncode',0)!=0 or v.get('scoring_failed'):return True
 if v.get('audio_played')and v.get('audio_quality_passed')is False:return True
 if v.get('branch')=='T6':return v.get('status')!='collected'or not v.get('audit',{}).get('frame_offsets_passed',False)or bool(v.get('agent_errors'))
 return v.get('status')=='technical_or_setup_failure'
def summarize(run,planned,phase):
 rows=[]
 for p in(run/'outcomes').glob('*.json'):
  try:rows.append(read(p))
  except ValueError:pass
 counts={}
 for method in ['B0','B1']:
  counts[method]={}
  for branch in ['T1','T2','T3','T4','T5','T6','T7','T8']:
   xs=[x for x in rows if x['method']==method and x['branch']==branch];c=dict(planned=sum(x['method']==method and x['branch']==branch for x in planned),completed=len(xs))
   for k in ['interaction','target','instruction']:
    vals=[x.get('score',{}).get(k)for x in xs];c[k]=dict(success=sum(v is True or v=='pass'for v in vals),observed=len([v for v in vals if v not in [None,'na']]))
   counts[method][branch]=c
 value=dict(phase=phase,planned=len(planned),completed=len(rows),infrastructure_errors=sum(defect(x)for x in rows),by_method=counts,rows=rows,time=time.time(),first_attempts_only=True,qa_needs_fixed_judge=True)
 write(run/'PROGRESS.json',value);write(Q/'STATUS.json',{k:v for k,v in value.items()if k!='rows'});return value

def cohort(name,rows,formal):
 halt.clear();run=Q/'runs'/name;run.mkdir(parents=True,exist_ok=False);(run/'outcomes').mkdir();(run/'items').mkdir();(run/'cases').mkdir()
 rows=[dict(x,registration_index=i)for i,x in enumerate(rows)]
 write(run/'REGISTERED.json',rows);write(run/'COORDINATOR.json',dict(pid=os.getpid(),started=time.time(),formal=formal,lanes=4,method_definitions='historical ASR direct and historical restricted-Oracle single Agent; no new planner assistance'))
 def worker(lane):
  for item in rows[lane::4]:
   if halt.is_set()or(Q/'STOP_AFTER_CURRENT').exists():break
   verify();uid=item['trial_uid'];f=run/'items'/(uid+'.json');write(f,item)
   if (run/'outcomes'/(uid+'.json')).exists()or(run/'cases'/uid).exists():raise RuntimeError('Refuse duplicate registered trial')
   with(run/(uid+'.console.log')).open('x')as log:
    p=subprocess.run([SIM,'-B','-u',str(Q/'tools/one_case.py'),'--item',str(f),'--run',str(run),'--lane',str(lane)],stdout=log,stderr=log)
   fp=run/'outcomes'/(uid+'.json')
   value=read(fp)if fp.exists()else dict(trial_uid=uid,method=item['method'],branch=item['branch'],case_id=item['public_case_id'],status='orchestration_error',engine_error=True,returncode=p.returncode,score={})
   if not fp.exists():write(fp,value)
   if defect(value):halt.set();write(run/'INFRASTRUCTURE_STOP.json',dict(trial_uid=uid,at=time.time(),first_result_preserved=True))
   with lock:summarize(run,rows,'draining_after_error'if halt.is_set()else'running')
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:
  futures=[pool.submit(worker,i)for i in range(4)]
  for f in futures:f.result()
 final=summarize(run,rows,'stopped'if halt.is_set()else'completed')
 write(run/'COMPLETED.json',{k:v for k,v in final.items()if k!='rows'})
 if final['completed']!=len(rows)or halt.is_set():raise RuntimeError('Cohort stopped; all first attempts retained; no automatic retry')
 return final

def main():
 lease=(Q/'run.lock').open('a');fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 processes=[];logs=[]
 try:
  # Common scoring must process actual Ours evidence before any baseline audio.
  with(Q/'logs'/('ours_common_smoke_'+os.environ.get('COMMON_CANDIDATE','r2')+'.log')).open('x')as f:subprocess.run([SIM,'-B','-u',str(Q/'tools/regrade_ours.py'),'--mode','smoke'],stdout=f,stderr=f,check=True)
  write(Q/'plans/FROZEN.json',dict(version='three-method-common-oracle-v1-20261114',frozen_at=time.time(),files=source_files(),run_parameters=dict(policy_seed=7,repetitions=3,max_lanes=4),no_outcome_retries=True))
  processes,logs=start()
  result=cohort('preflight15_'+os.environ.get('COMMON_CANDIDATE','r2'),read(Q/'plans/PREFLIGHT15.private.json'),False)
  write(Q/'reports/PREFLIGHT_ACCEPTANCE.json',dict(engineering_ready=True,completed=result['completed'],physics_success_not_an_admission_gate=True,formal_started=False))
  verify()
  # Full same-scorer Ours regrade runs independently and changes no actions.
  f=(Q/'logs/ours_common_full.log').open('x');review=subprocess.Popen([SIM,'-B','-u',str(Q/'tools/regrade_ours.py'),'--mode','full'],stdout=f,stderr=f,start_new_session=True)
  rows=read(Q/'plans/REGISTERED1770.private.json')
  # Balance conditions and task families across lanes rather than running all
  # of one category before the others. Registration still fixes every trial.
  groups=collections.defaultdict(list)
  for x in rows:groups[(x['method'],x['branch'])].append(x)
  ordered=[groups[k][i]for i in range(max(map(len,groups.values())))for k in sorted(groups)if i<len(groups[k])]
  cohort('formal1770_v1',ordered,True)
  review.wait();f.close()
  if review.returncode:raise RuntimeError('Ours common full regrade failed; see retained evidence')
 except BaseException as e:
  write(Q/'reports/COORDINATOR_ERROR.json',dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc(),at=time.time()));raise
 finally:stop(processes,logs)
if __name__=='__main__':main()
