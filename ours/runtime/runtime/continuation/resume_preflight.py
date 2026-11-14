"""Actual low-budget native+symbolic continuation, typed tools, no audio SR."""
import json,os,signal,subprocess,time,urllib.request,uuid
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102');SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
def main():
 d=ROOT/'R7'/('resume_preflight_'+time.strftime('%H%M%S'));d.mkdir(parents=True,exist_ok=False);fixture=json.loads((ROOT/'R5b/dataset/initial_states.json').read_text())[0]
 spec=dict(case_id='R7_RESUME_ENGINEERING',fixture=fixture,source_task=0,target_task=999,context_turns=[],task_control_budget=4)
 (d/'spec.json').write_text(json.dumps(spec));base='http://127.0.0.1:19681';token=(B/'freeze/voice/private/robot.token').read_text().strip();events=[]
 def request(path,body=None):
  req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=8)as r:return json.load(r)
 def tool(name,**args):
  s=request('/status');body=dict(name=name,args=dict(episode_id=s['episode_id'],expected_task_version=s['task_version'],**args),request_id=uuid.uuid4().hex);r=request('/tool',body);events.append(dict(name=name,receipt=r));return body,r
 def wait(fn,seconds=200):
  end=time.monotonic()+seconds
  while time.monotonic()<end:
   try:
    s=request('/status')
    if fn(s):return s
   except OSError:pass
   time.sleep(.1)
  raise TimeoutError('resume preflight wait')
 result=dict(passed=False,kind='actual low-budget service engineering; correct typed text; no audio')
 with(d/'console.log').open('w')as log:
  proc=subprocess.Popen([SIM,'-u',str(B/'continuation/service_r7.py'),'--spec',str(d/'spec.json'),'--out',str(d),'--port','19681','--gpu','5','--policy-port','19865'],stdout=log,stderr=log,start_new_session=True)
  try:
   initial=wait(lambda s:s.get('ready'));checks=[]
   for name,instruction in [('native','put the bowl on the stove'),('symbolic','put the cream cheese in the bowl')]:
    tool('robot_start_task'if name=='native'else'robot_revise_task',instruction=instruction)
    before=wait(lambda s:s['state']=='budget_exhausted');count=before['execution_budget']['authorized_control_steps'];subject=(before['episode_id'],before['task_id'],before['task_intent_revision'])
    body,receipt=tool('robot_resume');after=wait(lambda s:s['execution_budget']['authorized_control_steps']>count and s['state']=='budget_exhausted')
    assert (after['episode_id'],after['task_id'],after['task_intent_revision'])==subject
    assert after['reset_count']==initial['reset_count']
    def extensions():return [json.loads(l)for l in(d/'gateway.jsonl').open()if '"kind": "explicit_resume_budget_extended"'in l]
    prior=len(extensions());request('/tool',body);time.sleep(.3);assert len(extensions())==prior
    checks.append(dict(route=name,subject=subject,before_controls=count,after_controls=after['execution_budget']['authorized_control_steps'],same_subject=True,same_episode_memory=True,duplicate_request_no_extra_extension=True))
   result.update(passed=True,checks=checks)
  except Exception as e:result['error']=repr(e)
  finally:
   result['events']=events;(d/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(20)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(5)
 print(json.dumps({k:v for k,v in result.items()if k!='events'}),flush=True)
if __name__=='__main__':main()
