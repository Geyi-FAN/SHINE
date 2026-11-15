"""Drain after transport faults, probe health, then admit only unstarted trials.

All formal model generations keep retries=0. All first results, including
errors, stay in the original1770 denominator. Unknown defects stop the run.
"""
import concurrent.futures
import errno
import fcntl
import hashlib
import importlib.util
import json
import socket
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
spec = importlib.util.spec_from_file_location('frozen_dispatcher', Q / 'tools/coordinator.py')
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)
sys.path.insert(0, str(R))
from network_health import check as network_check

def read(p):
    return json.loads(p.read_text())

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def todo(registered, completed, started):
    ids = [v['trial_uid'] for v in registered]
    assert len(ids) == len(set(ids))
    assert set(completed) <= set(ids)
    assert set(started) == set(completed), 'Partially started case: no automatic replay'
    return [v for v in registered if v['trial_uid'] not in completed]

def ensure_ports_reusable(ports, timeout=20):
    """Match HTTPServer's SO_REUSEADDR while rejecting a real live listener."""
    deadline = time.monotonic() + timeout
    for port in ports:
        while True:
            try:
                with socket.socket() as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(('127.0.0.1', port))
                break
            except OSError as e:
                if e.errno != errno.EADDRINUSE or time.monotonic() >= deadline:
                    raise
                time.sleep(.25)

REVIEWED_AUDIO_FAILURES = {'B0:T7:T7AC1_OV_T04_N_I00:R03': {'audit_sha256': '2456b026251784e8b0e1f6975608a4e2f2601527ff9c160c9ab282d140bd0917', 'outcome_sha256': 'fb610c7a56d914f6f461618dbc672b6e433533e0b97b02f9d839d0f3f6c27481'}, 'B1:T3:T3S50_OV_S10_I00:R03': {'audit_sha256': '9187827a9a8fef44753d09d847b0e1334a2b36672f3e82fa71ef6a9ce1909762', 'outcome_sha256': 'f4aace0625d43213d816f8500f0ea070f7a90576cdde211baa6d1d2941d88457'}, 'B1:T4:T4C1_CL_T09_I00:R03': {'audit_sha256': '18c29beb5aa2ed890225ebeb7a9e3f38e8c221f980ca84fa249506b43521f92f', 'outcome_sha256': 'ec99430e7f4de4e24fdd9b832bedf656a1c371e2e122db978765d73f5dadbcdc'}}

def fault_kind(value, case):
    # Exact historical exceptions remain failed audio admission; no regrade or replay.
    approved_audio = REVIEWED_AUDIO_FAILURES.get(value.get("trial_uid"))
    if approved_audio and value.get("audio_quality_passed") is False:
        audit = case / "AUDIO_QUALITY.json"
        outcome = case.parent.parent / "outcomes" / (value["trial_uid"] + ".json")
        if (audit.exists() and outcome.exists()
                and sha(audit) == approved_audio["audit_sha256"]
                and sha(outcome) == approved_audio["outcome_sha256"]
                and value.get("scoring_returncode") == 0
                and not value.get("engine_error") and not value.get("scoring_failed")
                and all(c.get("exact_received_pcm") is True for c in read(audit)["clips"])):
            return "reviewed_audio_pacing_failure_retained"

    # Evidence, audio or scoring defects are never waived as network outages.
    if value.get('scoring_failed') or value.get('scoring_returncode', 0) != 0 or value.get('audio_quality_passed') is False:
        return None
    if value.get('branch') == 'T6' and not value.get('audit', {}).get('frame_offsets_passed'):
        return None
    texts = [str(value.get('final_status', {}).get('last_error') or '')] + [str(v) for v in value.get('agent_errors', [])]
    transport_timeout = False
    for p in (case / 'agent_calls').glob('*/transport.json'):
        v = read(p)
        if v.get('status') == 'error':
            texts.extend([str(v.get('error', '')), str(v.get('detail', ''))])
            transport_timeout |= v.get('error') in ['TimeoutError', 'URLError'] and 'timed out' in v.get('detail', '')
    text = ' '.join(texts)
    if 'Access denied' in text or 'HTTP 401' in text or 'HTTP 403' in text or '1007' in text:
        return None
    if 'Temporary failure in name resolution' in text:
        return 'dns_failure'
    if any('HTTP ' + str(c) in text for c in [429, 500, 502, 503, 504]):
        return 'upstream_http_error'
    if 'The read operation timed out' in text or transport_timeout:
        return 'upstream_timeout'
    if (value.get('status') == 'client_finished' and value.get('audio_played') and value.get('audio_quality_passed')
            and value.get('scoring_returncode') == 0
            and any('timeout:' in str(e) for e in value.get('client_errors', []))
            and value.get('final_status', {}).get('agent_execution', {}).get('phase') == 'planning'
            and not (case / 'ENGINE_FINISHED.json').exists()
            and any(not (p.parent / 'transport.json').exists()
                    and not (p.parent / 'response.json').exists()
                    for p in (case / 'agent_calls').glob('*/request.json'))):
        return 'unfinished_agent_request_at_client_deadline'
    return None

