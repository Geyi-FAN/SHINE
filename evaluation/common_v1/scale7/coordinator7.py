"""Deployment-only seven-GPU continuation, same1770 first attempts.

Retain every completed/started four-lane trial. Four speech accounts remain
exclusive to B1 slots0..3. Extra slots4..6 run only B0 (no speech API account).
No actor, model, prompt, scoring, registered waveform/fixture/seed is changed.
"""
from pathlib import Path
import json,os,sys,time,subprocess,threading,concurrent.futures,fcntl,hashlib,traceback
Q=Path(__file__).resolve().parents[1];run=Q/'runs/formal1770_v1';SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python';POLICY='/mnt/disk_1/geyi/audio_switch_asr_direct_pi05_20261108/python/bin/python3.11'
sys.path.insert(0,str(Q/'tools'));import coordinator as legacy
mutex=threading.Lock();halt=threading.Event();services=[];files=[];claimed=set()
def read(p):return json.loads(Path(p).read_text())
def save(p,x):legacy.write(p,x)
def freeze_hashes():return {str(p.relative_to(Q/'scale')):hashlib.sha256(p.read_bytes()).hexdigest()for p in(Q/'scale').glob('*.py')}
def wait_lock():
 lease=(Q/'run.lock').open('a')
 while True:
  try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);return lease
  except BlockingIOError:time.sleep(2)
def collect():return [read(p)for p in(run/'outcomes').glob('*.json')]
def refresh(phase):
 # Same fixed-count progress aggregator as the original frozen dispatcher.
 return legacy.summarize(run,planned,phase)
def launch(container,script,name):
 f=(Q/'logs'/name).open('x');files.append(f);p=subprocess.Popen(['docker','exec',container,SIM,'-B','-u',str(script)],stdout=f,stderr=f,start_new_session=True);services.append(p)
