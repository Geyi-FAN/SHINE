"""Recompute each recorded cheese containment pose, including speech prefixes.

No policy/Agent/audio calls and no env.step beyond fixture initialization.
All old files remain read-only. This separates scoring correction from repair.
"""
import gzip,json,sys
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
B=Path(__file__).resolve().parents[1];sys.path[:0]=[str(B),str(B/'g2')]
from bootstrap import configure
from entryfix.support import container_support
OLD=Path('/mnt/disk_2/geyi/audio_t3_selected10_20261102');CASE='T3R2_S09_V2_I00';src=OLD/'runs/formal10'/CASE
out=B/'reports/baseline_force_reaudit';out.mkdir(parents=True,exist_ok=True);(out/'logs').mkdir(exist_ok=True);configure(out,6)
from sim_runtime import GeometryRuntime
from revision_eval.env import make_libero_env,settle_env
import h5py
s=json.loads((src/'spec.json').read_text());assets=s['fixture']['assets'];env,_=make_libero_env(NS(problem_folder='',bddl_file=assets['bddl_file']['path'],language='recorded pose force audit'),NS(env_img_res=256,seed=s['fixture']['scene_seed'],control_mode='relative'))
with h5py.File(assets['source_hdf']['path'])as f:settle_env(env,f['states'][0].copy(),10)
rt=GeometryRuntime();mon=rt.monitor(env,6)
with gzip.open(src/'tasks/8d939deb42b840c782833863e2a6f37c/trace.json.gz','rt')as f:ms=json.load(f)['measurements']
evidence={};max_error=0
for row in ms:
 if not row['goal_frame']['goal']:continue
 v=row['target'];d=mon.live
 for name,p in v['all_object_poses'].items():
  j=env.sim.model.joint_name2id(env.env.objects_dict[name].joints[0]);a=int(mon.model.jnt_qposadr[j]);d.qpos[a:a+3]=p['position'];d.qpos[a+3:a+7]=p['quaternion_wxyz']
 d.qpos[mon.qidx]=v['joint_positions'];d.qpos[mon.gidx]=v['gripper_positions'];d.qvel[:]=0
 for name,joint in [('middle','wooden_cabinet_1_middle_level'),('top','wooden_cabinet_1_top_level'),('stove','flat_stove_1_button')]:
  j=env.sim.model.joint_name2id(joint);d.qpos[int(mon.model.jnt_qposadr[j])]=v['articulation'][name]
 env.sim.forward();max_error=max(max_error,float(np.max(np.abs(d.xpos[mon.target_body]-v['object_position']))));ev=container_support(mon);ev['provenance']='recomputed individual recorded pose; not original live force log';evidence[row['world_physics_step']]=ev
env.close();assert max_error<1e-8
(out/'FORCE_PER_FRAME.json').write_text(json.dumps(dict(scope='zero new robot rollout; each historical pose separately recomputed, no future frame borrowed',max_pose_error=max_error,frames=evidence),indent=2))
from selected_eval.score import evaluate
results=[]
for c in json.loads((B/'run_data/cases.private.json').read_text()):
 source=OLD/'runs/formal10'/c['case_id'];dest=out/c['case_id'];dest.mkdir(exist_ok=False)
 for n in('client','voice','gateway','gateway.jsonl','result.json','spec.json'):(dest/n).symlink_to(source/n,target_is_directory=(source/n).is_dir())
 (dest/'recordings').mkdir();(dest/'recordings/api.jsonl').symlink_to(source/'recordings/api.jsonl')
 r=json.loads((source/'result.json').read_text());ep=r['episode_id'];folder=dest/'recordings'/ep;folder.mkdir();rows=[]
 for line in(source/'recordings'/ep/'control_ticks.jsonl').read_text().splitlines():
  t=json.loads(line)
  if c['case_id']==CASE and t['step']in evidence:t['measurements']['cheese']['container_support_evidence']=evidence[t['step']]
  rows.append(t)
 (folder/'control_ticks.jsonl').write_text(''.join(json.dumps(t)+'\n'for t in rows))
 spec=json.loads((source/'spec.json').read_text());v=evaluate(dest,spec,spec['rules']);old=json.loads((source/'verdict.audited.json').read_text());results.append(dict(case_id=c['case_id'],old={k:old[k]for k in('interaction','target','instruction')},corrected={k:v[k]for k in('interaction','target','instruction')},spoken_claims=v.get('spoken_claims')))
summary=dict(scope='same original 10 rollouts, revised support implementation only; NOT new system performance',totals={version:{k:sum(r[version][k]=='pass'for r in results)for k in('interaction','target','instruction')}for version in('old','corrected')},cases=results)
(out/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary['totals']))