def main():
    lease = (Q / 'run.lock').open('a')
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not (R / 'SESSION_LOCK.json').exists(), 'Create a new deployment directory to restart this supervisor'
    frozen.verify()
    approved = read(R / 'APPROVED.json')
    registered = read(RUN / 'REGISTERED.json')
    retained = read(R / 'RETAINED_SHA.json')
    assert len(registered) == approved['planned'] == 1770
    assert len(retained) == approved['completed']
    assert sha(RUN / 'REGISTERED.json') == approved['registered_sha256']
    assert sha(Q / 'plans/FROZEN.json') == approved['source_freeze_sha256']
    for name, digest in retained.items():
        assert sha(RUN / 'outcomes' / name) == digest
    completed = {p.stem for p in (RUN / 'outcomes').glob('*.json')}
    assert completed == {n[:-5] for n in retained}
    todo(registered, completed, {p.name for p in (RUN / 'cases').iterdir()})
    old_bad = [v for p in (RUN / 'outcomes').glob('*.json') if frozen.defect(v := read(p))]
    assert {v['trial_uid'] for v in old_bad} == set(approved['reviewed_faults'])
    assert all(fault_kind(v, RUN / 'cases' / v['trial_uid']) for v in old_bad)
    scale = read(Q / 'scale/AMENDMENT.json')
    for name, digest in scale['scale_scripts_sha256'].items():
        assert sha(Q / 'scale' / name) == digest
    assert sha(Q / 'scale/GPU_MAP7.json') == scale['gpu_map_sha256']
    for name, cfg in read(R / 'DNS_PATCH.json')['containers'].items():
        assert subprocess.check_output(['docker', 'exec', name, 'cat', '/etc/resolv.conf']).decode() == cfg['after']
    signature = {p.name: sha(p) for p in R.glob('*.py')}
    frozen.write(R / 'SESSION_LOCK.json', dict(source_sha256=signature, registered=1770,
        retained=len(retained), remaining=len(registered)-len(retained),
        max_recovery_cycles=128, max_health_attempts_per_cycle=3,
        max_concurrent_cloud_requests=4, physical_gpus=[1, 2, 3, 4, 0, 5, 6],
        actor_or_scorer_changed=False, formal_request_retries=0, active_evaluation_lanes=[0, 1, 2, 3], at=time.time()))
    snapshot = R / 'initial_stop'
    snapshot.mkdir()
    for p in [RUN / 'COMPLETED.json', RUN / 'INFRASTRUCTURE_STOP.json']:
        if p.exists():
            p.rename(snapshot / p.name)
    for lane in range(7):
        p = Q / 'services' / ('asr' + str(lane)) / 'READY.json'
        if p.exists():
            p.rename(snapshot / ('asr%d_READY.json' % lane))
    (R / 'logs').mkdir()
    processes, files = [], []
    cycle = 0

    def progress(phase):
        v = frozen.summarize(RUN, registered, phase)
        public = {k: x for k, x in v.items() if k != 'rows'}
        public.update(recovery_cycle=cycle, automatic_network_admission=True,
                      completed_formal_trials_replayed=0, unknown_errors_require_review=True)
        frozen.write(Q / 'STATUS.json', public)
        return v

    def check_frozen():
        frozen.verify()
        assert {p.name: sha(p) for p in R.glob('*.py')} == signature
        assert sha(Q / 'scale/GPU_MAP7.json') == scale['gpu_map_sha256']
        assert sha(Q / 'scale/one_case_scaled.py') == scale['scale_scripts_sha256']['one_case_scaled.py']
        assert all(p.poll() is None for p in processes), 'Owned model service exited'

    try:
        for group, container in [('primary', 'common-oracle-baselines-20261114'), ('extra', 'common-baselines-extra056-20261114')]:
            f = (R / 'logs' / (group + '_supervisor.log')).open('x')
            files.append(f)
            processes.append(subprocess.Popen(['docker', 'exec', container, SIM, '-B', '-u',
                str(R / 'services.py'), group], stdout=f, stderr=f, start_new_session=True))
        deadline = time.monotonic() + 1000
        while not all((R / (s + '_READY.json')).exists() for s in ['PRIMARY', 'EXTRA']):
            assert time.monotonic() < deadline and all(p.poll() is None for p in processes), 'Model readiness failed'
            time.sleep(2)
        while True:
            check_frozen()
            completed = {p.stem for p in (RUN / 'outcomes').glob('*.json')}
            remaining = todo(registered, completed, {p.name for p in (RUN / 'cases').iterdir()})
            if not remaining:
                break
            if (Q / 'STOP_AFTER_CURRENT').exists() or (R / 'STOP').exists():
                raise RuntimeError('Explicit stop requested; no automatic continuation')
            assert cycle <= 128, 'Network recovery budget exhausted'
            wave = R / ('cycle_%02d' % cycle)
            wave.mkdir()
            progress('network_health_admission')
            healthy = False
            for attempt in range(3):
                value = network_check()
                frozen.write(wave / ('HEALTH_%02d.json' % attempt), value)
                if value['passed']:
                    healthy = True
                    break
                if value.get('fatal'):
                    break
                if attempt < 2:
                    time.sleep(30)
            assert healthy, 'Independent network health did not recover; no new formal cases dispatched'
            # No previous gateway may survive an interrupted case.
            ensure_ports_reusable(range(28310, 28317))
            halt, mutex = threading.Event(), threading.Lock()
            faults, claimed = [], set()
            queues = {m: [v for v in remaining if v['method'] == m] for m in ['B0', 'B1']}
            progress('running_auto_network_admission')

            def worker(lane):
                container = 'common-oracle-baselines-20261114' if lane < 4 else 'common-baselines-extra056-20261114'
                try:
                    while not halt.is_set() and not (Q / 'STOP_AFTER_CURRENT').exists() and not (R / 'STOP').exists():
                        with mutex:
                            choices = queues['B1'] if lane < 4 and queues['B1'] else queues['B0']
                            if not choices:
                                return
                            item = choices.pop(0)
                            uid = item['trial_uid']
                            assert uid not in claimed and uid not in completed
                            claimed.add(uid)
                        check_frozen()
                        assert not (RUN / 'cases' / uid).exists() and not (RUN / 'outcomes' / (uid + '.json')).exists()
                        ip = RUN / 'items' / (uid + '.json')
                        frozen.write(ip, item)
                        with (RUN / 'scale_logs' / (uid + '.log')).open('x') as f:
                            proc = subprocess.run(['docker', 'exec', container, SIM, '-B', '-u',
                                str(Q / 'scale/one_case_scaled.py'), '--item', str(ip), '--run', str(RUN), '--lane', str(lane)], stdout=f, stderr=f)
                        target = RUN / 'outcomes' / (uid + '.json')
                        v = read(target) if target.exists() else dict(trial_uid=uid, method=item['method'],
                            branch=item['branch'], case_id=item['public_case_id'], status='orchestration_error', engine_error=True, score={})
                        if not target.exists():
                            frozen.write(target, v)
                        frozen.write(RUN / 'scale_logs' / (uid + '.deployment.json'), dict(
                            trial_uid=uid, lane=lane, cycle=cycle, deployment=str(R), no_retry=True, at=time.time()))
                        with mutex:
                            if frozen.defect(v):
                                halt.set()
                                faults.append(dict(trial_uid=uid, kind=fault_kind(v, RUN / 'cases' / uid)))
                            progress('draining_after_error' if halt.is_set() else 'running_auto_network_admission')
                except BaseException:
                    halt.set()
                    raise

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(worker, lane) for lane in range(4)]
                for future in futures:
                    future.result()
            frozen.write(wave / 'DRAINED.json', dict(faults=faults, at=time.time(), original_first_results_retained=True))
            assert all(x['kind'] for x in faults), 'Unclassified defect: no automatic continuation'
            for name, digest in retained.items():
                assert sha(RUN / 'outcomes' / name) == digest
            cycle += 1
        final = progress('completed')
        frozen.write(RUN / 'COMPLETED.json', {k: v for k, v in final.items() if k != 'rows'})
    except BaseException:
        final = progress('stopped')
        frozen.write(RUN / 'COMPLETED.json', {k: v for k, v in final.items() if k != 'rows'})
        raise
    finally:
        (R / 'STOP_SERVICES').touch()
        for p in processes:
            try:
                p.wait(timeout=60)
            except subprocess.TimeoutExpired:
                pass
        for f in files:
            f.close()
        lease.close()

if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        frozen.write(R / 'ERROR.json', dict(type=type(e).__name__, reason=str(e), traceback=traceback.format_exc(), at=time.time()))
        raise
