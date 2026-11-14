"""Continue only unstarted registered trials after a diagnosed cloud HTTP 500.

Frozen actors/scorer/audio/fixtures are unchanged. Preserve all 247 first
attempts, including the failed cloud call; do not retry any model generation.
"""
import concurrent.futures
import fcntl
import hashlib
import json
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

R = Path(__file__).resolve().parent
Q = R.parents[1]
RUN = Q / 'runs/formal1770_v1'
SIM = '/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
sys.path.insert(0, str(Q / 'tools'))
import coordinator as frozen

def read(p):
    return json.loads(p.read_text())

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def validate():
    frozen.verify()
    approved = read(R / 'INCIDENT_AUDIT.json')
    assert read(R / 'API_HEALTH.json')['passed'], 'Cloud health not admitted'
    assert digest(RUN / 'REGISTERED.json') == approved['registered_sha256']
    assert digest(Q / 'plans/FROZEN.json') == approved['source_freeze_sha256']
    retained = read(R / 'RETAINED247_SHA.json')
    assert len(retained) == 247
    assert {p.name for p in (RUN / 'outcomes').glob('*.json')} == set(retained)
    for name, sha in retained.items():
        assert digest(RUN / 'outcomes' / name) == sha, 'Retained first attempt changed'
    uids = {p[:-5] for p in retained}
    assert {p.name for p in (RUN / 'cases').iterdir()} == uids, 'Partial trial: no automatic replay'
    old = [read(RUN / 'outcomes' / p) for p in retained]
    known = [x for x in old if frozen.defect(x)]
    assert len(known) == 1 and known[0]['trial_uid'] == 'B1:T2:T2COL1_NS_G01:R02'
    assert 'cloud01 HTTP 500' in known[0]['final_status']['last_error']
    planned = read(RUN / 'REGISTERED.json')
    remaining = [x for x in planned if x['trial_uid'] not in uids]
    assert len(remaining) == 1523 and len(planned) == 1770
    scale = read(Q / 'scale/AMENDMENT.json')
    for name, sha in scale['scale_scripts_sha256'].items():
        assert digest(Q / 'scale' / name) == sha, 'Original deployment changed'
    assert digest(Q / 'scale/GPU_MAP7.json') == scale['gpu_map_sha256']
    return approved, retained, uids, known, planned, remaining, scale

