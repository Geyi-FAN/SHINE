"""T7 isolated runtime and causal physical helpers. Never changes main services."""
import hashlib,json,os,shutil,socket,subprocess,sys,time,urllib.request,urllib.error
from pathlib import Path

ORIGINAL=Path('/mnt/disk_2/geyi/voice_pi05_harness')
BASE=Path('/mnt/disk_4/geyi/audio_switch_benchmark_dev_v1/t7_waiting_v2_20261101')
ROOT=Path(__file__).resolve().parents[2]
WEIGHTS='30a620085ba28b8faec160ae68a9276d705ec0fb6d2fc9237e706379d0c5eebc'
NORMALIZATION='d4e03a22ef5d89a910e32c233a509465ad0d265381a06745917d69fd8924a635'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)

def snapshot():
    """Copy business sources and built SDK; share only installed dependencies/assets."""
    out=BASE/'runtime'
    if out.exists():return out
    out.mkdir(parents=True,mode=0o700)
    prefixes=['sim_dependency','robot_gateway','hybrid_planner','scripts','web_host','configs','docs','skills']
    sdk=Path('vendor/Qwen-Live-Harness/packages/qwen-live-harness')
    sources=[]
    for folder in prefixes+[str(sdk/'dist')]:
        for p in (ORIGINAL/folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and 'node_modules' not in p.parts:
                sources.append(p)
    sources += [ORIGINAL/'package.json',ORIGINAL/sdk/'package.json']
    before={str(p.relative_to(ORIGINAL)):sha(p) for p in sources}
    for p in sources:
        dest=out/p.relative_to(ORIGINAL);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    changed=[k for k,v in before.items() if sha(ORIGINAL/k)!=v]
    if changed:raise RuntimeError('Sources changed during snapshot; preserve and make a new snapshot: '+str(changed))
    for rel in ['runtime','node_modules','vendor/Qwen-Live-Harness/node_modules',str(sdk/'node_modules')]:
        dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():dest.symlink_to(ORIGINAL/rel,target_is_directory=True)
    (out/'private').symlink_to(ORIGINAL/'private',target_is_directory=True)
    for rel in ['data/receipt_audio','data/visual_atlas_v2']:
        shutil.copytree(ORIGINAL/rel,out/rel,dirs_exist_ok=True)
    (out/'data/harness').mkdir(parents=True)
    shutil.copy2(ORIGINAL/'data/harness/config.json',out/'data/harness/config.json')
    os.chmod(out/'data/harness/config.json',0o600)
    (out/'data/libero').mkdir(parents=True)
    sys.path.insert(0,str(ORIGINAL/'scripts'))
    from project_config import load_runtime
    runtime=load_runtime(ORIGINAL)
    allowed=['evaluation_root','pi05_project','pi05_python','node','checkpoint','openpi_data_home','robot_python',
             'pi05_gpu','robot_gpu','xla_memory_fraction','expected_experiment','expected_checkpoint_step']
    dump(out/'configs/runtime.local.json',{k:str(runtime[k]) for k in allowed})
    dump(BASE/'SNAPSHOT.json',dict(created_at=time.time(),root=str(out),source_hashes=before,
                                  dependency_links='preinstalled Node/Playwright only; business sources and SDK dist are copied',
                                  runtime_config_note='absolute path adaptation only',main_services_modified=False))
    return out

def environment(root=ROOT):
    env=dict(os.environ,VOICE_EXECUTION_MODE='agent',VOICE_SCENE_MEMORY='1',HYBRID_PLANNER_BACKEND='qwen',
             HYBRID_AGENT_MODEL='qwen3.8-max',HYBRID_M2_CURRENT_ONLY='0',HYBRID_STATIC_CACHE='1',
             HYBRID_EPISODE_OBJECT_MEMORY='1',HYBRID_EXECUTOR='smolvla_e3_v4',HYBRID_YOLO_DEVICE='6',
             MUJOCO_EGL_DEVICE_ID='5',VOICE_EVAL_TASK_WALL_SECONDS='600',VOICE_BENCHMARK_TICK_LOG='1',
             VOICE_REALTIME_CONNECT_TIMEOUT_MS='25000',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',
             OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    loaded=subprocess.run(['bash','-c','source "$1/hybrid_planner/env.sh" >/dev/null; env -0','loader',str(root)],
                          env=env,capture_output=True,check=True)
    env.update(dict(x.decode().split('=',1) for x in loaded.stdout.split(b'\0') if b'=' in x))
    config=json.loads((root/'configs/unified_execution.local.json').read_text())
    paths=[p.replace(str(ORIGINAL/'hybrid_planner'),str(root/'hybrid_planner'))
           for p in env.get('PYTHONPATH','').split(':') if p]
    env.update(VOICE_SIM_SCRATCH_ROOT=str(BASE/'sim_scratch_disk4'),PYTHONPATH=':'.join(dict.fromkeys([str(root/'sim_dependency'),str(root/'hybrid_planner'),str(root),*paths,
                '/mnt/disk_4/geyi/smolvla_eval','/mnt/disk_4/geyi/smolvla_eval/smolvla_switch/vendor'])),
               HYBRID_HARNESS_HOME=str(root),HYBRID_YOLO_DEVICE='6',HYBRID_EXECUTOR='smolvla_e3_v4',
               HYBRID_POLICY_PORT=str(config['policy_port']),HYBRID_CHECKPOINT=config['checkpoint'])
    env.pop('VOICE_NETWORK_ROUTE_FILE',None)
    return env

def health(root=ROOT):
    c=json.loads((root/'configs/unified_execution.local.json').read_text())
    m=json.load(urllib.request.urlopen(f'http://127.0.0.1:{c["policy_port"]}/health',timeout=10))
    assert m['weights_sha256']==WEIGHTS and m['normalization_sha256']==NORMALIZATION
    assert m['executor']=='smolvla_e3_v4' and m['checkpoint']==c['checkpoint']
    return m

def fixtures():
    data=Path('/mnt/disk_4/geyi/audio_switch_benchmark_dev_v1/t1_single_turn_v1_20261031/evaluation_90/dataset')
    return {s['native_init_index'] if 'native_init_index' in s else s['init_index']:s for s in json.loads((data/'initial_states.json').read_text())}

def request(port,path,body=None,root=ROOT,timeout=8):
    token=(root/'private/robot.token').read_text().strip()
    req=urllib.request.Request(f'http://127.0.0.1:{port}'+path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    deadline=time.monotonic()+15
    while True:
        try:
            with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)
        except urllib.error.HTTPError as exc:
            # GET state is read-only; never retry a possibly committed mutation.
            if body is not None or exc.code!=503 or time.monotonic()>=deadline:raise
            with (BASE/'READ_ONLY_RETRIES.jsonl').open('a') as log:
                log.write(json.dumps(dict(time=time.time(),port=port,path=path,status=503,method='GET'))+'\n')
            time.sleep(.15)

def ticks(directory,episode):
    path=Path(directory)/'recordings'/episode/'control_ticks.jsonl'
    if not path.exists():return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def tail_tick(directory,episode):
    path=Path(directory)/'recordings'/episode/'control_ticks.jsonl'
    if not path.exists():return None
    with path.open('rb') as f:
        f.seek(max(0,path.stat().st_size-30000));lines=f.read().splitlines()
    for line in reversed(lines):
        try:return json.loads(line)
        except ValueError:continue
    return None

def ready(window,goal,rules):
    """Independent causal completion; no controller completed or next-stage truth."""
    from t1_contract import GOALS,goal_flag
    from benchmark_metrics.events import restore_window
    w=window[-5:]
    if len(w)<5 or not all(goal_flag(t,goal) is True for t in w):return False
    obj=GOALS[goal][2]
    if obj:
        if not all(obj in t.get('measurements',{}) for t in w):return False
        rows=[t['measurements'][obj] for t in w]
        if not restore_window(rows,dict(reference_position=rows[-1]['object_position'],stable_required=True,withdraw_required=False),1e6,rules)['complete']:return False
    return True

def stop_processes(processes):
    import signal
    for p in reversed(processes):
        if p.poll() is None:os.killpg(p.pid,signal.SIGTERM)
    for p in processes:
        try:p.wait(timeout=12)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()

def frozen_hashes(root=ROOT):
    prefixes=['sim_dependency','robot_gateway','hybrid_planner','web_host','configs','skills','scripts','vendor/Qwen-Live-Harness/packages/qwen-live-harness/dist']
    return {str(p.relative_to(root)):sha(p) for folder in prefixes for p in (root/folder).rglob('*')
            if p.is_file() and p.suffix in ['.py','.mjs','.js','.json','.txt','.md','.sh','.yaml','.yml','.toml'] and '__pycache__' not in p.parts}
