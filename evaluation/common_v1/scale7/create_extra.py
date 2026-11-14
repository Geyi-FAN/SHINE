from pathlib import Path
import json,subprocess
Q=Path('/mnt/disk_4/geyi/audio_switch_benchmark/deployments/common_scoring_oracle_baselines_20261114');P=Q.parent/'asr_agent_oracle_formal840_240_20261109';old='common-oracle-baselines-20261114';new='common-baselines-extra056-20261114'
v=json.loads(subprocess.check_output(['docker','inspect',old]).decode())[0];env=dict(x.split('=',1)for x in v['Config']['Env'])
cmd=['docker','run','-d','--name',new,'--network','host','--ipc','host','--entrypoint','/bin/bash','--gpus','"device=0,5,6"','--user',v['Config']['User'],'--volumes-from',old+':rw']
for k in ['PATH','PYTHONPATH','PYTHON_BIN','LD_LIBRARY_PATH','LIBERO_CONFIG_PATH','HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','TOKENIZERS_PARALLELISM','MUJOCO_GL','PYOPENGL_PLATFORM','NVIDIA_DRIVER_CAPABILITIES']:
 if k in env:cmd+=['-e',k+'='+env[k]]
cmd+=['-e','HOME='+str(Q/'work/container_home'),'-e','PYTHONDONTWRITEBYTECODE=1','-w',str(Q),v['Image'],'-lc','exec sleep infinity']
id=subprocess.check_output(cmd).decode().strip();(Q/'scale/EXTRA_CONTAINER.json').write_text(json.dumps(dict(name=new,id=id,physical_gpus=[0,5,6],no_other_containers_restarted=True),indent=2)+'\n');print(new,id)
