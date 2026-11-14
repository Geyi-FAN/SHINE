"""Replay recorded speech provenance without changing the original database."""
import copy,json,sqlite3,sys
from pathlib import Path
from types import SimpleNamespace
A=Path(__file__).parent;sys.path[:0]=[str(A),str(A.parent/'freeze/voice/robot_gateway')]
from speech_routing import native_candidate
import native_execution
D=Path('/mnt/disk_4/geyi/t7_c3r_goal10_20261103/round3/cases/T7V3_T03_C_I00')
s=json.loads((D/'result.json').read_text())['final'];events=[]
def state():
 return SimpleNamespace(episode=s['episode_id'],task_id=s['task_id'],instruction=s['instruction'],
  policy_metadata=s['policy_metadata'],task_record=copy.deepcopy(s['task']),scene_inventory=s['scene_inventory'],
  deferred_task=None,db=sqlite3.connect((D/'gateway/episodes.sqlite').resolve().as_uri()+'?mode=ro',uri=True),
  event=lambda k,v:events.append((k,v)))
x=state();assert native_execution.native_candidate(x,True,'none')==(None,'unresolved_ball_bowl_conflict')
y,reason=native_candidate(x,True,'none');assert y and y['task_id']==3 and len(events)==1
assert x.task_record['user_utterance']=='Open the top drawer and put the ball inside.'
x=state();x.task_record['voice_input_id']='absent';assert native_candidate(x,True,'none')[0]is None
x=state();x.task_record['episode_id']='old';assert native_candidate(x,True,'none')[0]is None
x=state();x.task_record['semantic_check']['audio_relisten_grounding_used']=False;assert native_candidate(x,True,'none')[0]is None
x=state();assert native_candidate(x,False,'none')[0]is None
x=state();assert native_candidate(x,True,'unknown')[0]is None
x=state();x.task_record['persistent_constraints']=['Keep stove off'];assert native_candidate(x,True,'none')[0]is None
x=state();x.task_record['semantic_check']['grounding_utterance']='put the cheese in the bowl';assert native_candidate(x,True,'none')[0]is None
print('Recorded acoustic correction native routing passed; seven stale/missing/takeover/holding/extra-constraint/changed-content negatives preserved; raw text unchanged')
