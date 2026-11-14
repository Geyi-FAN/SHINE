"""Isolated native LIBERO runtime for preparing data, never loads a policy."""
import os
import sys
from pathlib import Path
from schema import ROOT,WORK
os.environ.setdefault('MUJOCO_GL','egl')
os.environ.setdefault('PYOPENGL_PLATFORM','egl')
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ['REVISION_RUN_ROOT']=str(ROOT/'mini/runtime'/str(os.getpid()))
os.environ['REVISION_ASSET_CONFIG']=os.environ.get('MEMORY_ASSET_CONFIG',str(ROOT/'mini/assets.json'))
sys.path[:0]=[str(WORK/'memory_dataset_v5_fast60_20261013/pipeline/src'),
             str(WORK/'pi05_revision_p1/goal_new_state_test_p0_3750_v2_stratified/src')]
from revision_pipeline.settings import configure_runtime
configure_runtime()
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np
from libero.libero import benchmark,get_libero_path
from libero.libero.envs import OffScreenRenderEnv
from libero.libero.envs.bddl_utils import robosuite_parse_problem
from omnivla.env_adapters.libero import try_set_control_mode
from omnivla.env_adapters.contact_exit_scenes import sample_scene
from revisionlab.render_context import bind_render_context
from sim_state import capture,restore,identity,observation_state

def new_env(bddl):
    np.random.seed(7)
    env=OffScreenRenderEnv(bddl_file_name=str(bddl),camera_heights=256,camera_widths=256)
    env.env.hard_reset=False;env.env.ignore_done=True;env.env.horizon=10000
    try_set_control_mode(env,'relative');bind_render_context(env)
    env.memory_initialization={'mode':'native_libero_sampler_no_pose_override','cream_cheese_sampler_z_offset_extra_m':0.0}
    return env

def freeze(env,obs):
    c=capture(env)
    c['main_raw_image']=np.asarray(obs['agentview_image']).copy()
    c['wrist_raw_image']=np.asarray(obs['robot0_eye_in_hand_image']).copy()
    c['frozen_observation_state']=observation_state(obs)
    return c

def image_pair(obs):
    return {k:np.ascontiguousarray(obs[v][::-1,::-1]) for k,v in [('image','agentview_image'),('wrist_image','robot0_eye_in_hand_image')]}

def measured_position_error(env,measurement):
    """Independent live-GT consistency check against each free joint's world XYZ."""
    error=0.
    for obj,p in measurement['all_object_poses'].items():
        model=env.env.objects_dict[obj]
        joint=env.sim.model.joint_name2id(model.joints[0]);adr=int(env.sim.model.jnt_qposadr[joint])
        error=max(error,float(np.max(np.abs(env.sim.data.qpos[adr:adr+3]-p['position']))))
    assert error<1e-9,error
    return error

class GeometryRuntime:
    def __init__(self):self.suite=benchmark.get_benchmark_dict()['libero_goal']();self.goal_cache={}
    def goals(self,env,task):
        if task not in self.goal_cache:
            t=self.suite.get_task(task)
            self.goal_cache[task]=robosuite_parse_problem(str(Path(get_libero_path('bddl_files'))/t.problem_folder/t.bddl_file))['goal_state']
        return all(env.env._eval_predicate(g) for g in self.goal_cache[task])
    def frame(self,mon,task):
        from revision_eval.runtime import Runtime
        return Runtime.frame(self,mon,task)
    def monitor(self,env,task):
        from revisionlab.physics import Runtime
        return Runtime.monitor(self,env,task)
