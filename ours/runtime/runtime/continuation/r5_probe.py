"""Real simulator facade preflight, no cloud audio, no language command."""
import json,os,signal,subprocess,time,urllib.request
from pathlib import Path
B=Path(__file__).resolve().parents[1];OUT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102/R5');SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
def main():
 d=OUT/('transport_preflight_'+time.strftime('%H%M%S'));d.mkdir(exist_ok=False);fixture=json.loads((OUT/'dataset/initial_states.json').read_text())[0];spec=dict(case_id='R5_TRANSPORT_PREFLIGHT',fixture=fixture,source_task=0,target_task=999,context_turns=[]);p=d/'spec.json';p.write_text(json.dumps(spec));token=(B/'freeze/voice/private/robot.token').read_text().strip();base='http://127.0.0.1:19681'
 def request(path,post=False):
  req=urllib.request.Request(base+path,method='POST'if post else'GET',headers={'Authorization':'Bearer '+token})
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=5)as r:return json.load(r)
 result=dict(passed=False,input='no audio and no task command')
 with(d/'console.log').open('w')as log:
  proc=subprocess.Popen([SIM,'-u',str(B/'continuation/service_r5.py'),'--spec',str(p),'--out',str(d),'--port','19681','--gpu','5','--policy-port','19867'],stdout=log,stderr=log,start_new_session=True)
  try:
   end=time.monotonic()+180
   while time.monotonic()<end:
    try:
     if request('/status').get('ready'):break
    except OSError:pass
    time.sleep(.5)
   else:raise TimeoutError('readiness')
   start=request('/evaluator/inspect');receipt=request('/evaluator/hold',True);assert receipt['accepted']
   end=time.monotonic()+30
   while time.monotonic()<end:
    final=request('/evaluator/inspect')
    if final['physics_step']>=start['physics_step']+40 and final['hold_remaining']==0:break
    time.sleep(.1)
   else:raise TimeoutError('physical_hold')
   assert final['physics_step']-start['physics_step']>=40
   result.update(passed=True,hold_receipt=receipt,physics_advance=final['physics_step']-start['physics_step'],finish_receipt=request('/evaluator/finish',True))
  except Exception as e:result['error']=repr(e)
  finally:
   (d/'RESULT.json').write_text(json.dumps(result,indent=2));os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(20)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(5)
 print(json.dumps(result),flush=True);assert result['passed']
if __name__=='__main__':main()
