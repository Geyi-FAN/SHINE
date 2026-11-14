"""Local guard: collect/judge only once, after all1770 first trials exist."""
import json
import fcntl
import subprocess
import sys
import time
from pathlib import Path

M = Path(__file__).resolve().parent
Q = M.parents[1]
F = Q / 'finalization/formal1770_v1'
sys.path.insert(0, str(Q.parent / 'c3r_cloud04_240_20261108/tools'))
from remote import connect
from watchdog import pids, save
REMOTE_Q = Path(json.loads((M / 'CONFIG.json').read_text())['remote_deployment_alias'])

def main():
    lease = (M / 'finalizer_guard.lock').open('a')
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    while not (M / 'STOP').exists():
        try:
            c = connect()
            s = c.open_sftp()
            remote = json.loads(s.open(str(REMOTE_Q / 'STATUS.json')).read())
            try:
                s.stat(str(REMOTE_Q / 'STOP_AFTER_CURRENT'))
                requested_stop = True
            except OSError:
                requested_stop = False
            s.close()
            c.close()
            running = pids(Q / 'work/finalize_new.py')
            state = dict(at=time.time(), collection=remote.get('completed'), judge_process_pids=running,
                         no_semantic_rejudging=True)
            if requested_stop:
                state['action'] = 'user_stopped'
            elif running:
                state['action'] = 'existing_finalizer_running'
            elif remote.get('phase') == 'completed' and remote.get('completed') == 1770:
                status = json.loads((F / 'STATUS.json').read_text())
                complete = status.get('phase') == 'collected1770_first_QA_judged90' and (Q / 'reports/final1770/TABLE_COMMON.md').exists()
                if complete and not (F / 'ERROR.json').exists():
                    save(M / 'FINALIZER_STATUS.json', dict(state, action='all_done'))
                    break
                if (F / 'judge90_first').exists() or list((F / 'logs').glob('*')):
                    state['action'] = 'manual_judge_recovery_required_no_rerun'
                elif status.get('phase') == 'waiting_for_complete_formal1770':
                    if (F / 'ERROR.json').exists():
                        (F / 'ERROR.json').rename(M / ('prior_finalizer_error_%d.json' % time.time_ns()))
                    log = M / ('finalizer_guard_launch_%d.log' % time.time_ns())
                    with log.open('x') as f:
                        p = subprocess.Popen([sys.executable, '-B', '-u', str(Q / 'work/finalize_new.py')], stdout=f, stderr=f, start_new_session=True)
                    state.update(action='launched_first_finalizer', pid=p.pid)
                else:
                    state['action'] = 'manual_finalizer_state_review'
            else:
                state['action'] = 'waiting_for_all1770'
            save(M / 'FINALIZER_STATUS.json', state)
        except Exception as e:
            save(M / 'FINALIZER_STATUS.json', dict(at=time.time(), action='connection_or_guard_error', error=type(e).__name__))
        time.sleep(60)
    lease.close()

if __name__ == '__main__':
    main()
