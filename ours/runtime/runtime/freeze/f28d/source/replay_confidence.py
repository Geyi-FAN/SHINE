"""Frozen observations and Agent stage schedule; not a closed-loop success estimate."""
import sys,json,gzip,collections
from pathlib import Path
from observed_completion import ObservedCompletion,Settings
OLD=Path('/mnt/disk_4/geyi/s1_D0_benchmark_final_20261027')
OUT=Path(__file__).resolve().parents[1]/'reports'
rows=[]
for arm in ['B','D0']:
 for folder in sorted((OLD/'formal'/arm/'cases/fresh').iterdir()):
  if not (folder/'result.json').exists():continue
  ds=[json.loads(x) for x in (folder/'points/detections.jsonl').read_text().splitlines()]
  ps={d['frame']:d['points'] for d in ds if d['time_source']=='current'}
  history={(d['time_source'],p['entity'],p['keypoint']):p for d in ds if d['time_source']!='current' for p in d['points']}
  observations=[json.loads(x) for x in (folder/'completion_observations.jsonl').read_text().splitlines()]
  calls=json.loads((folder/'agent_calls.json').read_text());stages={x['input']['frame']:x['result']['output']['remaining_plan'][0] for x in calls if x['result']['output'] and x['result']['output'].get('remaining_plan')}
  with gzip.open(folder/'trace.json.gz','rt') as f:trace=json.load(f)
  for conf in [.35,.1]:
   mon=ObservedCompletion(history,Settings(confidence=conf));seg=None
   for row in observations:
    sensor=row['sensor'];t=sensor['frame'];event=mon.observe(t,sensor['eef_xyz'],sensor['gripper_qpos'],sensor['eef_yx'],ps.get(t,[]))
    if event and seg is not None and seg['prediction'] is None:seg['prediction']=t
    if t in stages:
     if seg is not None:seg['end']=t;rows.append(seg)
     mon.active=None;mon.select(stages[t]);seg=dict(arm=arm,case_id=folder.name,confidence=conf,entered=t,operation=stages[t]['operation'],kind=stages[t]['kind'],prediction=None)
   if seg is not None:seg['end']=observations[-1]['sensor']['frame']+1;rows.append(seg)
   # Audit readiness at every control step within the frozen stage interval.
   for seg in [x for x in rows if x['arm']==arm and x['case_id']==folder.name and x['confidence']==conf]:
    ts=[m['step'] for m in trace['measurements'] if seg['entered']<m['step']<=seg['end'] and m.get('oracle_checked_operation')==seg['operation'] and m.get('oracle_stage_ready_for_audit')]
    seg['oracle_first']=min(ts) if ts else None
    p,o=seg['prediction'],seg['oracle_first']
    seg['classification']='no_prediction_no_reference' if p is None and o is None else 'missed_reference' if p is None else 'prediction_without_reference' if o is None else 'early' if p<o else 'at_or_after_reference'
summary={}
for conf in [.35,.1]:
 rr=[r for r in rows if r['confidence']==conf and r['kind'] in ['return','grasp','release']]
 summary[str(conf)]=dict(stages=len(rr),counts=dict(collections.Counter(r['classification'] for r in rr)),predictions=sum(r['prediction'] is not None for r in rr))
(OUT/'confidence_replay.json').write_text(json.dumps(dict(method='Fixed historical observations and Agent stage schedule; physical reference is audit only; not closed-loop success; target stages excluded from headline counts',summary=summary,rows=rows),indent=2))
print(json.dumps(summary,indent=2))
