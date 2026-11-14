"""Start only private loopback services and a genuine audio client."""
import json,os,signal,socket,subprocess,time,urllib.request
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=B/'freeze/voice';PROD=Path('/mnt/disk_2/geyi/voice_pi05_harness');OUT=Path('/mnt/disk_4/geyi/voice_f28d_G22_20261101')/os.environ.get('G22_AUDIO_LABEL','audio_smoke_v2')
SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python';NODE=str(PROD/'runtime/node-v22.23.3-linux-x64/bin/node')

def main():
    root=OUT.parent
    required=[B/'reports/G22/close_entry8_v2/COMPLETED.json',root/'release_stage_v2/original/result.json',root/'release_stage_v2/recovery/result.json',root/'release_observation_v1/RESULTS.json']
    for _ in range(600):
        if all(p.exists()for p in required):break
        time.sleep(1)
    else:raise TimeoutError('Diagnostic prerequisites incomplete; no audio sent')
    recovered=json.loads(required[2].read_text());negative=json.loads(required[3].read_text())[0]['result']
    assert recovered['observed_complete'] and not recovered['false_completion'] and recovered['kernel_error'] is None
    assert negative['accepted'] and negative['response']['recovery_request']!='release_supported_in_place','Airborne inspection must not authorize release'
    OUT.mkdir(parents=True,exist_ok=False);voice=OUT/'voice';voice.mkdir(mode=0o700)
    (OUT/'ADMISSION.json').write_text(json.dumps(dict(prerequisites=[str(p)for p in required],close_preflight='rejected; original scheduling retained',release='development positive fixture and airborne rejection; not proven generic SR improvement',browser_free=True,production_8787_untouched=True),indent=2))
    for port in [18981,18987,18989]:
        with socket.socket()as sock:assert sock.connect_ex(('127.0.0.1',port))!=0,port
    conf=json.loads((ROOT/'data/harness/config.json').read_text());conf['port']=18989;conf['backends']=[];(voice/'config.json').write_text(json.dumps(conf));os.chmod(voice/'config.json',0o600)
    manifest=json.loads(Path('/mnt/disk_4/geyi/audio_switch_benchmark_dev_v1/frozen_audio_20261031/manifest.json').read_text());use=['T1_01_U01','T2_02_U01','T2_01_U02','T3_03_U01'];turns=[]
    for uid in use:
        rec=next(r for r in manifest if uid in r['uses']);turns.append(dict(id=uid,text=rec['text'],file=rec['file'],sha256=rec['sha256']))
    fixture=json.loads(Path('/mnt/disk_1/geyi/audio_cli_smoke_attempt4_20261101/fixture.json').read_text());spec=dict(case_id='G22_AUDIO_SOURCE_PAUSE_RESUME_SWITCH_PLATE',fixture=fixture,source_task=1,target_task=8,preserve_bowl=False,phase='M2',context_turns=[turns[0]['text']],turns=turns,task_control_budget=600)
    (OUT/'spec.json').write_text(json.dumps(spec,indent=2));env=dict(os.environ,VOICE_ROBOT_DATA_DIR=str(OUT/'gateway'),VOICE_EVAL_RECORD_DIR=str(OUT/'recordings'),VOICE_DISCOVERY_FILE=str(voice/'run/daemon.json'),VOICE_HISTORY_DIR=str(OUT/'review_history'),VOICE_ROBOT_PORT='18981',VOICE_WEB_PORT='18987',VOICE_HARNESS_RUNTIME_CONFIG=str(ROOT/'configs/runtime.local.json'),HYBRID_POLICY_NAMESPACE='G22_AUDIO:'+OUT.name,PYTHONDONTWRITEBYTECODE='1')
    ve=dict(env,DASHSCOPE_API_KEY=(ROOT/'private/dashscope.key').read_text().strip(),QWEN_LIVE_HARNESS_DATA_DIR=str(voice),QWEN_LIVE_HARNESS_DISCOVERY_DIR=str(voice),ROBOT_GATEWAY_URL='http://127.0.0.1:18981',ROBOT_GATEWAY_TOKEN_FILE=str(ROOT/'private/robot.token'),ROBOT_AUDIO_BENCHMARK_HOST='1',ROBOT_BROWSER_HOST='1',ROBOT_RECEIPT_AUDIO_DIR=str(PROD/'data/receipt_audio'),ROBOT_INSTRUCTION_PROMPT_FILE=str(ROOT/'configs/instruction_prompt.txt'))
    processes=[]
    with (OUT/'services.log').open('w')as log:
        try:
            for cmd,e in [([NODE,str(B/'artifacts/G22_audio_daemon/dist/index.js'),'--daemon-only'],ve),([SIM,'-u',str(B/'g22/gateway.py'),'--spec',str(OUT/'spec.json'),'--out',str(OUT),'--port','18981','--gpu','5','--policy-port','19867'],env),([NODE,str(ROOT/'web_host/server.mjs')],env)]:processes.append(subprocess.Popen(cmd,env=e,stdout=log,stderr=log,start_new_session=True))
            for _ in range(150):
                if any(p.poll()is not None for p in processes):raise RuntimeError('Isolated service exited; see services.log')
                try:
                    response=json.load(urllib.request.urlopen('http://127.0.0.1:18987/api/status',timeout=2))
                    if response.get('ready'):break
                except (OSError,ValueError):pass
                time.sleep(1)
            else:raise TimeoutError('readiness')
            (OUT/'readiness.json').write_text(json.dumps(response,indent=2));print('READY isolated real audio',flush=True)
            subprocess.run([NODE,str(B/'g22/audio_smoke.mjs'),str(OUT/'spec.json'),str(OUT)],env=env,check=True,timeout=700)
            for p in processes[1:2]:
                try:p.wait(30)
                except subprocess.TimeoutExpired:pass
        finally:
            for p in reversed(processes):
                if p.poll()is None:os.killpg(p.pid,signal.SIGTERM)
            for p in processes:
                try:p.wait(15)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL)
    print('private services stopped',flush=True)

if __name__=='__main__':main()
