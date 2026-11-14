import json,math
from score_preflight import lines
from score_dev96 import execution_events
from control_order import command_step,action_after

def evaluate(directory,spec,rules):
 p=directory/'result.json'
 if not p.exists():return dict(case_id=spec['case_id'],interaction='fail',target='na',instruction='na',failures=['missing_result'])
 r=json.loads(p.read_text());u=next((t for t in r.get('turns',[]) if t['turn_id']=='U1'),None)
 if not u:return dict(case_id=spec['case_id'],interaction='fail',target='na',instruction='na',checks=[dict(status='fail')],failures=['source_or_voice_not_reached'],errors=r.get('errors'))
 events=[e for e in execution_events(directory,r) if e['time']>=u['audio_started_wall']];ticks=[t for t in lines(directory/'recordings'/r['episode_id']/'control_ticks.jsonl') if t['time']>=u['audio_started_wall']]
 pauses=[e for e in events if e['kind']=='task_paused'];tasks=[e for e in events if e['kind']=='task_instruction'];checks={}
 if spec['expected']=='unsupported':
  plays=[m for m in r.get('messages',[]) if m.get('direction')=='sent' and m.get('type')=='host.playback_started' and u['audio_ended_wall']<=m['time']<=u['audio_ended_wall']+20]
  checks=dict(no_unsupported_task_started=not tasks,no_policy_actions=not any(t['policy_action'] for t in ticks),still_idle=r['final']['state']=='idle',actual_reply=bool(plays))
 elif spec['expected']=='negative':
  checks=dict(no_false_pause=not pauses,no_task_replacement=not tasks,no_new_task_id=r['final']['task_id']==r['source_task_id'],source_keeps_executing=any(t['policy_action'] and t['time']>u['audio_ended_wall']+1 for t in ticks))
 else:
  checks=dict(one_pause=len(pauses)==1,no_new_task=not tasks,still_paused=r['final']['state']=='paused',queue_empty=r['final']['queued_actions']==0)
  if pauses:
   pause=pauses[0]['time'];checks['stop_within_5s']=pause<=u['audio_ended_wall']+5;applied_step=command_step(directory,pauses[0],r['episode_id']);checks['no_old_actions_after_pause']=not any(action_after(t,pauses[0],applied_step) for t in ticks)
   plays=[m for m in r.get('messages',[]) if m.get('direction')=='sent' and m.get('type')=='host.playback_started' and pause<=m['time']<=pause+10]
   checks['actual_pause_ack_audio']=bool(plays)
 return dict(case_id=spec['case_id'],interaction='pass' if checks and all(checks.values()) else 'fail',target='na',instruction='na',checks=[dict(name=k,status='pass' if v else 'fail') for k,v in checks.items()],failures=[k for k,v in checks.items() if not v],errors=r.get('errors',[]),pauses=len(pauses),source_task_id=r.get('source_task_id'),final_state=r['final']['state'])
