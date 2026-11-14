"""Real hard-pause/receipt probe on the owner-thread priority queue; no audio."""
import json,os,signal,subprocess,time,sqlite3,urllib.error
from pathlib import Path
from repair.text_probe import B,OUT,SIM,Probe

def run():
 d=OUT/'text_priority_r3';d.mkdir(exist_ok=False);fixture=json.load(open(OUT/'dataset/initial_states.json'))[0]
 spec=dict(case_id='TEXT_PRIORITY_R3',fixture=fixture,source_task=1,target_task=1,context_turns=['unscored source'],phase='M2',held_source_entity='bowl',source_window_task_count=1,task_control_budget=1200)
 (d/'spec.json').write_text(json.dumps(spec));env=dict(os.environ,VOICE_PRIORITY_STOP='1',PYTHONDONTWRITEBYTECODE='1',HYBRID_POLICY_NAMESPACE='TEXT_PRIORITY_R3');p=Probe(19481);result=dict(input='public text tool; not audio',passed=False)
 with(d/'services.log').open('w')as log:
  proc=subprocess.Popen([SIM,'-u',str(B/'repair/gateway.py'),'--spec',str(d/'spec.json'),'--out',str(d),'--port','19481','--gpu','5','--policy-port','19867'],env=env,stdout=log,stderr=log,start_new_session=True)
  try:
   end=time.monotonic()+180
   while time.monotonic()<end:
    if proc.poll()is not None:raise RuntimeError('gateway_start_failed')
    try:
     if p.status().get('ready'):break
    except OSError:pass
    time.sleep(.5)
   else:raise TimeoutError('readiness')
   p.tool('robot_start_task',instruction='put the bowl on the stove');source=p.wait(lambda s:s['fixture_hold']and s['sample']['physical']['held_object']=='bowl');tid=source['task_id']
   began=time.monotonic();pause=p.tool('robot_pause');result['public_tool_pause_latency_s']=time.monotonic()-began
   before=p.wait(lambda s:s['mode']=='paused',10);time.sleep(1.5);after=p.request('/evaluator/inspect')
   result['pause_zero_world_change']=all(before[k]==after[k]for k in('physics_step','simulation_time','physical_state_sha256'))
   assert result['pause_zero_world_change'];assert before['sample']['physical']['held_object']=='bowl'
   p.tool('robot_resume');continued=p.wait(lambda s:s['mode']=='running'and s['control_step']>before['control_step'],30)
   prior=p.status()
   try:p.tool('robot_resume');raise AssertionError('duplicate resume unexpectedly accepted as new mutation')
   except urllib.error.HTTPError as error:
    assert error.code==409;result['duplicate_resume_rejection']=json.loads(error.read())
   now=p.status();assert now['task_id']==tid and now['task_version']==prior['task_version']
   with sqlite3.connect(d/'gateway/episodes.sqlite')as db:
    resumed=db.execute("SELECT COUNT(*) FROM events WHERE kind='task_resumed'").fetchone()[0]
   assert resumed==1;result['actual_resume_events']=resumed
   result.update(passed=True,before=before,after=after,resumed=continued,duplicate_resume_task_id_unchanged=True)
  except Exception as e:result['error']=repr(e)
  finally:
   result['events']=p.events
   try:result['final']=p.status();p.request('/evaluator/finish',{})
   except OSError:pass
   (d/'RESULT.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
   try:proc.wait(20)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait(20)
 print(json.dumps({k:result.get(k)for k in('passed','public_tool_pause_latency_s','pause_zero_world_change','error')}),flush=True)
if __name__=='__main__':run()
