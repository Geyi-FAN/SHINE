"""Actual fixed-model waiting handoff. Typed setup, no audio or score claim."""
import json,os,signal,subprocess,time,urllib.request,uuid
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102');SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
def main():
 d=ROOT/'R6'/('waiting_engineering_'+time.strftime('%H%M%S'));d.mkdir(parents=True,exist_ok=False);fixture=json.loads((ROOT/'R5b/dataset/initial_states.json').read_text())[0];spec=dict(case_id='R6_WAITING_ENGINEERING',fixture=fixture,source_task=1,target_task=999,context_turns=['source'],phase='M2',task_control_budget=1200);p=d/'spec.json';p.write_text(json.dumps(spec));base='http://127.0.0.1:19681';token=(B/'freeze/voice/private/robot.token').read_text().strip();events=[]
 def request(path,body=None,post=False):
  req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),method='POST'if post or body is not None else'GET',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=8)as r:return json.load(r)
 def tool(name,**args):
  s=request('/status');r=request('/tool',dict(name=name,args=dict(episode_id=s['episode_id'],expected_task_version=s['task_version'],**args),request_id=uuid.uuid4().hex));events.append(dict(time=time.time(),tool=name,receipt=r));return r
 def wait(fn,seconds=180):
  end=time.monotonic()+seconds
  while time.monotonic()<end:
   try:
    s=request('/evaluator/inspect')
    if fn(s):return s
   except OSError:pass
   time.sleep(.15)
  raise TimeoutError('waiting engineering wait')
 result=dict(passed=False,input='public text tools; no audio; same fixed action model')
 with(d/'console.log').open('w')as log:
  proc=subprocess.Popen([SIM,'-u',str(B/'repair6/service.py'),'--spec',str(p),'--out',str(d),'--port','19681','--gpu','4','--policy-port','19866'],stdout=log,stderr=log,start_new_session=True)
  try:
   wait(lambda s:request('/status').get('ready'));tool('robot_start_task',instruction='put the bowl on the stove');held=wait(lambda s:s['fixture_hold']and s['sample']['physical']['held_object']=='bowl')
   tool('robot_schedule_task',instruction='put the cream cheese into the bowl and keep the bowl on the stove',user_utterance='After the bowl is on the stove and released, put the cream cheese into it. Keep the bowl on the stove.')
   # No artificial wait for the prefetch. Release the controlled window now.
   request('/evaluator/release_window',post=True)
   changed=wait(lambda s:s['task_count']==2,220);result['successor_started']=True;result['handoff_gripper_width']=sum(abs(x)for x in changed['sample']['proprioception']['robot0_gripper_qpos']);assert result['handoff_gripper_width']>=.065
   before=changed['control_step'];first=wait(lambda s:s['task_count']==2 and s['control_step']>before,180);result['first_successor_action_time']=first['sample']['time'];result['successor_task_id']=first['task_id'];result['current_execution_metadata']=request('/status')['agent_execution'];assert result['current_execution_metadata'].get('task_id',first['task_id'])==first['task_id']
   result['prefetch_reused']='waiting_wording_prefetch_reused'in(d/'gateway.jsonl').read_text();result['passed']=result['prefetch_reused']
  except Exception as e:result['error']=repr(e)
  finally:
   try:request('/evaluator/finish',post=True)
   except OSError:pass
   result['events']=events;(d/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(20)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(5)
 print(json.dumps({k:v for k,v in result.items()if k not in ['events','current_execution_metadata']}),flush=True)
if __name__=='__main__':main()
