"""Never silently share GPUs with existing compute jobs, regardless of owner."""
import os,subprocess
for gpu in os.environ['CUDA_VISIBLE_DEVICES'].split(','):
 text=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
 pids=[x.strip() for x in text.splitlines() if x.strip().isdigit()]
 if pids:raise RuntimeError(f'GPU {gpu} has active compute processes {pids}. Stop only authorized own jobs before launching.')
print('Selected GPUs have no active compute jobs',flush=True)
