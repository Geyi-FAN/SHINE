"""Read-only reconstructed terminal-pose force diagnostic; zero env.step."""
import gzip,json,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
B=Path(__file__).resolve().parents[1];sys.path[:0]=[str(B),str(B/'g2')]
OLD=Path('/mnt/disk_2/geyi/audio_t3_selected10_20261102/runs/formal10/T3R2_S09_V2_I00')
from bootstrap import configure
out=B/'reports/support_reconstruction';out.mkdir(exist_ok=True,parents=True);configure(out,3)
from sim_runtime import GeometryRuntime
from revision_eval.env import make_libero_env,settle_env
import h5py
spec=json.loads((OLD/'spec.json').read_text());assets=spec['fixture']['assets']
env,_=make_libero_env(SimpleNamespace(problem_folder='',bddl_file=assets['bddl_file']['path'],language='terminal-pose force diagnostic'),SimpleNamespace(env_img_res=256,seed=spec['fixture']['scene_seed'],control_mode='relative'))
with h5py.File(assets['source_hdf']['path'])as f:settle_env(env,f['states'][0].copy(),10)
rt=GeometryRuntime();mon=rt.monitor(env,6)
with gzip.open(OLD/'tasks/8d939deb42b840c782833863e2a6f37c/trace.json.gz','rt')as f:terminal=json.load(f)['measurements'][-1]['target']
for name,p in terminal['all_object_poses'].items():
 obj=env.env.objects_dict[name];j=env.sim.model.joint_name2id(obj.joints[0]);adr=int(mon.model.jnt_qposadr[j]);mon.live.qpos[adr:adr+3]=p['position'];mon.live.qpos[adr+3:adr+7]=p['quaternion_wxyz']
mon.live.qpos[mon.qidx]=terminal['joint_positions'];mon.live.qpos[mon.gidx]=terminal['gripper_positions'];mon.live.qvel[:]=0
for name,joint in [('middle','wooden_cabinet_1_middle_level'),('top','wooden_cabinet_1_top_level'),('stove','flat_stove_1_button')]:
 j=env.sim.model.joint_name2id(joint);mon.live.qpos[int(mon.model.jnt_qposadr[j])]=terminal['articulation'][name]
env.sim.forward();m=mon.measure();errors={name:float(np.max(np.abs(np.asarray(p['position'])-np.asarray(m['all_object_poses'][name]['position']))))for name,p in terminal['all_object_poses'].items()};eef_error=float(np.linalg.norm(np.asarray(m['eef_position'])-terminal['eef_position']))
contacts=[]
for i,c in enumerate(mon.live.contact[:mon.live.ncon]):
 a,b=int(c.geom1),int(c.geom2)
 if(a in mon.target_geoms)==(b in mon.target_geoms):continue
 force=np.zeros(6);mon.mj.mj_contactForce(mon.model,mon.live,i,force)
 world=c.frame.reshape(3,3).T@force[:3];world*=1 if b in mon.target_geoms else-1
 other=a if b in mon.target_geoms else b
 contacts.append(dict(pair=[env.sim.model.geom_id2name(a),env.sim.model.geom_id2name(b)],other_object=mon.object_geom_owner.get(other),other_is_robot=other in mon.robot_geoms,normal_z=float(abs(c.frame.reshape(3,3)[0,2])),normal_force=float(force[0]),upward_resultant_force=float(world[2]),contact_z=float(c.pos[2]),object_com_z=float(mon.live.xipos[mon.target_body,2]),penetration=float(-c.dist)))
mass=float(mon.model.body_mass[mon.target_body]);gravity=float(abs(mon.model.opt.gravity[2]));force=sum(c['upward_resultant_force']for c in contacts if not c['other_is_robot'])
report=dict(scope='reconstructed recorded terminal pose, zero robot actions; forces are recomputed, NOT original recorded force measurements',pose_position_max_error=max(errors.values()),eef_error=eef_error,legacy_supported=m['support_contact'],mass_kg=mass,weight_newton=mass*gravity,upward_contact_force_newton=force,force_to_weight_ratio=force/(mass*gravity),contacts=contacts,original_initial_scene_used=True)
assert max(errors.values())<1e-8 and eef_error<1e-6,report
(out/'FORCES.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False));env.close()
