import sys,time,json,os,subprocess,signal,urllib.request,socket
from pathlib import Path
Q=Path(__file__).resolve().parents[1];B=Q.parents[1];P=Q.parent/'asr_agent_oracle_formal840_240_20261109';N=Q.parent/'ours_full930_readiness_20261114';W=N/'code/runtime_v8';g=json.loads((Q/'scale/GPU_MAP7.json').read_text())
POLICY='/mnt/disk_1/geyi/audio_switch_asr_direct_pi05_20261108/python/bin/python3.11';ASR='/mnt/disk_4/geyi/audio_switch_c3r_cloud04_20261109/envs/rexomni/bin/python'
ps=[];logs=[]
try:
 for lane in range(4,7):
  for port in [28110+lane,28210+lane,28310+lane]:s=socket.socket();s.bind(('127.0.0.1',port));s.close()
  for kind,py,script,args in [('policy',POLICY,W/'runtime/unified/serve_policy.py',['--port',str(28110+lane),'--out',str(Q/'services'/('r7scale7_policy'+str(lane)))]),('asr',ASR,Q/'actors/B0/code/asr_server.py',['--port',str(28210+lane),'--model',str(P/'models/whisper-large-v3'),'--out',str(Q/'services'/('asr'+str(lane)))])]:
   env=dict(os.environ,CUDA_VISIBLE_DEVICES=g['gpu_uuids'][lane],HOME=str(Q/'work/container_home'),OPENPI_DATA_HOME='/mnt/disk_4/geyi/audio_switch_benchmark/deployments/our720_nonoracle_cloud04_240_20261109/container_home/.cache/openpi',PYTHONPATH=str(W/'runtime')+':/mnt/disk_1/geyi/audio_switch_asr_direct_pi05_20261108/compat:/mnt/disk_2/geyi/openpi/.venv/lib/python3.11/site-packages',XLA_PYTHON_CLIENT_PREALLOCATE='false',XLA_PYTHON_CLIENT_MEM_FRACTION='.40',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
   if kind=='asr':env['PYTHONPATH']=str(P/'asr_overlay')
   f=(Q/'logs'/('scaled_'+kind+str(lane)+'.log')).open('x');logs.append(f);ps.append(subprocess.Popen([py,'-B','-u',str(script)]+args,env=env,stdout=f,stderr=f,start_new_session=True))
 pending=set(range(4,7));deadline=time.monotonic()+900;op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 while pending and time.monotonic()<deadline:
  assert all(p.poll()is None for p in ps),'An extra service exited'
  for lane in list(pending):
   try:
    with op.open('http://127.0.0.1:%d/metadata'%(28110+lane),timeout=2)as f:v=json.load(f)
    assert v['complete_task_input_supported']and v['archive_sha256']=='57315913541eb81f40678a75121e15c55c2622bbbe496a75ead7903f61820588'
    if not(Q/'services'/('asr'+str(lane))/'READY.json').exists():continue
    (Q/'scale'/('EXTRA_POLICY'+str(lane)+'.json')).write_text(json.dumps(v,indent=2));pending.remove(lane)
   except(OSError,ValueError):pass
  time.sleep(2)
 assert not pending,'Extra service readiness timeout'
 (Q/'scale/EXTRA_READY.json').write_text(json.dumps(dict(ready=True,lanes=[4,5,6],at=time.time())))
 while not(Q/'scale/STOP_SERVICES').exists():
  assert all(p.poll()is None for p in ps);time.sleep(2)
finally:
 for p in ps:
  if p.poll()is None:
   try:os.killpg(p.pid,signal.SIGTERM)
   except ProcessLookupError:pass
 for p in ps:
  try:p.wait(timeout=20)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
 for f in logs:f.close()
