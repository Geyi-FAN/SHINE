"""Correct-text integration diagnosis only, never reported as audio success."""
import json,os,signal,subprocess,time,urllib.request,uuid,sys,socket
from pathlib import Path
B=Path(__file__).resolve().parents[1];OUT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102');SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
TOKEN=(B/'freeze/voice/private/robot.token').read_text().strip()
class Probe:
 def __init__(self,port):self.base=f'http://127.0.0.1:{port}';self.events=[]
 def request(self,path,body=None):
  req=urllib.request.Request(self.base+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=15)as r:return json.load(r)
 def status(self):return self.request('/status')
 def tool(self,name,**args):
  s=self.status();body=dict(name=name,args=dict(episode_id=s['episode_id'],expected_task_version=s['task_version'],**args),request_id=uuid.uuid4().hex)
  out=self.request('/tool',body);self.events.append(dict(time=time.time(),name=name,args=args,receipt=out));return out
 def wait(self,predicate,seconds=180):
  end=time.monotonic()+seconds
  while time.monotonic()<end:
   s=self.request('/evaluator/inspect')
   if predicate(s):return s
   if s['mode']in('needs_review','budget_exhausted'):raise RuntimeError('backend_'+s['mode'])
   time.sleep(.2)
  raise TimeoutError('text_probe_wait')

def run(cases,kinds=None,label='text_integration_r1'):
 root=OUT/label;root.mkdir(exist_ok=True)
 for kind,template in [('native','T1_01'),('clarification','T5_01'),('return_only','T4_01'),('waiting','T7_01')]:
  if kinds and kind not in kinds:continue
  d=root/kind;d.mkdir(exist_ok=False);a=next(c for c in cases if c['script_id']==template and c['case_id'].endswith('S1'));fixture=json.load(open(OUT/'dataset/initial_states.json'))[0]
  spec=dict(case_id='TEXT_'+label+'_'+kind,fixture=fixture,source_task=1,target_task=6 if kind in('clarification','waiting')else 1,restore='bowl'if kind=='return_only'else None,return_only=kind=='return_only',context_turns=['source']if kind in('return_only','waiting')else[],phase='M2'if kind in('return_only','waiting')else None,preserve_bowl=kind=='waiting',task_control_budget=1200)
  (d/'spec.json').write_text(json.dumps(spec));env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',HYBRID_POLICY_NAMESPACE='TEXT_REPAIR:'+label+':'+kind);port=19581 if label.endswith(('r2','r3'))else 19381
  with socket.socket()as check:assert check.connect_ex(('127.0.0.1',port))!=0,'isolated port already in use'
  with (d/'services.log').open('w')as log:
   proc=subprocess.Popen([SIM,'-u',str(B/'repair/gateway.py'),'--spec',str(d/'spec.json'),'--out',str(d),'--port',str(port),'--gpu','5','--policy-port','19867'],env=env,stdout=log,stderr=log,start_new_session=True)
   result=dict(kind=kind,input='correct text via actual public tool; not audio',passed=False)
   p=Probe(port)
   try:
    end=time.monotonic()+180
    while time.monotonic()<end:
     if proc.poll()is not None:raise RuntimeError('gateway_start_failed')
     try:
      if (d/'READY.json').exists()and p.status().get('ready')and p.status()['episode_id']==json.loads((d/'READY.json').read_text())['episode_id']:break
     except OSError:pass
     time.sleep(1)
    else:raise TimeoutError('readiness')
    if kind=='clarification':
     r=p.tool('robot_begin_clarification',user_utterance='Please move it.',voice_input_id='u1',question='Which object do you want to move?',missing_slot='object');c=p.status()['pending_clarification']
     p.tool('robot_answer_clarification',clarification_id=c['clarification_id'],user_utterance='The cream cheese.',resolved_answer='The cream cheese.',voice_input_id='u2',question='Where should I put the cream cheese?')
     s=p.status();assert s['task_id']is None;c=s['pending_clarification']
     p.tool('robot_answer_clarification',clarification_id=c['clarification_id'],user_utterance='Into the bowl.',voice_input_id='u3',instruction='put the cream cheese in the bowl')
    else:p.tool('robot_start_task',instruction='put the bowl on the stove')
    if kind in('return_only','waiting'):
     result['source']=p.wait(lambda s:s['fixture_hold']and s['sample']['physical']['held_object']=='bowl')
     if kind=='return_only':p.tool('robot_revise_task',instruction='Return the bowl to its episode-start position and release it.',user_utterance='Put it back where it was at the beginning of this episode, and let go.')
     else:
      p.tool('robot_schedule_task',instruction='put the cream cheese in the bowl',user_utterance='After this task finishes, put the cheese in the bowl.')
      p.request('/evaluator/release_window',{})
    result['final']=p.wait(lambda s:s['mode']=='completed'and(kind!='waiting'or s['task_count']==2),650)
    result['passed']=True
   except Exception as e:result['error']=repr(e)
   finally:
    result['events']=p.events
    try:result['public_final']=p.status();p.request('/evaluator/finish',{})
    except Exception:pass
    (d/'TEXT_RESULT.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
    try:proc.wait(20)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait(20)
   print(json.dumps(dict(kind=kind,passed=result['passed'],error=result.get('error'))),flush=True)
