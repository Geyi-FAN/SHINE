"""Sampled evidence replay: cannot reconstruct every old per-step contact signal."""
import json,gzip
from pathlib import Path
from scene_memory import SceneMemory,pose_deltas
OLD=Path('/mnt/disk_4/geyi/s1_D0_benchmark_final_20261027');OUT=Path(__file__).resolve().parents[1]/'reports'
summary=[]
for arm,c,entity,body in [('D0','V2_R329_T04_M4_T06_SWITCH_T04_M4_R07','cheese','cream_cheese_1'),('B','V2_R329_T05_P0_T09_SWITCH_T05_P0_R04','wine_bottle','wine_bottle_1')]:
 p=OLD/'formal'/arm/'cases/fresh'/c
 obs={x['sensor']['frame']:x for x in map(json.loads,(p/'completion_observations.jsonl').read_text().splitlines())}
 ds=[x for x in map(json.loads,(p/'points/detections.jsonl').read_text().splitlines()) if x['time_source']=='current']
 with gzip.open(p/'trace.json.gz','rt') as f:tr=json.load(f)
 ms={x['step']:x for x in tr['measurements']}
 initial=json.loads((p/'episode_initial_validity_evidence.json').read_text())
 log=OUT/(arm+'_'+c+'_memory_replay.jsonl');log.write_text('');m=SceneMemory(log,episode_id=c);rows=[]
 for d in ds:
  t=d['frame'];o=obs[t]['oracle_for_scoring_only']['objects'][entity]
  # At t=0 use initial pose ONLY when old validated import establishes same pose.
  if t==0:pose=initial['facts'][entity]['pose']
  else:
   po=ms[t]['source']['all_object_poses'][body];pose=po['position']+po['quaternion_wxyz']
  reusable=o['supported'] is True and o['bilateral_contact'] is False
  m.evidence(t,{entity:dict(pose=pose,static=False,cache_reusable=reusable)},'replay-fixed-camera')
  m.ingest([x for x in d['points'] if x['entity']==entity and x['keypoint']=='K1'],t)
  point,status=m.resolve(entity,'K1');rows.append(dict(frame=t,status=status,source_frame=None if point is None else point['frame']))
 summary.append(dict(case_id=c,arm=arm,last=rows[-1],rows=rows,counts=m.counts))
(OUT/'memory_replay.json').write_text(json.dumps(dict(limitation='Sampled support/contact plus recorded world poses; no exact per-control-step replay; t0 initial-pose warm start, no old initial point import; closed-loop validation reported separately',cases=summary),indent=2))
for x in summary:print(x['case_id'],x['last'],x['counts'])