def main():
 global planned,lease
 lease=wait_lock();legacy.verify()
 old=collect();uids={x['trial_uid']for x in old};assert len(uids)==len(old)
 planned=read(run/'REGISTERED.json');assert len(planned)==1770
 assert uids<={x['trial_uid']for x in planned}
 assert not any(legacy.defect(x)for x in old),'A retained infrastructure failure requires separate diagnosis before continuation'
 # Never rerun a started case lacking a completed outcome.
 started={p.name for p in(run/'cases').iterdir()};assert started<=uids,'Partially started case requires recovery; no automatic replay'
 retained={x['trial_uid']:hashlib.sha256((run/'outcomes'/(x['trial_uid']+'.json')).read_bytes()).hexdigest()for x in old}
 save(Q/'scale/RETAINED_DRAINED_SHA.json',retained)
 if(run/'COMPLETED.json').exists():
  (run/'COMPLETED.json').rename(Q/'scale/FOUR_LANE_DRAINED.json')
 if(Q/'STOP_AFTER_CURRENT').exists():(Q/'STOP_AFTER_CURRENT').rename(Q/'scale/FOUR_LANE_DRAIN_REQUEST.json')
 save(Q/'scale/AMENDMENT.json',dict(kind='deployment_only_scale_from4_to7',user_authorization='all server240 GPUs authorized on2026-11-14',retained=len(old),remaining=1770-len(old),source_freeze_sha256=hashlib.sha256((Q/'plans/FROZEN.json').read_bytes()).hexdigest(),old_trial_results_replayed=False,original_registered_trials=1770,physical_gpus=[1,2,3,4,0,5,6],old4_slots='original four-lane mixed-method phase',new7_slots='B1 only in slots0..3; B0 in extra4..6 and idle primary slots',max_concurrent_speech_accounts=4,max_concurrent_planning_requests=4,latency_stratification_required=True,scale_scripts_sha256=freeze_hashes(),gpu_map_sha256=hashlib.sha256((Q/'scale/GPU_MAP7.json').read_bytes()).hexdigest(),at=time.time()))
 (run/'scale_logs').mkdir(exist_ok=True)
 launch('common-oracle-baselines-20261114',Q/'scale/hold_primary_services.py','scale7_primary_services.log')
 launch('common-baselines-extra056-20261114',Q/'scale/hold_extra_services.py','scale7_extra_services.log')
 end=time.monotonic()+1000
 while time.monotonic()<end:
  if any(p.poll()is not None for p in services):raise RuntimeError('Scaled services exited before admission')
  if(Q/'scale/PRIMARY_READY.json').exists()and(Q/'scale/EXTRA_READY.json').exists():break
  time.sleep(2)
 assert(Q/'scale/PRIMARY_READY.json').exists()and(Q/'scale/EXTRA_READY.json').exists(),'Scale service readiness timeout'
 remaining=[x for x in planned if x['trial_uid']not in uids];queues={'B0':[x for x in remaining if x['method']=='B0'],'B1':[x for x in remaining if x['method']=='B1']}
 save(Q/'scale/LAUNCHED.json',dict(lanes=7,retained=len(old),remaining=len(remaining),at=time.time(),first_attempt_only=True))
 def worker(lane):
  container='common-oracle-baselines-20261114'if lane<4 else'common-baselines-extra056-20261114'
  while not halt.is_set()and not(Q/'STOP_AFTER_CURRENT').exists():
   with mutex:
    choices=queues['B1']if lane<4 and queues['B1']else queues['B0']
    if not choices:return
    item=choices.pop(0);uid=item['trial_uid'];assert uid not in claimed;claimed.add(uid)
   legacy.verify();assert freeze_hashes()==read(Q/'scale/AMENDMENT.json')['scale_scripts_sha256'],'Scale dispatcher changed'
   assert hashlib.sha256((Q/'scale/GPU_MAP7.json').read_bytes()).hexdigest()==read(Q/'scale/AMENDMENT.json')['gpu_map_sha256']
   assert not(run/'cases'/uid).exists()and not(run/'outcomes'/(uid+'.json')).exists(),'Refuse repeat registered trial'
   ip=run/'items'/(uid+'.json');save(ip,item)
   with(run/'scale_logs'/(uid+'.log')).open('x')as f:
    p=subprocess.run(['docker','exec',container,SIM,'-B','-u',str(Q/'scale/one_case_scaled.py'),'--item',str(ip),'--run',str(run),'--lane',str(lane)],stdout=f,stderr=f)
   fp=run/'outcomes'/(uid+'.json')
   v=read(fp)if fp.exists()else dict(trial_uid=uid,method=item['method'],branch=item['branch'],case_id=item['public_case_id'],status='orchestration_error',engine_error=True,returncode=p.returncode,score={})
   if not fp.exists():save(fp,v)
   save(run/'scale_logs'/(uid+'.deployment.json'),dict(trial_uid=uid,phase='seven_lane_continuation',lane=lane,container=container,source_freeze_sha256=hashlib.sha256((Q/'plans/FROZEN.json').read_bytes()).hexdigest(),at=time.time()))
   if legacy.defect(v):halt.set();save(run/'INFRASTRUCTURE_STOP.json',dict(trial_uid=uid,at=time.time(),deployment='scale7',first_trial_preserved=True))
   with mutex:refresh('draining_after_error'if halt.is_set()else'running_scaled7')
 with concurrent.futures.ThreadPoolExecutor(max_workers=7)as pool:
  futures=[pool.submit(worker,lane)for lane in range(7)]
  for f in futures:f.result()
 summary=refresh('stopped'if halt.is_set()else'completed')
 for uid,digest in retained.items():assert hashlib.sha256((run/'outcomes'/(uid+'.json')).read_bytes()).hexdigest()==digest,'Retained result changed'
 save(Q/'scale/RETAINED_VERIFY.json',dict(passed=True,retained=len(retained),replayed=0))
 save(run/'COMPLETED.json',{k:v for k,v in summary.items()if k!='rows'})
 if summary['completed']!=1770 or halt.is_set():raise RuntimeError('Scaled formal run stopped; no retries')
finally_marker=Q/'scale/STOP_SERVICES'
if __name__=='__main__':
 try:main()
 except BaseException as e:save(Q/'scale/ERROR.json',dict(type=type(e).__name__,reason=str(e),traceback=traceback.format_exc(),at=time.time()));raise
 finally:
  finally_marker.touch()
  for p in services:
   try:p.wait(timeout=60)
   except subprocess.TimeoutExpired:pass
  for f in files:f.close()
