"""Actual R6 service: empty POST, incomplete clarification and native placement.
Correct typed text only; not audio SR or a physical performance estimate.
"""
import json,os,signal,subprocess,time,urllib.request,urllib.error,uuid
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102');SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
def main():
 d=ROOT/'R6'/('engineering_'+time.strftime('%H%M%S'));d.mkdir(parents=True,exist_ok=False);fixture=json.loads((ROOT/'R5b/dataset/initial_states.json').read_text())[0];spec=dict(case_id='R6_ENGINEERING',fixture=fixture,source_task=0,target_task=999,context_turns=[],task_control_budget=1200);p=d/'spec.json';p.write_text(json.dumps(spec));base='http://127.0.0.1:19681';token=(B/'freeze/voice/private/robot.token').read_text().strip();events=[]
 def request(path,body=None,post=False):
  req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),method='POST'if post or body is not None else'GET',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=8)as r:return json.load(r)
 def tool(name,**args):
  s=request('/status');r=request('/tool',dict(name=name,args=dict(episode_id=s['episode_id'],expected_task_version=s['task_version'],**args),request_id=uuid.uuid4().hex));events.append(dict(tool=name,receipt=r));return r
 def wait(fn,seconds=180):
  end=time.monotonic()+seconds
  while time.monotonic()<end:
   try:
    s=request('/evaluator/inspect')
    if fn(s):return s
   except OSError:pass
   time.sleep(.15)
  raise TimeoutError('engineering wait')
 result=dict(passed=False,input='typed public tools; no audio')
 with(d/'console.log').open('w')as log:
  proc=subprocess.Popen([SIM,'-u',str(B/'repair6/service.py'),'--spec',str(p),'--out',str(d),'--port','19681','--gpu','4','--policy-port','19866'],stdout=log,stderr=log,start_new_session=True)
  try:
   start=wait(lambda s:request('/status').get('ready'));request('/evaluator/hold',post=True);wait(lambda s:s['physics_step']>=start['physics_step']+40 and s['hold_remaining']==0,30);result['real40step_hold_passed']=True
   tool('robot_begin_clarification',user_utterance='Please move it.',voice_input_id='u1',question='Which object should I move?',missing_slot='object');c=request('/status')['pending_clarification']
   try:tool('robot_answer_clarification',clarification_id=c['clarification_id'],user_utterance='The cream cheese.',voice_input_id='u2',instruction='Move the cream cheese.');raise AssertionError('incomplete instruction accepted')
   except urllib.error.HTTPError as e:
    message=e.read().decode();assert 'clarification_missing_destination'in message;result['incomplete_goal_rejected']=True
   assert request('/status')['task_id']is None
   tool('robot_answer_clarification',clarification_id=c['clarification_id'],user_utterance='The cream cheese.',voice_input_id='u2',question='Where should I put it?');assert request('/status')['task_id']is None
   tool('robot_answer_clarification',clarification_id=c['clarification_id'],user_utterance='Into the bowl.',voice_input_id='u3',instruction='put the cream cheese in the bowl');result['same_answer_followup_and_final_binding']=True
   final=wait(lambda s:s['mode']in ['completed','needs_review','budget_exhausted'],240);result['placement_terminal']=final['mode'];result['placement_goal']=final['sample']['physical']['native_goal_relations']['cheese_bowl'];result['raw_contact_recorded']='object_object_contacts'in final['sample']['measurements']['cheese'];assert result['raw_contact_recorded'];result['passed']=True
  except Exception as e:result['error']=repr(e)
  finally:
   try:request('/evaluator/finish',post=True)
   except OSError:pass
   result['events']=events;(d/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(20)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(5)
 print(json.dumps({k:v for k,v in result.items()if k!='events'}),flush=True)
if __name__=='__main__':main()
