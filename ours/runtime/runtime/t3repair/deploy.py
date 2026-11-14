"""Activate reviewed repairs only in a disconnected, empty main episode.

Restarts the owned robot facade only. R8 speech, web, actor model, role pool,
training and other branches' frozen evaluation processes are left running.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

B=Path(__file__).resolve().parents[1]
MAIN=Path('/mnt/disk_2/geyi/voice_pi05_harness')
OUT=B/'reports/deployment'
SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
sys.path.insert(0,str(MAIN/'scripts/live_tests'))
from deploy_interaction_when_idle import safe_to_reload


def request(port,path,authenticated=False):
    headers={'Authorization':'Bearer '+(MAIN/'private/robot.token').read_text().strip()}if authenticated else{}
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(urllib.request.Request(f'http://127.0.0.1:{port}{path}',headers=headers),timeout=5)as r:
        return json.load(r)


def write(state,**details):
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(time=time.time(),state=state,action_model_restarted=False,voice_restarted=False,web_restarted=False,**details)
    (OUT/'DEPLOYMENT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False),flush=True)


def preflight():
    mini=B/'reports/mini3_v2/real_audio_v2'
    audit=json.loads((mini/'REPAIR_AUDIT.json').read_text())
    if not audit['complete']or audit['received']!=3 or audit['runtime_drift']:
        raise RuntimeError('completed three-case evidence required')
    for row in audit['cases']:
        if row['runner_errors']or row['kernel_errors']:
            raise RuntimeError('unresolved transport/kernel error')
    manifest=json.loads((B/'reports/mini3_v2/ARCHIVED_FREEZE.json').read_text())
    for path,digest in manifest['files'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('archived mini runtime drift: '+path)
    smoke=B/'reports/canonical_smoke1/real_audio_canonical'
    if not(smoke/'COMPLETED.json').exists():raise RuntimeError('final integration smoke incomplete')
    verdicts=json.loads((smoke/'reports_audited/v1.9_wait45/verdicts.json').read_text())
    if len(verdicts)!=1 or verdicts[0]['instruction']!='pass':
        raise RuntimeError('final integration physical contract failed')
    # Timing failures remain failures; functional deployment does not relabel SR.
    allowed={'first_action_after_request','first_new_action_within_45s'}
    failures=[c['name']for c in verdicts[0]['checks']if c['status']!='pass']
    if any(name not in allowed for name in failures):
        raise RuntimeError('unresolved functional check: '+str(failures))
    final=json.loads((B/'reports/canonical_smoke1/FREEZE.json').read_text())
    for path,digest in final['files'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('final runtime drift: '+path)
    tests=json.loads((B/'reports/TEST_RESULTS.json').read_text())
    if not tests['passed']:raise RuntimeError('repair regression tests failed')
    return failures


def main():
    deadline_failures=preflight()
    config=MAIN/'configs/unified_execution.local.json'
    before_bytes=config.read_bytes();before_hash=hashlib.sha256(before_bytes).hexdigest()
    old=json.loads(before_bytes)
    signature=None;stable=0
    for _ in range(6):
        s=request(8801,'/status',True);voice=request(8787,'/api/session')
        current=(s.get('episode_id'),s.get('task_version'),s.get('reset_count'))
        if safe_to_reload(s,voice):
            stable=stable+1 if current==signature else 1;signature=current
        else:stable=0;signature=None
        if stable>=3:break
        time.sleep(2)
    if stable<3:
        write('not_deployed_active_main_preserved');return
    s=request(8801,'/status',True);voice=request(8787,'/api/session')
    if not safe_to_reload(s,voice)or signature!=(s['episode_id'],s['task_version'],s['reset_count']):
        write('not_deployed_idle_changed');return
    if hashlib.sha256(config.read_bytes()).hexdigest()!=before_hash:
        raise RuntimeError('parallel profile update; do not overwrite')
    OUT.mkdir(parents=True,exist_ok=True)
    backup=OUT/'original_unified_execution.local.json'
    if backup.exists():raise RuntimeError('deployment already attempted; preserve its evidence')
    backup.write_bytes(before_bytes);os.chmod(backup,0o600)
    (OUT/'pre_reload_status.json').write_text(json.dumps(s,ensure_ascii=False,indent=2))
    spec=json.loads(Path(old['live_spec']).read_text())
    spec.update(case_id='LIVE_MAIN_F28D_R7_T3_1',reset_count=s['reset_count']+1,
                initial_version=s['task_version']+1,previous_episode_id=s['episode_id'])
    specfile=OUT/'live_spec.json';specfile.write_text(json.dumps(spec,indent=2))
    candidate=dict(old,f28d_bundle=str(B),gateway_entry=str(B/'t3repair/service.py'),
                   live_spec=str(specfile),live_output='/mnt/disk_4/geyi/voice_t3_harness_repair_20261102/main_service',
                   freeze_manifest=str(B/'reports/canonical_smoke1/FREEZE.json'))
    # Keep the exact already-running R8 voice artifact: no speech restart needed.
    candidate['voice_bundle_path']=old['voice_bundle_path']
    path=OUT/'candidate_unified_execution.local.json';path.write_text(json.dumps(candidate,indent=2));os.chmod(path,0o600)
    tmp=config.with_suffix('.t3.new');tmp.write_bytes(path.read_bytes());os.chmod(tmp,0o600);tmp.replace(config)
    write('reloading_owned_robot_only',old_episode=s['episode_id'],timing_failures_retained=deadline_failures)
    subprocess.run([SIM,str(MAIN/'scripts/services.py'),'restart','--component','robot'],cwd=MAIN,check=True)
    deadline=time.monotonic()+150
    while time.monotonic()<deadline:
        try:
            fresh=request(8801,'/status',True)
            if fresh.get('ready')and fresh.get('execution_service_revision')=='R7-T3.1':
                assert fresh['state']=='idle'and fresh['task_id']is None and fresh['policy_action_steps']==0
                assert fresh['policy_metadata']==s['policy_metadata']
                write('deployed',new_episode=fresh['episode_id'],revision=fresh['execution_service_revision'],
                      policy_weights_sha256=fresh['policy_metadata']['weights_sha256'],
                      scene_memory=fresh['scene_memory'],timing_failures_retained=deadline_failures)
                return
        except(OSError,ValueError):pass
        time.sleep(1)
    write('verification_failed_no_automatic_second_reload')
    raise RuntimeError('main repair startup verification failed')


if __name__=='__main__':main()
