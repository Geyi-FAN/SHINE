"""Explicit isolated launchers; no downloads, service restart or automatic retry."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import urllib.request

W=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(W/'runtime'))


def free_port(port):
    if not 1024<int(port)<65536 or int(port) in (8787,8801):
        raise ValueError('Use an explicitly reserved isolated port; main ports are prohibited')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',int(port)))


def verify_assets(c):
    receipt=json.loads(Path(c['checkpoint_receipt']).read_text())
    if not receipt['passed'] or receipt['checkpoint_step']!=30000 or receipt['archive_sha256']!=c['checkpoint_archive_sha256']:
        raise ValueError('Checkpoint extraction identity mismatch')
    if hashlib.sha256(Path(c['normalization_file']).read_bytes()).hexdigest()!=c['normalization_sha256']:
        raise ValueError('Normalization fingerprint changed')
    root=Path(c['checkpoint']).parent
    for row in receipt['files']:
        p=root/row['path']
        if not p.is_file() or p.stat().st_size!=row['bytes']:
            raise ValueError('Checkpoint member absent or size changed: '+str(p))
    return dict(normalization_rehashed=True,checkpoint='receipt and member sizes; no fresh parameter rehash')


def verify_freeze():
    from verify_freeze import verify
    result=verify(W)
    if not result['passed']:raise RuntimeError('Frozen files changed: '+str(result))


def new_output(path):
    path=path.resolve()
    if path==W or path in W.parents or (W in path.parents and W/'runs' not in path.parents):
        raise ValueError('Logs must be in runs/ or an external fresh output')
    path.mkdir(parents=True,exist_ok=False)
    return path


def token():
    path=Path(os.environ['HARNESS_ROBOT_TOKEN_FILE']).resolve()
    if not path.is_file() or not path.read_text().strip():raise ValueError('Missing private gateway token')
    return path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='mode',required=True)
    policy=sub.add_parser('policy');policy.add_argument('--gpu',type=int,required=True);policy.add_argument('--port',type=int,required=True);policy.add_argument('--out',type=Path,required=True)
    robot=sub.add_parser('robot');robot.add_argument('--gpu',type=int,required=True);robot.add_argument('--port',type=int,required=True);robot.add_argument('--child-port',type=int,required=True);robot.add_argument('--policy-port',type=int,required=True);robot.add_argument('--spec',type=Path,required=True);robot.add_argument('--out',type=Path,required=True)
    voice=sub.add_parser('voice');voice.add_argument('--port',type=int,required=True);voice.add_argument('--robot-port',type=int,required=True);voice.add_argument('--private-config',type=Path,required=True);voice.add_argument('--out',type=Path,required=True);voice.add_argument('--audio-benchmark',action='store_true',help='Admit the authenticated headless replay Host without an OS shortcut')
    sub.add_parser('check')
    a=p.parse_args();c=json.loads((W/'config/model.json').read_text())
    verify_freeze();assets=verify_assets(c)
    if a.mode=='check':print(json.dumps(dict(code_freeze=True,assets=assets)));return
    free_port(a.port)
    env=dict(os.environ,PYTHONPATH=str(W/'runtime'),PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    if a.mode=='policy':
        out=new_output(a.out)
        env.update(CUDA_VISIBLE_DEVICES=str(a.gpu),XLA_PYTHON_CLIENT_MEM_FRACTION='.65',XLA_PYTHON_CLIENT_PREALLOCATE='false')
        command=[c['policy_python'],'-m','unified.serve_policy','--port',str(a.port),'--out',str(out)]
    elif a.mode=='robot':
        free_port(a.child_port)
        if len({a.port,a.child_port,a.policy_port})!=3:raise ValueError('Ports must be distinct')
        token()
        from unified.actor import Pi05HTTPClient
        Pi05HTTPClient(port=a.policy_port).get_server_metadata()
        spec=json.loads(a.spec.read_text())
        if spec.get('state_directory'):raise ValueError('Shared state_directory overrides are prohibited')
        if not spec.get('case_id') or not isinstance(spec.get('fixture'),dict):raise ValueError('A fixture spec is required')
        out=new_output(a.out)
        command=[c['simulation_python'],'-m','unified.service','--spec',str(a.spec.resolve()),'--out',str(out),'--gpu',str(a.gpu),'--port',str(a.port),'--child-port',str(a.child_port),'--policy-port',str(a.policy_port),'--python',c['simulation_python']]
    else:
        key=token()
        if a.robot_port in (8787,8801) or a.robot_port==a.port:raise ValueError('A separate robot gateway is required')
        url='http://127.0.0.1:'+str(a.robot_port)
        request=urllib.request.Request(url+'/status',headers={'Authorization':'Bearer '+key.read_text().strip()})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request,timeout=10) as response:status=json.load(response)
        if not status.get('ready') or status.get('runtime_revision')!=c['runtime_revision'] or status.get('execution_kernel')!='C3r':raise ValueError('Robot runtime not ready or does not match this release')
        config=json.loads(a.private_config.read_text())
        if config.get('realtimeModel', 'qwen3.8-omni-flash-realtime')!='qwen3.8-omni-flash-realtime':raise ValueError('Different realtime model requires a new runtime identity')
        out=new_output(a.out);private=out/'private';private.mkdir(mode=0o700)
        config.update(port=a.port,defaultCwd=str(W),realtimeModel='qwen3.8-omni-flash-realtime')
        cfg=private/'config.json';cfg.write_text(json.dumps(config,ensure_ascii=False,indent=2));cfg.chmod(0o600)
        env.update(ROBOT_GATEWAY_URL=url,ROBOT_GATEWAY_TOKEN_FILE=str(key),QWEN_LIVE_HARNESS_DATA_DIR=str(private),QWEN_LIVE_HARNESS_DISCOVERY_DIR=str(private),QWEN_LIVE_HARNESS_PORT=str(a.port),QWEN_LIVE_HARNESS_CWD=str(W))
        from voice_profile import activate
        env.update(activate(W,out))
        env.update(ROBOT_BROWSER_HOST='1',ROBOT_AUDIO_BENCHMARK_HOST='1' if a.audio_benchmark else '0')
        command=[c['node'],str(W/'voice/dist/index.js'),'--daemon-only']
    (out/'launch_identity.json').write_text(json.dumps(dict(runtime_revision=c['runtime_revision'],mode=a.mode,port=a.port,checkpoint=c['checkpoint'],code_root=str(W)),indent=2))
    print('Starting isolated '+a.mode+'; no existing process will be stopped',flush=True)
    os.execve(command[0],command,env)


if __name__=='__main__':main()
