import json,collections
from pathlib import Path
Q=Path('/mnt/disk_4/geyi/audio_switch_benchmark/deployments/common_scoring_oracle_baselines_20261114');A=Q/'audits/target_unknown_T2_20261115';R=Q/'runs/formal1770_v1'
def lines(p):return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []
u=json.loads((A/'unknown47.json').read_text());answer=[]
for v in u:
 d=Path(v['directory']);s=json.loads((R/'outcomes'/(v['trial_uid']+'.json')).read_text())['score'];p=s['attribution'];w=p['window'];result=json.loads((d/'result.json').read_text());ticks=lines(d/'recordings'/result['episode_id']/'control_ticks.jsonl');events=lines(d/'task_events.jsonl')
 active=[t for t in ticks if w['start']<=t['time']<=w['deadline']]
 created=[e for e in events if e.get('kind') in ['task_instruction','task_updated'] and w['start']<=e['time']<=w['deadline']]
 calls=[]
 for pp in sorted((d/'agent_calls').glob('*/request.json')):
  folder=pp.parent;response=folder/'response.json';transport=folder/'transport.json'
  row=dict(call=folder.name,response_exists=response.exists(),transport_exists=transport.exists())
  if response.exists():
   vv=json.loads(response.read_text());row['keys']=list(vv)[:8];row['intent']=vv.get('intent');row['complete_task']=vv.get('complete_task');row['decision']=vv.get('decision')
  if transport.exists():
   t=json.loads(transport.read_text());row['status']=t.get('status');row['error']=t.get('error');row['detail']=t.get('detail')
  calls.append(row)
 answer.append(dict(trial_uid=v['trial_uid'],branch=v['branch'],active_tick_count=len(active),active_policy_count=sum(bool(x.get('policy_action')) for x in active),new_instruction_events=[{k:e.get(k) for k in ['kind','time','task_id','instruction']} for e in created],calls=calls,window_start=w['start'],window_deadline=w['deadline'],client_finished=result['finished']['time']))
(A/'unknown47_deep.json').write_text(json.dumps(answer,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(dict(no_active_ticks=sum(not x['active_tick_count'] for x in answer),no_new_instruction=sum(not x['new_instruction_events'] for x in answer),with_new_instruction=sum(bool(x['new_instruction_events']) for x in answer),no_policy_in_window=sum(not x['active_policy_count'] for x in answer))))
