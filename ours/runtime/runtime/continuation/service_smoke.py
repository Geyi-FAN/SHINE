"""Actual episode, hard pause, task change, reset and HTTP reconnect test.

Correct-text API smoke only; not an audio benchmark or a physical SR estimate.
"""
import json,os,signal,subprocess,time,urllib.request,urllib.error,uuid
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102/R4');SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python';TOKEN=(B/'freeze/voice/private/robot.token').read_text().strip()
def main():
 d=ROOT/('service_lifecycle_smoke_'+time.strftime('%H%M%S'));d.mkdir(exist_ok=False);fixture=json.load(open(ROOT/'dataset/initial_states.json'))[0];spec=dict(case_id='LIVE_LIFECYCLE_SMOKE',fixture=fixture,source_task=0,target_task=999,context_turns=[],serve_live=True,state_directory=str(d/'state'),task_control_budget=1200)
 p=d/'spec.json';p.write_text(json.dumps(spec));base='http://127.0.0.1:19781';events=[]
 def request(path,body=None):
  req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=15)as r:return json.loads(r.read())
 def status():return request('/status')
 def tool(name,**args):
  s=status();r=request('/tool',dict(name=name,args=dict(episode_id=s['episode_id'],expected_task_version=s['task_version'],**args),request_id=uuid.uuid4().hex));events.append(dict(time=time.time(),tool=name,receipt=r));return r
 def wait(predicate,seconds=180):
  end=time.monotonic()+seconds
  while time.monotonic()<end:
   try:
    s=status()
    if predicate(s):return s
   except OSError:pass
   time.sleep(.1)
  raise TimeoutError('lifecycle_smoke_wait')
 def physical():
  f=d/'physical.jsonl'
  with f.open('rb')as stream:stream.seek(max(0,f.stat().st_size-30000));return json.loads(stream.read().splitlines()[-1])
 result=dict(input='public typed API; real fixed model; no speech',passed=False)
 with(d/'console.log').open('w')as log:
  proc=subprocess.Popen([SIM,'-u',str(B/'continuation/serve.py'),'--spec',str(p),'--out',str(d),'--port','19781','--gpu','5','--policy-port','19867'],stdout=log,stderr=log,start_new_session=True)
  try:
   first=wait(lambda s:s.get('ready'));old_ep=first['episode_id'];result['first_ready']=first
   try:request('/evaluator/inspect');raise AssertionError('private evaluator exposed in production mode')
   except urllib.error.HTTPError as error:assert error.code==404
   tool('robot_start_task',instruction='put the bowl on the stove')
   end=time.monotonic()+120
   while time.monotonic()<end:
    if physical()['physical']['held_object']=='bowl':break
    time.sleep(.025)
   else:raise TimeoutError('actual_bowl_held')
   tool('robot_pause');wait(lambda s:s['state']=='paused');time.sleep(.2);a=physical();time.sleep(1.5);b=physical()
   assert (a['step'],a['simulation_time'],a['state_hash'])==(b['step'],b['simulation_time'],b['state_hash']);result['hard_pause_zero_world_change']=True
   revised=tool('robot_revise_task',instruction='Return the bowl to its episode-start position and release it.',user_utterance='Return the bowl to its episode-start position and release it.')
   assert revised['episode_id']==old_ep;result['task_change_keeps_episode']=True
   done=wait(lambda s:s['state']in('completed','needs_review','budget_exhausted'),240);result['revised_terminal']=done
   assert done['state']=='completed'
   before_reset=status();rid=uuid.uuid4().hex;body=dict(args=dict(episode_id=old_ep,expected_task_version=before_reset['task_version']),request_id=rid)
   result['reset_receipt']=request('/reset',body);fresh=wait(lambda s:s.get('ready')and s.get('episode_id')!=old_ep);assert fresh['task_id']is None and fresh['reset_count']==2 and fresh['task_version']>before_reset['task_version']
   result['reset_clears_task_and_initializes_new_memory']=fresh['scene_memory']['episode_id']==fresh['episode_id'];assert result['reset_clears_task_and_initializes_new_memory']
   same=request('/reset',body);time.sleep(.6);after=status();assert after['episode_id']==fresh['episode_id'];assert after['reset_count']==2
   result['duplicate_reset_no_second_reset']=True
   # A new independent HTTP connection is a reconnect, not an episode reset.
   again=request('/status');assert again['episode_id']==fresh['episode_id'];result['http_reconnect_keeps_episode']=True;result['new_ready']=fresh;result['passed']=True
  except Exception as e:result['error']=repr(e)
  finally:
   result['events']=events;(d/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(20)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(5)
 print(json.dumps({k:result.get(k)for k in('passed','error','hard_pause_zero_world_change','task_change_keeps_episode','reset_clears_task_and_initializes_new_memory','duplicate_reset_no_second_reset','http_reconnect_keeps_episode')}),flush=True)
if __name__=='__main__':main()
