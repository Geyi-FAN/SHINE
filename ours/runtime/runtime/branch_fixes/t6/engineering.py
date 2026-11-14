"""Two independent C3r environments and real voice readiness, zero task audio."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import run_core as core

A = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--worker', type=int, choices=[0, 1])
    args = p.parse_args()
    root = core.OUT/'engineering_v1'
    if args.worker is None:
        root.mkdir(parents=True, exist_ok=False)
        children, logs = [], []
        for i in [0, 1]:
            log = (root/f'worker{i}.console.log').open('w')
            logs.append(log)
            children.append(subprocess.Popen([core.SIM, '-u', str(A/'engineering.py'),
                            '--worker', str(i)], stdout=log, stderr=log))
        codes = [c.wait() for c in children]
        for log in logs:
            log.close()
        core.save(root/'COMPLETED.json', dict(ready=codes==[0, 0],
                  exit_codes=codes, task_audio_frames=0, actual_policy_actions=0))
        assert codes == [0, 0], codes
        return
    case = json.loads((core.BASE/'data/cases.private.json').read_text())[args.worker]
    runtime = core.Runtime(root/f'worker{args.worker}', case, args.worker)
    try:
        runtime.start()
        runtime.connect_voice()
        s = runtime.status()
        assert s.get('policy_action_steps') == 0, s.get('policy_action_steps')
        core.save(runtime.folder/'ENGINEERING_READY.json', dict(time=time.time(),
                  state=s, task_audio_frames=0, actual_policy_actions=0))
    finally:
        runtime.close()

if __name__ == '__main__':
    main()
