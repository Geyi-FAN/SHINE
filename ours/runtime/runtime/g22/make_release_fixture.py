"""Reconstruct a stopped pose for a release diagnostic, not replay equivalence."""
import argparse,copy,gzip,json,sys
from pathlib import Path
import numpy as np
B=Path(__file__).resolve().parents[1];sys.path[:0]=[str(B),str(B/'g2')]
from bootstrap import configure
from g22.context import restore_complete

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False);(args.out/'logs').mkdir()
    core,runner,authority=configure(args.out,4)
    from sim_runtime import GeometryRuntime,new_env,get_libero_path
    from hold_gate import PoseHold
    from PIL import Image
    cid='SW4_T02_M2_T08_SWITCH_T02_M2_S04';source=Path('/mnt/disk_4/geyi/voice_f28d_G21_20261101/G21_natural8_v1')/cid
    case=next(c for c in json.loads((B/'g2/fixed32.json').read_text())if c['case_id']==cid)
    rt=GeometryRuntime();t=rt.suite.get_task(case['source_task']);env=new_env(Path(get_libero_path('bddl_files'))/t.problem_folder/t.bddl_file)
    ctx=dict(np.load(case['initial_state_file']));obs=restore_complete(env,ctx,authority)
    last=json.load(gzip.open(source/'gateway_trace.json.gz','rt'))['measurements'][-1]['source'];robot=env.env.robots[0]
    env.sim.data.qpos[robot._ref_joint_pos_indexes]=last['joint_positions'];env.sim.data.qpos[robot._ref_gripper_joint_pos_indexes]=last['gripper_positions']
    for name,p in last['all_object_poses'].items():
        obj=env.env.objects_dict.get(name)
        if obj and obj.joints:
            env.sim.data.set_joint_qpos(obj.joints[0],np.r_[p['position'],p['quaternion_wxyz']])
    for level,q in last['articulation'].items():
        name='wooden_cabinet_1_'+level+'_joint'
        if name in env.sim.model.joint_names:env.sim.data.set_joint_qpos(name,q)
    env.sim.data.qvel[:]=0;env.sim.forward();robot.controller.update(force=True);robot.controller.reset_goal();robot.gripper.current_action[:]=1
    obs=env.env._get_observations(force_update=True);hold=PoseHold(obs,robot.controller)
    for _ in range(12):obs,*_=env.step(hold.action(obs))
    context=authority.state.capture(env);context.update(main_raw_image=obs['agentview_image'],wrist_raw_image=obs['robot0_eye_in_hand_image']);np.savez_compressed(args.out/'supported.npz',**context)
    Image.fromarray(obs['agentview_image'][::-1,::-1]).save(args.out/'MAIN.png');Image.fromarray(obs['robot0_eye_in_hand_image'][::-1,::-1]).save(args.out/'WRIST.png')
    now=rt.monitor(env,case['source_task']).measure();np0=np.asarray(case['initial_xyz']['wine_bottle_1']);report=dict(scope='reconstructed final recorded robot/object pose; zero initial velocities and 12 settling controls; NOT exact trajectory continuation',source=str(source),case=case,private_fixture_validation=dict(supported=now['support_contact'],finger_contact=now['finger_contact'],width_m=now['gripper_gap'],return_error_m=float(np.linalg.norm(np.asarray(now['object_position'])-np0))),controller_identity=authority.state.identity(context))
    (args.out/'fixture.json').write_text(json.dumps(report,indent=2));print(json.dumps(report['private_fixture_validation']),flush=True);env.close()
if __name__=='__main__':main()
