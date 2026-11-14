"""Host PID-to-GPU attribution via actual NVIDIA graphics process telemetry."""
from pathlib import Path
import json,subprocess,time,xml.etree.ElementTree as ET
Q=Path(__file__).resolve().parents[1];C='common-baselines-extra056-20261114';SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
ps=[];logs=[]
for egl in range(3):
 f=(Q/'logs'/('extra_renderer_probe'+str(egl)+'.log')).open('x');logs.append(f)
 ps.append(subprocess.Popen(['docker','exec',C,SIM,'-B',str(Q/'scale/probe_renderer.py'),'--egl',str(egl),'--out',str(Q/'scale'/('probe'+str(egl)))],stdout=f,stderr=f))
end=time.monotonic()+180;mapping={}
while len(mapping)<3 and time.monotonic()<end:
 for i,p in enumerate(ps):
  if p.poll()is not None and i not in mapping:raise RuntimeError('Renderer probe exited; see logs')
 top=subprocess.check_output(['docker','top',C,'-eo','pid,args']).decode().splitlines()[1:]
 pids={}
 for row in top:
  if str(Q/'scale/probe_renderer.py')in row:
   pid,args=row.strip().split(None,1)
   for egl in range(3):
    if '--egl '+str(egl)+' 'in args:pids[int(pid)]=egl
 xml=ET.fromstring(subprocess.check_output(['nvidia-smi','-q','-x']))
 for gpu in xml.findall('gpu'):
  for p in gpu.findall('./processes/process_info'):
   pid=int(p.findtext('pid')or'0')
   if pid in pids:
    egl=pids[pid];ready=Q/'scale'/('probe'+str(egl))/'READY.json'
    if ready.exists():mapping[egl]=dict(egl=egl,gpu_uuid=gpu.findtext('uuid'),host_pid=pid,initial_scene_verified=True)
 time.sleep(.5)
assert len(mapping)==3,('Could not identify actual graphics allocation',mapping)
base=json.loads((Q.parent/'ours_full930_readiness_20261114/reports/GPU_MAP.json').read_text())
extra=['GPU-fb1e5622-4cf0-b3a0-884c-86d124225b5e','GPU-71511ac9-bf3e-06c9-2620-216537ef126c','GPU-31e6bf57-3d2c-d29a-f58d-82b74d177d59']
byuuid={x['gpu_uuid']:x['egl']for x in mapping.values()};assert set(byuuid)==set(extra)
g=dict(base);g['physical_gpus']=[1,2,3,4,0,5,6];g['gpu_uuids']=base['gpu_uuids']+extra;g['renderer_egl_by_lane']=base['renderer_egl_by_lane']+[byuuid[u]for u in extra];g['extra_probe_rows']=mapping;g['container_by_lane']=['common-oracle-baselines-20261114']*4+[C]*3
(Q/'scale/GPU_MAP7.json').write_text(json.dumps(g,indent=2)+'\n')
for egl in range(3):(Q/'scale'/('probe'+str(egl))/'STOP').touch()
for p in ps:p.wait(timeout=30)
for f in logs:f.close()
print(json.dumps(dict(verified=True,extra_gpu_renderers=mapping,physical_gpus=g['physical_gpus'])))
