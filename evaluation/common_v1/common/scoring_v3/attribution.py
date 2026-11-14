"""Evaluator-only causal actor attribution, independent of rewritten Task text.

The frozen geometric predicates and thresholds are untouched. This module only
answers which real action identities follow the actual authorized audio turn.
"""
import json
VERSION='audio-causal-attribution-v3-20261109'
def lines(path):return[json.loads(x)for x in path.read_text().splitlines()if x.strip()]if path.exists()else[]
def window(branch,result,case):
 turns=result.get('turns',[]);main=[t for t in turns if not t.get('prelude')]
 if not turns:return None
 if branch in ['T1','T2']:turn=turns[0]
 elif branch=='T3':
  if len(turns)<2:return None
  turn=turns[1]
 elif branch=='T4':
  if not main:return None
  turn=main[0]
 elif branch=='T5':
  turn=result.get('authorization_turn')
  if not turn:return None
 elif branch=='T7':
  p=case['private_contract'];index=0 if case.get('branch')=='C'else min(2,len(turns)-1)if case.get('branch')=='R'else 1
  if len(turns)<=index:return None
  turn=turns[index]
 elif branch=='T8':
  if not main:return None
  turn=main[0]
 else:raise ValueError(branch)
 if 'audio_started_wall'not in turn or'audio_ended_wall'not in turn:return None
 return dict(start=turn['audio_started_wall'],deadline=min(result['finished']['time'],turn['audio_ended_wall']+600),turn=turn)
def causal_ids(branch,result,case,events,ticks):
 w=window(branch,result,case)
 if w is None:return dict(valid=False,reason='no_actual_authorizing_audio',ids=[],window=None)
 episode=result.get('episode_id');selected=[];authorized_after={}
 if branch=='T8'or(branch=='T7'and case.get('branch')=='C'):
  sid=result.get('source_task_id');selected=[sid]if sid else[]
 else:
  for e in events:
   if e.get('kind')not in ['task_instruction','task_updated']or not(w['start']<=e.get('time',-1)<=w['deadline']):continue
   if branch=='T2'and e.get('time',-1)>w['turn']['audio_ended_wall']+20:continue
   if e.get('task_id'):
    selected.append(e['task_id']);authorized_after[e['task_id']]=min(authorized_after.get(e['task_id'],e['time']),e['time'])
 if branch=='T2':
  # Stop/resume must not manufacture new logical target authorizations.
  sid=result.get('source_task_id')or(selected[0]if selected else None);selected=[sid]if sid else[]
 ids=set(selected)
 actual={t.get('task_id')for t in ticks if t.get('episode_id')==episode and t.get('policy_action')and max(w['start'],authorized_after.get(t.get('task_id'),w['start']))<=t.get('time',-1)<=w['deadline']}
 return dict(valid=True,ids=sorted(ids&actual),window=w,source='actual_audio_time_task_events_and_action_cohort; no_instruction_string_matching',episode_id=episode,authorized_after=authorized_after)
