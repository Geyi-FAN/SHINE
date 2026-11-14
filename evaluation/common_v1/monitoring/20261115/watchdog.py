"""One-minute independent monitor with a small allowlist of operational repairs.

Never modifies actors, scorers or outcomes. Never executes a trial twice.
New, unclassified code faults are bundled for review, not blindly patched.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import time
import traceback
from pathlib import Path
from eta import forecast, stamp

M = Path(__file__).resolve().parent
Q = M.parents[1]
RUN = Q / 'runs/formal1770_v1'
PYTHON = '/mnt/disk_1/geyi/audio_switch_asr_direct_pi05_20261108/python/bin/python3.11'

def read(p):
    return json.loads(p.read_text())

def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_suffix('.tmp')
    t.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    t.replace(p)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def update_ledger(paths, ledger):
    for p in paths:
        digest = sha(p)
        if p.name in ledger:
            assert ledger[p.name] == digest, 'Published first outcome changed: ' + p.name
        else:
            ledger[p.name] = digest
    return ledger

def clean(text):
    return re.sub(r'(?i)(?:Bearer\s+\S+|sk-ws-[\w.=-]+|sk-[\w-]{16,}|ms-[\w-]{24,}|api_key=[^\s&]+)', '[REDACTED]', str(text))

def pids(script):
    result = subprocess.run(['pgrep', '-f', script.name], capture_output=True, text=True, timeout=10)
    found = []
    for value in result.stdout.split():
        try:
            argv = (Path('/proc') / value / 'cmdline').read_bytes().decode().split('\0')
            if command_matches(argv, script):
                found.append(int(value))
        except (OSError, ValueError):
            pass
    return found

def command_matches(argv, script):
    return bool(argv and 'python' in Path(argv[0]).name and any(
        value.startswith('/') and Path(value).resolve() == script.resolve() for value in argv[1:]))

def lock_busy():
    with (Q / 'run.lock').open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True

def blocked_startup_ports(ports=None):
    # The unchanged model-service bootstrap uses a bare bind, so wait for its
    # ports to be fully clear instead of causing a TIME_WAIT startup failure.
    ports = ports if ports is not None else [base+lane for base in [28110,28210,28310] for lane in range(7)]
    blocked = []
    for port in ports:
        try:
            with socket.socket() as s:
                s.bind(('127.0.0.1', port))
        except OSError:
            blocked.append(port)
    return blocked

def decision(complete, explicit_stop, busy, coordinator_alive, partial, service_alive, reason, fatal):
    if explicit_stop or 'Explicit stop requested' in reason:
        return 'user_stopped'
    if complete:
        return 'collection_complete'
    if busy or coordinator_alive:
        return 'observe'
    if partial:
        return 'manual_partial_trial'
    if fatal:
        return 'manual_account_or_model_identity'
    allowed = ['Independent network health did not recover', 'Owned model service exited']
    if reason and not any(x in reason for x in allowed):
        return 'manual_unknown_error'
    if service_alive:
        return 'stop_owned_orphan_services'
    return 'resume_verified_unstarted_only'

def bundle(view, active, error):
    key = hashlib.sha256(json.dumps([view['action'], view['completed'], error], sort_keys=True).encode()).hexdigest()[:12]
    dst = M / 'alerts' / key
    if not dst.exists():
        dst.mkdir(parents=True)
        safe_error = {k: clean(error.get(k, '')) for k in ['type', 'reason', 'traceback']}
        save(dst / 'DIAGNOSIS.json', dict(view=view, error=safe_error, deployment=str(active),
             frozen_protocol_changed=False, response='No arbitrary code patch; preserve first results.'))
        text = '\n'.join((active / 'coordinator.console.log').read_text(errors='replace').splitlines()[-50:]) if (active / 'coordinator.console.log').exists() else ''
        (dst / 'coordinator_tail.txt').write_text(clean(text))
    return str(dst)

def snapshot():
    cfg = read(M / 'CONFIG.json')
    control = read(M / 'CONTROL.json')
    active = Path(control['active_deployment'])
    assert active.parent.resolve() == (Q / 'recovery').resolve()
    status = read(Q / 'STATUS.json')
    observed, parse_errors = [], []
    for p in (RUN / 'outcomes').glob('*.json'):
        try:
            v = read(p)
            assert v['trial_uid'] == p.stem
            observed.append((p.stat().st_mtime, v))
        except (ValueError, OSError, KeyError, AssertionError):
            parse_errors.append(p.name)
    finished = {v['trial_uid'] for _, v in observed}
    assert len(finished) == len(observed), 'Duplicate outcome identities'
    ledger = read(M / 'FIRST_SEEN_SHA.json') if (M / 'FIRST_SEEN_SHA.json').exists() else {}
    update_ledger([RUN / 'outcomes' / (v['trial_uid'] + '.json') for _, v in observed], ledger)
    save(M / 'FIRST_SEEN_SHA.json', ledger)
    cases = {p.name for p in (RUN / 'cases').iterdir()}
    partial = sorted(cases - finished)
    now = time.time()
    error = read(active / 'ERROR.json') if (active / 'ERROR.json').exists() else {}
    reason = str(error.get('reason', ''))
    fatal = False
    for directory in sorted(active.glob('cycle_*'))[-1:]:
        for p in directory.glob('HEALTH_*.json'):
            h = read(p)
            fatal |= bool(h.get('fatal')) or any(x.get('http_status') in [400, 401, 403, 404, 422] for x in h.get('probes', []))
    manager_pids, holder_pids = pids(active / 'coordinator.py'), pids(active / 'services.py')
    action = decision(len(finished) == 1770, (Q / 'STOP_AFTER_CURRENT').exists() or (active / 'STOP').exists(),
                      lock_busy(), bool(manager_pids), bool(partial or parse_errors), bool(holder_pids), reason, fatal)
    if action == 'observe' and not manager_pids:
        action = 'observe_external_coordinator'
    last_end = max((t for t, _ in observed), default=now)
    view = dict(at=now, beijing=stamp(now), phase=status.get('phase'), completed=len(finished), planned=1770,
                infrastructure_errors=status.get('infrastructure_errors'), active_deployment=str(active),
                coordinator_pids=manager_pids, service_holder_pids=holder_pids,
                active_cases=partial, parsing_in_progress=parse_errors, action=action,
                seconds_since_last_finished=now-last_end, relaunches=len(control.get('relaunches', [])),
                automatic_code_patching=False, formal_case_retries=0)
    view['severity'] = 'critical' if action.startswith('manual_') else ('warning' if now-last_end > 300 else 'ok')
    registered = read(RUN / 'REGISTERED.json')
    base_start = read(active / 'SESSION_LOCK.json').get('at', now) if (active / 'SESSION_LOCK.json').exists() else now
    view['eta'] = forecast(registered, observed, now, base_start, status.get('phase'))
    return cfg, control, active, status, observed, view, error

def relaunch(cfg, control, active, observed, view):
    # Exact frozen operational implementation only, never a newly generated patch.
    assert sha(Q / 'plans/FROZEN.json') == cfg['frozen_sha256']
    assert sha(RUN / 'REGISTERED.json') == cfg['registered_sha256']
    template = Path(cfg['template'])
    for name, digest in cfg['template_sources'].items():
        assert sha(template / name) == digest
    assert sha(template / 'RETAINED_SHA.json') == cfg['initial_manifest_sha256']
    assert sha(template / 'DNS_PATCH.json') == cfg['dns_patch_sha256']
    for name, digest in read(template / 'RETAINED_SHA.json').items():
        assert sha(RUN / 'outcomes' / name) == digest
    update_ledger([RUN / 'outcomes' / (v['trial_uid']+'.json') for _, v in observed], read(M / 'FIRST_SEEN_SHA.json'))
    spec = importlib.util.spec_from_file_location('verified_monitor_template', template / 'coordinator.py')
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    core.frozen.verify()
    completed = {v['trial_uid'] for _, v in observed}
    core.todo(read(RUN / 'REGISTERED.json'), completed, {p.name for p in (RUN / 'cases').iterdir()})
    faults = {v['trial_uid']: core.fault_kind(v, RUN / 'cases' / v['trial_uid'])
              for _, v in observed if core.frozen.defect(v)}
    assert all(faults.values()), 'A historical fault is not approved by the frozen classifier'
    recent = [x for x in control.get('relaunches', []) if time.time()-x['at'] < 43200]
    assert len(recent) < 3, 'Three operational restarts in12h already; review required'
    blocked = blocked_startup_ports()
    if blocked:
        view.update(action='waiting_for_owned_ports_to_clear', blocked_ports=blocked)
        return
    value = core.network_check()
    health_path = M / 'health' / ('probe_%d.json' % time.time_ns())
    save(health_path, value)
    if not value['passed']:
        view.update(severity='critical' if value.get('fatal') else 'warning', action='waiting_for_network_health', health=str(health_path))
        return
    assert not lock_busy() and not pids(active / 'coordinator.py') and not pids(active / 'services.py')
    blocked = blocked_startup_ports()
    if blocked:
        view.update(action='waiting_for_owned_ports_to_clear', blocked_ports=blocked)
        return
    dst = Q / 'recovery' / ('network_watch_resume_%d' % int(time.time()))
    dst.mkdir()
    for name in cfg['template_sources']:
        shutil.copy2(template / name, dst / name)
    shutil.copy2(template / 'DNS_PATCH.json', dst / 'DNS_PATCH.json')
    save(dst / 'APPROVED.json', dict(completed=len(observed), planned=1770,
        reviewed_faults=faults, registered_sha256=cfg['registered_sha256'], source_freeze_sha256=cfg['frozen_sha256'],
        autonomous_operational_relaunch=True, actor_scorer_changed=False, at=time.time()))
    save(dst / 'RETAINED_SHA.json', {v['trial_uid']+'.json': sha(RUN / 'outcomes' / (v['trial_uid']+'.json')) for _, v in observed})
    with (dst / 'coordinator.console.log').open('x') as log:
        process = subprocess.Popen([PYTHON, '-B', '-u', str(dst / 'coordinator.py')], stdout=log, stderr=log, start_new_session=True)
    control['active_deployment'] = str(dst)
    control.setdefault('relaunches', []).append(dict(at=time.time(), pid=process.pid, previous=str(active), deployment=str(dst), retained=len(observed)))
    save(M / 'CONTROL.json', control)
    view.update(action='restarted_verified_coordinator', new_deployment=str(dst), relaunch_pid=process.pid)

def main():
    lease = (M / 'monitor.lock').open('a')
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    save(M / 'PID.json', dict(pid=os.getpid(), started=time.time()))
    last_repair = 0
    while not (M / 'STOP').exists():
        try:
            cfg, control, active, status, observed, view, error = snapshot()
            if view['action'].startswith('manual_'):
                view['diagnostic_bundle'] = bundle(view, active, error)
            elif view['action'] == 'stop_owned_orphan_services':
                (active / 'STOP_SERVICES').touch()
                view['action'] = 'requested_owned_service_cleanup'
            elif view['action'] == 'resume_verified_unstarted_only' and time.time()-last_repair > 300:
                blocked = blocked_startup_ports()
                if blocked:
                    view.update(action='waiting_for_owned_ports_to_clear', blocked_ports=blocked)
                else:
                    last_repair = time.time()
                    save(M / 'STATUS.json', dict(view, action='checking_network_before_operational_restart'))
                    relaunch(cfg, control, active, observed, view)
            save(M / 'STATUS.json', view)
            with (M / 'history.jsonl').open('a') as f:
                f.write(json.dumps({k: view.get(k) for k in ['at', 'phase', 'completed', 'action', 'severity']})+'\n')
            if view['action'] == 'collection_complete':
                break
        except Exception as e:
            save(M / 'ERROR.json', dict(at=time.time(), reason=clean(e), traceback=clean(traceback.format_exc())))
            previous = read(M / 'STATUS.json') if (M / 'STATUS.json').exists() else {}
            previous.update(at=time.time(), beijing=stamp(time.time()), severity='critical',
                            action='manual_monitor_error', diagnostic_bundle=str(M / 'ERROR.json'))
            save(M / 'STATUS.json', previous)
        time.sleep(60)
    lease.close()

if __name__ == '__main__':
    main()
