"""Own processes only. No shared service kills; no key values in commands."""
from pathlib import Path
import json,os,subprocess,time,urllib.request,signal,socket
Q=Path(__file__).resolve().parents[1];N=Q.parent/'ours_full930_readiness_20261114';P=Q.parent/'asr_agent_oracle_formal840_240_20261109';W=N/'code/runtime_v8'
POLICY='/mnt/disk_1/geyi/audio_switch_asr_direct_pi05_20261108/python/bin/python3.11'
ASR='/mnt/disk_4/geyi/audio_switch_c3r_cloud04_20261109/envs/rexomni/bin/python'
def read(p):return json.loads(Path(p).read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2)+'\n')
def start():
 (Q/'services').mkdir(exist_ok=True);processes=[];logs=[]
 gpu=read(N/'reports/GPU_MAP.json')
 try:
  for lane in range(4):
   for port in [28110+lane,28210+lane,28310+lane]:
    s=socket.socket();s.bind(('127.0.0.1',port));s.close()
   for kind,python,script,args in [
    ('policy',POLICY,W/'runtime/unified/serve_policy.py',['--port',str(28110+lane),'--out',str(Q/'services'/(__import__('os').environ.get('COMMON_CANDIDATE','r2')+'_policy'+str(lane)))]),
    ('asr',ASR,Q/'actors/B0/code/asr_server.py',['--port',str(28210+lane),'--model',str(P/'models/whisper-large-v3'),'--out',str(Q/'services'/('asr'+str(lane)))])]:
    home=Q/'work/container_home';home.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,HOME=str(home),OPENPI_DATA_HOME='/mnt/disk_4/geyi/audio_switch_benchmark/deployments/our720_nonoracle_cloud04_240_20261109/container_home/.cache/openpi',CUDA_VISIBLE_DEVICES=gpu['gpu_uuids'][lane],PYTHONPATH=str(W/'runtime')+':/mnt/disk_1/geyi/audio_switch_asr_direct_pi05_20261108/compat:/mnt/disk_2/geyi/openpi/.venv/lib/python3.11/site-packages',XLA_PYTHON_CLIENT_PREALLOCATE='false',XLA_PYTHON_CLIENT_MEM_FRACTION='.40',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    if kind=='asr':env['PYTHONPATH']=str(P/'asr_overlay')
    f=(Q/'logs'/(kind+str(lane)+'.log')).open('a');logs.append(f)
    p=subprocess.Popen([python,'-B','-u',str(script)]+args,env=env,stdout=f,stderr=f,start_new_session=True);processes.append(p)
  save(Q/'reports/OWN_SERVICE_PIDS.json',[dict(pid=p.pid)for p in processes])
  op=urllib.request.build_opener(urllib.request.ProxyHandler({}));pending=set(range(4));deadline=time.monotonic()+900
  while pending and time.monotonic()<deadline:
   for p in processes:
    if p.poll()is not None:raise RuntimeError('Own service exited '+str(p.pid)+':'+str(p.returncode))
   for lane in list(pending):
    try:
     with op.open('http://127.0.0.1:%d/metadata'%(28110+lane),timeout=2)as f:md=json.load(f)
     assert md['complete_task_input_supported']and md['archive_sha256']=='57315913541eb81f40678a75121e15c55c2622bbbe496a75ead7903f61820588'
     assert md['normalization_sha256']=='b3a44bb2810436fb62917decaea58bd4d9110255df527dea21e8fd40c960bd84'
     if not(Q/'services'/('asr'+str(lane))/'READY.json').exists():continue
     save(Q/'reports'/('policy'+str(lane)+'_metadata.json'),md);pending.remove(lane)
    except(OSError,ValueError):pass
   save(Q/'STATUS.json',dict(phase='loading_own_services',pending=sorted(pending),time=time.time()));time.sleep(2)
  if pending:raise RuntimeError('Own model readiness timeout: '+str(pending))
  save(Q/'reports/SERVICES_READY.json',dict(ready=True,lanes=4,gpu=gpu,method_policy='explicit complete_task or symbolic; effective prompt hash logged',time=time.time()))
  return processes,logs
 except BaseException:
  stop(processes,logs);raise

def stop(processes,logs):
 for p in processes:
  if p.poll()is None:
   try:os.killpg(p.pid,signal.SIGTERM)
   except ProcessLookupError:pass
 for p in processes:
  try:p.wait(timeout=20)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
 for f in logs:f.close()
