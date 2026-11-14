"""Serial 6-case technical admission then a separately registered 90-case run."""
import argparse,collections,fcntl,hashlib,json,os,signal,subprocess,sys,time,traceback,urllib.request
from pathlib import Path
from collect import extract
ROOT=Path(__file__).resolve().parents[1];PARENT=ROOT.parent

DATA=Path('/mnt/disk_4/geyi/audio_switch_benchmark/T6/current')
PREFIX=Path('/mnt/disk_4/geyi/audio_switch_benchmark/T6/releases/t6-prefix-v2-20261108')
ACTOR=PARENT/'actors/B1'
SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
NODE='/mnt/disk_2/geyi/voice_pi05_harness/runtime/node-v22.23.3-linux-x64/bin/node'
PORT=int(os.environ['COMMON_GATEWAY_PORT'])
TOKEN=(ACTOR/'private/robot.token').read_text().strip()
OP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
TASKS={1:'Put the bowl on the stove.',2:'Put the wine bottle on top of the cabinet.',3:'Open the top drawer and put the bowl inside.',4:'Put the bowl on top of the cabinet.',6:'Put the cream cheese in the bowl.',8:'Put the bowl on the plate.',9:'Put the wine bottle on the rack.'}
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.tmp');t.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n');t.replace(p)
def request(path,body=None):
    q=urllib.request.Request('http://127.0.0.1:'+str(PORT)+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+TOKEN})
    with OP.open(q,timeout=5)as f:return json.load(f)
def network_wait():
    while True:
        value=health.network_probe();save(ROOT/'NETWORK.json',value)
        if value['ok']:return
        if value.get('fatal'):raise RuntimeError('fatal network admission: '+str(value))
        time.sleep(30)
def one(item,run,index):
    cid=item['case_id'];case=run/'cases'/item['trial_uid'];case.mkdir(parents=True,exist_ok=False)
    output=dict(case_id=cid,trial_uid=item['trial_uid'],branch='T6',method='B1',directory=str(case),status='starting',time=time.time(),no_generation_retry=True)
    files=[];processes=[]
    def spawn(argv,env,name):
        f=(case/(name+'.console.log')).open('x');files.append(f)
        p=subprocess.Popen(argv,env=env,stdout=f,stderr=f,start_new_session=True);processes.append(p);return p
    try:
        mapping=read(PREFIX/'PREFIX_INDEX.json')['by_scene_card'][item['scene_card_id']]
        prefix=PREFIX/mapping['relative_path'];meta=read(prefix/'PREFIX.json');fixture=meta['fixture']
        for x in fixture['assets'].values():assert sha(Path(x['path']))==x['sha256']
        manifest=next(x for x in read(DATA/'manifest.json')if x['case_id']==cid)
        for field in ('audio','pcm'):assert sha(DATA/manifest[field+'_path'])==manifest[field+'_sha256']
        spec=dict(evaluation_family='T6_ASR_AGENT',fixture=fixture,t6_card=item,
            prefix=str(prefix),source_task=item['active_task_id'],public_current_task=TASKS[item['active_task_id']],policy_seed=7,service_lifetime_s=500)
        save(case/'spec.json',spec)
        cfg=dict(case_id=cid,baseUrl='http://127.0.0.1:'+str(PORT),pcm=str(DATA/manifest['pcm_path']),
            pcm_sha256=manifest['pcm_sha256'],audio_sha256=manifest['audio_sha256'],tokenFile=str(ACTOR/'private/robot.token'))
        save(case/'client_spec.json',cfg)
        env=dict(os.environ,RAW_ASR_URL=os.environ['RAW_ASR_URL'],PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost')
        robot=spawn([SIM,'-B','-u',str(ROOT/'code/gateway.py'),'--spec',str(case/'spec.json'),'--out',str(case),'--port',str(PORT),'--gpu',os.environ['COMMON_RENDER_GPU'],'--policy',os.environ['COMMON_POLICY_URL']],env,'robot')
        deadline=time.monotonic()+150
        while time.monotonic()<deadline:
            if robot.poll()is not None:raise RuntimeError('robot_exit_before_ready:'+str(robot.returncode))
            if (case/'T6_ADAPTER_READY.json').exists():break
            time.sleep(.2)
        assert (case/'T6_ADAPTER_READY.json').exists(),'adapter readiness timeout'
        client=spawn([NODE,str(ROOT/'code/client.mjs'),str(case/'client_spec.json'),str(case/'client')],env,'client')
        client.wait(timeout=180)
        if client.returncode:raise RuntimeError('audio client exit:'+str(client.returncode))
        output['status']='collected'
    except Exception as e:
        output.update(status='technical_or_setup_failure',error=repr(e),traceback=traceback.format_exc())
    finally:
        try:output['final_status']=request('/status');request('/evaluator/finish',{})
        except Exception:pass
        for p in processes:
            try:p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=15)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
        for f in files:f.close()
        evidence,control,audit=extract(case,item,index)
        output.update(audit=audit,finished=time.time(),agent_errors=read(case/'ENGINE_FINISHED.json').get('errors',[])if(case/'ENGINE_FINISHED.json').exists()else[])
        save(case/'OUTCOME.json',output)
    return output
