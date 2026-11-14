"""Restart only this evaluation's model services, using the frozen seven-GPU map."""
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

R = Path(__file__).resolve().parent
Q = R.parents[1]
sys.path.insert(0, str(Q / 'tools'))
from services import start, stop

def main(group):
    processes, logs = [], []
    try:
        if group == 'primary':
            os.environ['COMMON_CANDIDATE'] = 'r7_network_admission_v3'
            processes, logs = start()
        else:
            g = json.loads((Q / 'scale/GPU_MAP7.json').read_text())
            P = Q.parent / 'asr_agent_oracle_formal840_240_20261109'
            W = Q.parent / 'ours_full930_readiness_20261114/code/runtime_v8'
            policy = '/mnt/disk_1/geyi/audio_switch_asr_direct_pi05_20261108/python/bin/python3.11'
            asr = '/mnt/disk_4/geyi/audio_switch_c3r_cloud04_20261109/envs/rexomni/bin/python'
            for lane in range(4, 7):
                for port in [28110 + lane, 28210 + lane, 28310 + lane]:
                    with socket.socket() as s:
                        s.bind(('127.0.0.1', port))
                for kind, py, script, args in [
                    ('policy', policy, W / 'runtime/unified/serve_policy.py',
                     ['--port', str(28110 + lane), '--out', str(Q / 'services' / ('r7_network_admission_v3_policy' + str(lane)))]),
                    ('asr', asr, Q / 'actors/B0/code/asr_server.py',
                     ['--port', str(28210 + lane), '--model', str(P / 'models/whisper-large-v3'),
                      '--out', str(Q / 'services' / ('asr' + str(lane)))])]:
                    env = dict(os.environ, CUDA_VISIBLE_DEVICES=g['gpu_uuids'][lane],
                               HOME=str(Q / 'work/container_home'),
                               OPENPI_DATA_HOME='/mnt/disk_4/geyi/audio_switch_benchmark/deployments/our720_nonoracle_cloud04_240_20261109/container_home/.cache/openpi',
                               PYTHONPATH=str(W / 'runtime') + ':/mnt/disk_1/geyi/audio_switch_asr_direct_pi05_20261108/compat:/mnt/disk_2/geyi/openpi/.venv/lib/python3.11/site-packages',
                               XLA_PYTHON_CLIENT_PREALLOCATE='false', XLA_PYTHON_CLIENT_MEM_FRACTION='.40',
                               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
                    if kind == 'asr':
                        env['PYTHONPATH'] = str(P / 'asr_overlay')
                    f = (R / 'logs' / ('extra_' + kind + str(lane) + '.log')).open('x')
                    logs.append(f)
                    processes.append(subprocess.Popen([py, '-B', '-u', str(script)] + args,
                                     env=env, stdout=f, stderr=f, start_new_session=True))
            pending = set(range(4, 7))
            deadline = time.monotonic() + 900
            op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            while pending and time.monotonic() < deadline:
                assert all(p.poll() is None for p in processes), 'Extra service exited'
                for lane in list(pending):
                    try:
                        with op.open('http://127.0.0.1:%d/metadata' % (28110 + lane), timeout=2) as f:
                            md = json.load(f)
                        assert md['complete_task_input_supported']
                        assert md['archive_sha256'] == '57315913541eb81f40678a75121e15c55c2622bbbe496a75ead7903f61820588'
                        assert md['normalization_sha256'] == 'b3a44bb2810436fb62917decaea58bd4d9110255df527dea21e8fd40c960bd84'
                        if not (Q / 'services' / ('asr' + str(lane)) / 'READY.json').exists():
                            continue
                        (R / ('POLICY' + str(lane) + '.json')).write_text(json.dumps(md, indent=2))
                        pending.remove(lane)
                    except (OSError, ValueError):
                        pass
                time.sleep(2)
            assert not pending, 'Extra model readiness timeout'
        (R / (group.upper() + '_READY.json')).write_text(json.dumps(dict(ready=True, at=time.time())))
        while not (R / 'STOP_SERVICES').exists():
            assert all(p.poll() is None for p in processes), 'An owned service exited'
            time.sleep(2)
    finally:
        stop(processes, logs)

if __name__ == '__main__':
    main(sys.argv[1])
