"""Two owned GPU/environment processes, shared account audio lease, original MX10."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True
B = Path(__file__).resolve().parents[1]
A = B/'t2_adapter'
W = Path('/mnt/disk_2/geyi/t2_c3r_mx10_20261102')
OUT = Path('/mnt/disk_4/geyi/t2_c3r_mx10_20261102')
V = B/'freeze/voice'
PY = '/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
NODE = str(V/'runtime/node-v22.23.3-linux-x64/bin/node')
SLOTS = [dict(gpu=1, policy=28600, gateway=28481, web=28487, voice=28489, child=38481),
         dict(gpu=2, policy=28601, gateway=28581, web=28587, voice=28589, child=38581)]
LEASE = Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102/R9/parallel21/single_voice.lock')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    tmp.replace(path)


def freeze():
    parent = read(B/'run_data/FREEZE.json')
    assert all(sha(p) == h for p, h in parent['files'].items()), 'Shared C3r changed'
    files = dict(parent['files'])
    for directory in [A, B/'native_prefetch', W/'policies', W/'receipt_audio_v2']:
        for p in directory.rglob('*'):
            if p.is_file() and not any(n in p.parts for n in ['node_modules', '__pycache__', 'reports']):
                if p.suffix in ['.py', '.mjs', '.js', '.json', '.md'] and not p.name.startswith(('POLIC', 'MODEL', 'NUMERICAL')):
                    files[str(p)] = sha(p)
    for spec in read(A/'dataset/selected.private.json'):
        for t in spec['turns']:
            p = t['audio_ref']['file']
            assert sha(p) == t['audio_sha256']
            files[p] = sha(p)
        for asset in spec['fixture']['assets'].values():
            assert sha(asset['path']) == asset['sha256']
            files[asset['path']] = asset['sha256']
    files[str(W/'network_route_v1.json')] = sha(W/'network_route_v1.json')
    for directory in [Path('/mnt/disk_2/geyi/voice_t2_diverse120_20261102/scoring'),
                      Path('/mnt/disk_2/geyi/voice_f28d_audio_repair_20261102/repair8')]:
        for p in directory.rglob('*.py'):
            files[str(p)] = sha(p)
    for p in [Path('/mnt/disk_2/geyi/voice_f28d_audio_repair_20261102/artifacts/G22_audio_client.mjs'),
              Path('/mnt/disk_2/geyi/voice_t2_diverse120_20261102/runtime/scripts/audio_switch_benchmark/t2_mainmerge_support/t2_physics_v2.mjs')]:
        files[str(p)] = sha(p)
    p = A/'reports/RUN_FREEZE.json'
    assert not p.exists(), 'Keep old frozen rounds; create a new version after a method change'
    put(p, dict(time=time.time(), files=files, parent_freeze_sha256=sha(B/'run_data/FREEZE.json'),
                method='C3r recovery + R7-T3.2 + NativePrefetch-v1 + R8/T2-control-v3 + ShortAcceptedReceipt-v1',
                input_cases=10, goal='Interaction/Target/Instruction each 10/10',
                retry='only before first pause PCM; never replay enrolled results'))


def check_freeze():
    drift = [p for p, h in read(A/'reports/RUN_FREEZE.json')['files'].items() if sha(p) != h]
    assert not drift, ('frozen_drift', drift)


def stop_owned(processes):
    for p in reversed(processes):
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for p in processes:
        try:
            p.wait(90)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait(10)


def lease_audio(directory):
    handle = LEASE.open('r+b')
    began = time.time()
    fcntl.flock(handle, fcntl.LOCK_EX)
    handle.seek(0)
    ended = float(handle.read().strip() or b'0')
    time.sleep(max(0., 30-(time.time()-ended)))
    put(directory/'AUDIO_LEASE.json', dict(time=time.time(), wait_s=time.time()-began,
        lease=str(LEASE), simultaneous_voice_sessions=1, environments_preheated=2))
    return handle


def run_attempt(spec, directory, slot, engineering=False):
    check_freeze()
    directory.mkdir(parents=True, exist_ok=False)
    fast = Path('/tmp/geyi_t2_c3r_metadata')/hashlib.sha256(str(directory).encode()).hexdigest()[:20]
    fast.mkdir(parents=True, exist_ok=False)
    for n in ['gateway', 'voice', 'review_history']:
        (fast/n).mkdir(mode=0o700)
        (directory/n).symlink_to(fast/n, target_is_directory=True)
    spec = copy.deepcopy(spec)
    spec.update(serve_live=False, robot_port=slot['gateway'], gateway_port=slot['gateway'],
                web_port=slot['web'], state_directory=str(fast/'gateway'), reset_count=1, initial_version=0)
    put(directory/'spec.json', spec)
    conf = read(V/'data/harness/config.json')
    conf.update(port=slot['voice'], backends=[])
    put(fast/'voice/config.json', conf)
    (fast/'voice/config.json').chmod(0o600)
    route = read(W/'network_route_v1.json')
    assert route['websocket_verified'] and route['expires_at'] > time.time()+120, 'Expired route; no audio'
    for key in ['gateway', 'web', 'voice', 'child']:
        with socket.socket() as sock:
            assert sock.connect_ex(('127.0.0.1', slot[key])) != 0, ('port_busy', slot[key])
    env = dict(os.environ, C3R_PROFILE='recovery', VOICE_ROBOT_DATA_DIR=str(fast/'gateway'),
        VOICE_EVAL_RECORD_DIR=str(directory/'recordings'), VOICE_DISCOVERY_FILE=str(fast/'voice/run/daemon.json'),
        VOICE_HISTORY_DIR=str(fast/'review_history'), VOICE_ASR_EVIDENCE_DIR=str(directory/'asr'),
        VOICE_ROBOT_PORT=str(slot['gateway']), VOICE_WEB_PORT=str(slot['web']),
        VOICE_HARNESS_RUNTIME_CONFIG=str(V/'configs/runtime.local.json'),
        VOICE_NETWORK_ROUTE_FILE=str(W/'network_route_v1.json'), PYTHONDONTWRITEBYTECODE='1',
        VOICE_CUMULATIVE_TASK_BUDGET='1', VOICE_BENCHMARK_TICK_LOG='1', VOICE_PRIORITY_STOP='1',
        OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    ve = dict(env, DASHSCOPE_API_KEY=(V/'private/dashscope.key').read_text().strip(),
        QWEN_LIVE_HARNESS_DATA_DIR=str(fast/'voice'), QWEN_LIVE_HARNESS_DISCOVERY_DIR=str(fast/'voice'),
        ROBOT_GATEWAY_URL=f"http://127.0.0.1:{slot['gateway']}", ROBOT_GATEWAY_TOKEN_FILE=str(V/'private/robot.token'),
        ROBOT_AUDIO_BENCHMARK_HOST='1', ROBOT_BROWSER_HOST='1', ROBOT_FAST_STOP='1', ROBOT_AUDIO_RELISTEN='1',
        ROBOT_RECEIPT_AUDIO_DIR=str(W/'receipt_audio_v2'),
        ROBOT_INSTRUCTION_PROMPT_FILE=str(V/'configs/instruction_prompt.txt'),
        ROBOT_AUDIO_RECEIVE_LOG=str(directory/'audio_received.jsonl'))
    children, lease, error = [], None, None
    started = time.time()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def status():
        with opener.open(f"http://127.0.0.1:{slot['web']}/api/status", timeout=3) as response:
            return json.load(response)
    try:
        with (directory/'services.log').open('w') as log:
            commands = [([NODE, str(A/'daemon/dist/index.js'), '--daemon-only'], ve),
                ([PY, '-u', str(A/'service.py'), '--spec', str(directory/'spec.json'), '--out', str(directory),
                  '--port', str(slot['gateway']), '--child-port', str(slot['child']),
                  '--gpu', str(slot['gpu']), '--policy-port', str(slot['policy'])], env),
                ([NODE, str(V/'web_host/server.mjs')], env)]
            for cmd, e in commands:
                children.append(subprocess.Popen(cmd, cwd=V, env=e, stdout=log, stderr=log, start_new_session=True))
            put(directory/'CHILD_PIDS.json', dict(pids=[p.pid for p in children], slot=slot))
            for _ in range(300):
                if any(p.poll() is not None for p in children):
                    raise RuntimeError('isolated_service_startup_failed')
                try:
                    ready = status()
                    if ready.get('ready') and ready.get('execution_readiness', {}).get('ready'):
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(.5)
            else:
                raise TimeoutError('C3r readiness')
            assert ready['execution_kernel'] == 'C3r' and ready['c3r_profile'] == 'recovery'
            assert ready['execution_service_revision'] == 'R7-T3.2+C3r+NativePrefetch-v1'
            assert ready['native_scheduler'] == 'prefetch-frame-aligned-v1'
            assert ready['t2_evaluation_adapter'] == 'MX10-original-contract-v1'
            assert ready['state'] == 'idle' and not ready.get('task_id')
            put(directory/'readiness.json', ready)
            scene = read(directory/'initial_scene.json')
            assert scene['maximum_channel_delta'] <= 2 and scene['mean_delta'] <= .001
            print('READY', spec['case_id'], directory.name, 'GPU', slot['gpu'], flush=True)
            lease = lease_audio(directory)
            if engineering:
                subprocess.run([NODE, str(B/'t1_adapter/connection_probe.mjs'), str(slot['web']), str(directory)],
                               env=env, stdout=log, stderr=log, check=True, timeout=60)
                state = status()
                assert state['state'] == 'idle' and not state['task_id'] and state['policy_action_steps'] == 0
                put(directory/'ENGINEERING_READY.json', dict(time=time.time(), no_task_audio=True,
                    no_authorized_tasks=True, policy_actions=0, status=state))
            else:
                if (directory.parents[3]/'BLOCKED_CLOUD.json').exists():
                    raise InterruptedError('provider blocked; no additional audio')
                p = subprocess.Popen([NODE, str(A/'t2_client.mjs'), str(directory),
                    f"http://127.0.0.1:{slot['web']}", str(directory/'spec.json')], cwd=A,
                    env=env, stdout=log, stderr=log, start_new_session=True)
                children.append(p)
                p.wait(1850)
                if p.returncode:
                    raise RuntimeError('audio_client_exit_'+str(p.returncode))
    except BaseException as exc:
        error = repr(exc)
    finally:
        stop_owned(children)
        if lease is not None:
            lease.seek(0)
            lease.truncate()
            lease.write(str(time.time()).encode())
            lease.flush()
            fcntl.flock(lease, fcntl.LOCK_UN)
            lease.close()
        import shutil
        shutil.copytree(fast, directory/'state_archive', dirs_exist_ok=True)
        for n in ['gateway', 'voice', 'review_history']:
            (directory/n).unlink()
            (directory/n).symlink_to(Path('state_archive')/n, target_is_directory=True)
        if not (directory/'result.json').exists():
            put(directory/'result.json', dict(case_id=spec['case_id'], enrolled=False, trigger_covered=False,
                turns=[], messages=[], errors=[error or 'no_result'], run_status='startup_failed',
                started=dict(time=started), finished=dict(time=time.time())))
        put(directory/'PROCESS.json', dict(started=started, finished=time.time(), error=error,
            processes=[dict(pid=p.pid, returncode=p.poll()) for p in children]))
    if not engineering:
        with (directory/'audio_audit.log').open('w') as log:
            subprocess.run([NODE, str(B/'repair/audit_audio.mjs'), str(directory)], stdout=log, stderr=log, check=False)
    result = read(directory/'result.json')
    print('FINISHED', spec['case_id'], 'enrolled', result.get('enrolled'), result.get('errors'), error, flush=True)
    return result


def worker(index, label, engineering=False, preflight=False):
    root = OUT/label
    cases = read(A/'dataset/selected.private.json')
    cases = cases[:2] if engineering else cases[2:3] if preflight else cases
    selected = cases[index::2]
    for spec in selected:
        case = root/'cases'/spec['case_id']
        case.mkdir(parents=True, exist_ok=False)
        n = 0
        while True:
            n += 1
            d = case/'preparation_attempts'/f'attempt_{n:03d}'
            result = run_attempt(spec, d, SLOTS[index], engineering)
            if engineering:
                assert (d/'ENGINEERING_READY.json').exists(), 'No-audio readiness failed'
                put(case/'CASE_DONE.json', dict(time=time.time(), engineering=True))
                break
            denial = any('Access denied' in p.read_text() for p in (d/'voice/sessions').glob('*.jsonl'))
            if denial:
                put(root/'BLOCKED_CLOUD.json', dict(time=time.time(), case_id=spec['case_id'], directory=str(d)))
                raise RuntimeError('External service blocked; preserve attempts')
            if result.get('enrolled') or (d/'ENROLLED.json').exists():
                (case/'formal').symlink_to(d.relative_to(case), target_is_directory=True)
                put(case/'PREPARATION.json', dict(attempt_count=n, formal_attempt=n))
                subprocess.run([PY, str(A/'score_case.py'), str(case/'formal'), spec['case_id']], check=True)
                put(case/'CASE_DONE.json', dict(time=time.time(), slot=SLOTS[index], verdict=read(d/'score_r8_audited.json')))
                break
            put(case/'PREPARATION_WARNING.json', dict(attempts=n, errors=result.get('errors'),
                same_state_and_audio=True, enrolled=False))
            if n >= 3 and (d/'PROCESS.json').exists() and read(d/'PROCESS.json')['error']:
                raise RuntimeError('Repeated infrastructure startup issue; repair before further preparation')
            time.sleep(30)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--label', required=True)
    p.add_argument('--worker', type=int)
    p.add_argument('--engineering', action='store_true')
    p.add_argument('--preflight', action='store_true')
    args = p.parse_args()
    if args.worker is not None:
        worker(args.worker, args.label, args.engineering, args.preflight)
        return
    check_freeze()
    specs = read(A/'dataset/selected.private.json')
    specs = specs[:2] if args.engineering else specs[2:3] if args.preflight else specs
    root = OUT/args.label
    root.mkdir(parents=True, exist_ok=False)
    put(root/'REGISTERED.json', dict(time=time.time(), count=len(specs), case_ids=[c['case_id'] for c in specs],
        slots=SLOTS, audio_parallelism=1, environment_parallelism=2, first_enrolled_outcome_only=True,
        same_original_audio_state_trigger_budget=True, engineering=args.engineering, preflight=args.preflight))
    children, logs = [], []
    for index in range(min(2, len(specs))):
        log = (root/f'worker{index}.console.log').open('w')
        logs.append(log)
        cmd = [PY, '-u', str(Path(__file__)), '--label', args.label, '--worker', str(index)]
        if args.engineering:
            cmd.append('--engineering')
        if args.preflight:
            cmd.append('--preflight')
        children.append(subprocess.Popen(cmd, cwd=B, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                                        stdout=log, stderr=log))
    while any(p.poll() is None for p in children):
        done = list((root/'cases').glob('*/CASE_DONE.json'))
        put(W/'PROGRESS.json', dict(time=time.time(), label=args.label, planned=len(specs),
            completed=len(done), output=str(root), status='running'))
        time.sleep(3)
    for log in logs:
        log.close()
    if any(p.returncode for p in children):
        put(root/'SCHEDULER_ERROR.json', dict(time=time.time(), returncodes=[p.returncode for p in children],
            preserve_all_attempts=True, no_enrolled_replay=True))
        raise RuntimeError('Worker issue; keep original evidence and diagnose')
    assert len(list((root/'cases').glob('*/CASE_DONE.json'))) == len(specs)
    check_freeze()
    if not args.engineering:
        sys.path[:0] = [str(A/'analysis'), str(A/'tools')]
        from audited_score import aggregate
        s = aggregate(root)
        put(root/'summary.json', s)
    put(root/'COMPLETED.json', dict(time=time.time(), count=len(specs), engineering=args.engineering,
        preflight=args.preflight, method='C3r recovery + R7-T3.2 + NativePrefetch + R8/T2-v3 + ShortAcceptedReceipt-v1'))
    put(W/'PROGRESS.json', dict(time=time.time(), label=args.label, planned=len(specs),
        completed=len(specs), status='completed', output=str(root)))


if __name__ == '__main__':
    main()