def main():
    lease = (Q / 'run.lock').open('a')
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    approved, retained, uids, known, planned, remaining, scale = validate()
    own_sources = {p.name: digest(p) for p in R.glob('*.py')}
    frozen.write(R / 'CONTINUATION_LOCK.json', dict(
        retained=247, remaining=1523, failed_trial_retained=known[0]['trial_uid'],
        no_trial_or_generation_retry=True, source_sha256=own_sources,
        original_freeze_sha256=approved['source_freeze_sha256'],
        registered_sha256=approved['registered_sha256'],
        gpu_map_sha256=scale['gpu_map_sha256'], original_seven_lane_amendment_preserved=True,
        concurrency_unchanged=7, planning_and_speech_concurrency=4, at=time.time()))
    backup = R / 'stopped_snapshot'
    backup.mkdir(exist_ok=False)
    for source in [RUN / 'COMPLETED.json', RUN / 'INFRASTRUCTURE_STOP.json']:
        if source.exists():
            source.rename(backup / source.name)
    # Clear only stale readiness indicators, preserving them in the incident record.
    for lane in range(7):
        p = Q / 'services' / ('asr' + str(lane)) / 'READY.json'
        if p.exists():
            p.rename(backup / ('asr%d_READY.json' % lane))
    (R / 'logs').mkdir(exist_ok=True)
    halt = threading.Event()
    mutex = threading.Lock()
    processes, files = [], []
    queues = {m: [x for x in remaining if x['method'] == m] for m in ['B0', 'B1']}
    claimed = set()
    try:
        frozen.summarize(RUN, planned, 'restarting_services_retained247')
        for group, container in [('primary', 'common-oracle-baselines-20261114'),
                                 ('extra', 'common-baselines-extra056-20261114')]:
            f = (R / 'logs' / (group + '_supervisor.log')).open('x')
            files.append(f)
            processes.append(subprocess.Popen(['docker', 'exec', container, SIM, '-B', '-u',
                             str(R / 'services.py'), group], stdout=f, stderr=f, start_new_session=True))
        deadline = time.monotonic() + 1000
        while time.monotonic() < deadline:
            assert all(p.poll() is None for p in processes), 'Service supervisor exited'
            if all((R / (g + '_READY.json')).exists() for g in ['PRIMARY', 'EXTRA']):
                break
            time.sleep(2)
        assert all((R / (g + '_READY.json')).exists() for g in ['PRIMARY', 'EXTRA']), 'Service readiness timeout'
        frozen.write(R / 'LAUNCHED.json', dict(retained=247, remaining=1523, at=time.time(), no_replays=True))
        frozen.summarize(RUN, planned, 'running_scaled7_resumed')

        def worker(lane):
            container = 'common-oracle-baselines-20261114' if lane < 4 else 'common-baselines-extra056-20261114'
            while not halt.is_set() and not (Q / 'STOP_AFTER_CURRENT').exists():
                with mutex:
                    choices = queues['B1'] if lane < 4 and queues['B1'] else queues['B0']
                    if not choices:
                        return
                    item = choices.pop(0)
                    uid = item['trial_uid']
                    assert uid not in claimed and uid not in uids
                    claimed.add(uid)
                frozen.verify()
                assert {p.name: digest(p) for p in R.glob('*.py')} == own_sources
                assert digest(Q / 'scale/one_case_scaled.py') == scale['scale_scripts_sha256']['one_case_scaled.py']
                assert digest(Q / 'scale/GPU_MAP7.json') == scale['gpu_map_sha256']
                assert not (RUN / 'cases' / uid).exists() and not (RUN / 'outcomes' / (uid + '.json')).exists()
                ip = RUN / 'items' / (uid + '.json')
                frozen.write(ip, item)
                with (RUN / 'scale_logs' / (uid + '.log')).open('x') as f:
                    p = subprocess.run(['docker', 'exec', container, SIM, '-B', '-u',
                        str(Q / 'scale/one_case_scaled.py'), '--item', str(ip), '--run', str(RUN),
                        '--lane', str(lane)], stdout=f, stderr=f)
                target = RUN / 'outcomes' / (uid + '.json')
                value = read(target) if target.exists() else dict(trial_uid=uid, method=item['method'],
                    branch=item['branch'], case_id=item['public_case_id'], status='orchestration_error',
                    engine_error=True, returncode=p.returncode, score={})
                if not target.exists():
                    frozen.write(target, value)
                frozen.write(RUN / 'scale_logs' / (uid + '.deployment.json'),
                    dict(trial_uid=uid, phase='seven_lane_continuation_after_cloud500', lane=lane,
                         container=container, incident_record=str(R), at=time.time()))
                if frozen.defect(value):
                    halt.set()
                    frozen.write(RUN / 'INFRASTRUCTURE_STOP.json', dict(
                        trial_uid=uid, at=time.time(), deployment='resume_after_cloud500', first_trial_preserved=True))
                with mutex:
                    frozen.summarize(RUN, planned, 'draining_after_error' if halt.is_set() else 'running_scaled7_resumed')

        with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
            futures = [pool.submit(worker, i) for i in range(7)]
            for future in futures:
                future.result()
        final = frozen.summarize(RUN, planned, 'completed' if not halt.is_set() else 'stopped')
        for name, sha in retained.items():
            assert digest(RUN / 'outcomes' / name) == sha
        frozen.write(R / 'RETAINED_VERIFY.json', dict(passed=True, preserved=247, replayed=0))
        frozen.write(RUN / 'COMPLETED.json', {k: v for k, v in final.items() if k != 'rows'})
        assert final['completed'] == 1770 and not halt.is_set(), 'New interruption; all first attempts retained'
    finally:
        (R / 'STOP_SERVICES').touch()
        for p in processes:
            try:
                p.wait(timeout=60)
            except subprocess.TimeoutExpired:
                pass
        for f in files:
            f.close()

if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        frozen.write(R / 'ERROR.json', dict(type=type(e).__name__, reason=str(e), traceback=traceback.format_exc(), at=time.time()))
        raise
