"""Immutable T6 rounds: two GPU processes, one account audio lease, no splicing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import run_core as core

A = Path(__file__).resolve().parent
B = core.ROOT
W = core.BASE
O = core.OUT
PY = core.SIM

def read(p):
    return json.loads(Path(p).read_text())

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def freeze(label, selected_ids=None):
    root = O/label
    root.mkdir(parents=True, exist_ok=False)
    snapshot = W/'source_archives'/label/'t6_adapter'
    shutil.copytree(A, snapshot, symlinks=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    files = {}
    for p, h in read(B/'run_data/FREEZE.json')['files'].items():
        assert sha(p) == h, ('shared parent changed', p)
        files[p] = h
    for directory in [snapshot, B/'native_prefetch', W/'data', W/'policies', W/'receipt_audio']:
        for p in directory.rglob('*'):
            if p.is_file() and not p.is_symlink() and not any(
                    x in p.parts for x in ['node_modules', '__pycache__']):
                if p.suffix in ['.py', '.mjs', '.js', '.json', '.md'] and not p.name.startswith(
                        ('POLIC', 'NUMERICAL', 'MODEL')):
                    files[str(p)] = sha(p)
    cases = read(W/'data/cases.private.json')
    assert len(cases) == len({c['case_id'] for c in cases}) == 20
    if selected_ids:
        selected = set(selected_ids)
        assert selected <= {c['case_id'] for c in cases}, selected
        cases = [c for c in cases if c['case_id'] in selected]
    pcm = {x['utterance_id']: x for x in read(W/'data/PCM_MANIFEST.json')}
    for case in cases:
        row = pcm[case['question_utterance_id']]
        for field in ['file', 'source_file']:
            files[row[field]] = sha(row[field])
    fixture_path = Path('/mnt/disk_2/geyi/T6_dataset/scenes/LIVE8787_I00/fixture.json')
    files[str(fixture_path)] = sha(fixture_path)
    for asset in read(fixture_path)['assets'].values():
        assert sha(asset['path']) == asset['sha256']
        files[asset['path']] = asset['sha256']
    core.save(root/'cases.private.json', cases)
    protocol = read(W/'data/PROTOCOL.json')
    protocol.update(version='T6-MV20-C3r-recovery-clocked-v5',
        gate_confirmation_clock='five distinct real environment control cycles, including pose holds',
        legacy_policy_action_counter_retained=True,
        same_physical_grasp_predicates=True,
        sampling_clock_adapter_disclosed=True,
        runtime='shared C3r recovery + NativePrefetch + T2/T3 controls + T6 answer-order + image fact review + authorized task records + bounded speech + terminal observations',
        image_review='same current image and public task record, no private scene facts',
        task_record_fallback='after 5s pure task queries only; fresh read-only status; bounded yield of unheard reply only with matching input/version/generation lease; late output fenced; no robot mutation',
        visual_review_budget='14s total visual pipeline; same-image review 5s request, at most one timeout-only retry; no unverified candidate fallback',
        notification_speech='opt-in result speech: 6s attempt, one timeout or rejected fixed-readout retry, 12s total; strict exact-readout and PCM checks retained',
        task_status_language='English-only status sentence for English-only task questions; original task content and actual mode unchanged',
        terminal_observation='real pose-hold physics ticks after terminal state; no policy actions or pause resume',
        evaluation_scope='targeted engineering preflight' if selected_ids else 'full fixed same20 development round')
    core.save(root/'PROTOCOL.json', protocol)
    for file in [root/'cases.private.json', root/'PROTOCOL.json']:
        files[str(file)] = sha(file)
    core.save(root/'FREEZE.json', dict(files=files, snapshot_adapter=str(snapshot), time=time.time()))
    core.save(root/'REGISTERED.json', dict(time=time.time(), planned=len(cases),
        case_ids=[c['case_id'] for c in cases], environment_processes=2,
        GPUs=[1, 2], policy_ports=[29000, 29001], audio_concurrency=1,
        source_snapshot=str(snapshot), previous_target='19/20 qualified audible QA',
        no_post_question_retry=True, no_splicing=True))
    print('FROZEN', label, len(files), flush=True)

def check(root):
    drift = [p for p, h in read(root/'FREEZE.json')['files'].items()
             if not Path(p).exists() or sha(p) != h]
    assert not drift, drift

def worker(index, root, limit=None):
    from tools.audit_case_audio import audit
    cases = read(root/'cases.private.json')
    if limit:
        cases = cases[:limit]
    def stop(*_):
        raise SystemExit('operator stopped owned T6 worker')
    signal.signal(signal.SIGTERM, stop)
    for case in cases:
        if case['original_worker'] != index:
            continue
        if (root/'HALT.json').exists():
            break
        check(root)
        result = core.execute(case, root, index, max_attempts=3)
        if result['qa_started']:
            d = Path(result['committed_directory'])
            quality = audit(d)
            core.save(d/'AUDIO_QUALITY.json', quality)
            if not quality['passed']:
                core.save(root/'HALT.json', dict(reason='invalid_audio_delivery',
                    case_id=case['case_id'], quality=quality, preserve_committed_case=True))
        if core.HALT.is_set():
            core.save(root/'HALT.json', dict(reason='provider_account_denial',
                case_id=case['case_id'], no_success_retries=True))

def progress(root, expected):
    cases = read(root/'cases.private.json')[:expected]
    results = [read(p) for c in cases
               if (p := root/'cases'/c['case_id']/'CASE.json').exists()]
    value = dict(label=root.name, planned=expected, finished=len(results),
        qa_started=sum(x['qa_started'] for x in results),
        total_preparation_attempts=sum(len(x['attempts']) for x in results),
        halted=(root/'HALT.json').exists(), time=time.time())
    core.save(root/'PROGRESS.json', value)
    core.save(W/'PROGRESS.json', value)
    return value

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--worker', type=int, choices=[0, 1])
    parser.add_argument('--preflight', type=int, choices=[2])
    parser.add_argument('--case-id', action='append', help='Targeted engineering preflight only; default is all original 20 cases.')
    args = parser.parse_args()
    if args.freeze:
        freeze(args.label, args.case_id)
        return
    root = O/args.label
    if args.worker is not None:
        worker(args.worker, root, args.preflight)
        return
    check(root)
    snapshot = Path(read(root/'FREEZE.json')['snapshot_adapter'])
    processes, logs = [], []
    began = time.time()
    try:
        for index in [0, 1]:
            log = (root/f'worker{index}.console.log').open('w')
            logs.append(log)
            cmd = [PY, '-u', str(snapshot/'run.py'), '--label', args.label,
                   '--worker', str(index)]
            if args.preflight:
                cmd += ['--preflight', str(args.preflight)]
            processes.append(subprocess.Popen(cmd, cwd=B, stdout=log, stderr=log,
                                              start_new_session=True))
        expected = args.preflight or len(read(root/'cases.private.json'))
        while any(p.poll() is None for p in processes):
            progress(root, expected)
            time.sleep(5)
        value = progress(root, expected)
        codes = [p.returncode for p in processes]
        check(root)
        complete = value['finished'] == expected and codes == [0, 0] and not value['halted']
        core.save(root/('COMPLETED.json' if complete else 'INTERRUPTED.json'),
            dict(value, worker_exit_codes=codes, elapsed_seconds=time.time()-began))
        subprocess.run([PY, '-B', str(snapshot/'tools/harvest_results.py'), str(root)], check=True)
        assert complete, ('Incomplete T6 round', value, codes)
    finally:
        for p in processes:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(90)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
        for log in logs:
            log.close()

if __name__ == '__main__':
    main()
