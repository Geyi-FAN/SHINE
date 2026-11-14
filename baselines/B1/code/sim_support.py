"""Only simulator construction, camera transforms, proprioception and pose hold.
No agent/grounding/memory imports. Private native goals live in the evaluator.
"""
import os,sys,json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation

FROZEN=Path('/mnt/disk_4/geyi/audio_switch_benchmark/runtimes/c3r_pi05_744_30k_r15_20261108/runtime')
def configure(out,gpu):
 os.environ.update(MUJOCO_GL='egl',PYOPENGL_PLATFORM='egl',MUJOCO_EGL_DEVICE_ID=str(gpu),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',REVISION_RUN_ROOT=str(out/'sim_runtime'),REVISION_ASSET_CONFIG='/mnt/disk_2/geyi/pi05_small722_20261016/local_assets.json')
 sys.path.insert(0,'/mnt/disk_2/geyi/memory_dataset_v5_fast60_20261013/pipeline/src')
 from revision_pipeline.settings import configure_runtime
 configure_runtime()
 sys.path.insert(0,str(FROZEN/'freeze/simulation/adapters'))
 sys.path.insert(0,'/mnt/disk_2/geyi/pi05_revision_p1/goal_new_state_test_p0_3750_v2_stratified/src')

def build_env(root,fixture,out):
 import hashlib,h5py
 from PIL import Image
 from types import SimpleNamespace
 from revision_eval.env import make_libero_env,settle_env
 from revisionlab.render_context import bind_render_context
 assets=fixture['assets']
 for a in assets.values():
  assert hashlib.sha256((root/a['path']).read_bytes()).hexdigest()==a['sha256']
 task=SimpleNamespace(problem_folder='',bddl_file=str(root/assets['bddl_file']['path']),language='')
 env,_=make_libero_env(task,SimpleNamespace(env_img_res=256,seed=fixture['scene_seed'],control_mode='relative'))
 env.env.ignore_done=True;env.env.horizon=100000;bind_render_context(env)
 with h5py.File(root/assets['source_hdf']['path']) as f:obs=settle_env(env,f['states'][0].copy(),10)
 actual=np.ascontiguousarray(obs['agentview_image'][::-1,::-1]);reference=np.asarray(Image.open(root/assets['reference_image']['path']).convert('RGB'))
 delta=np.abs(actual.astype(int)-reference.astype(int));checks={'max_delta':int(delta.max()),'mean_delta':float(delta.mean()),'pass':bool(delta.max()<=2 and delta.mean()<=.001),'fixture':fixture['state_id']}
 (out/'initial_scene.json').write_text(json.dumps(checks,indent=2));Image.fromarray(actual).save(out/'initial.png')
 assert checks['pass'],'initial scene mismatch'
 return env,obs

def policy_observation(obs):
 from PIL import Image
 def camera(k):return np.asarray(Image.fromarray(np.ascontiguousarray(obs[k][::-1,::-1])).resize((224,224),Image.Resampling.BILINEAR))
 q=np.asarray(obs['robot0_eef_quat'],float).copy();q[3]=np.clip(q[3],-1,1);den=np.sqrt(1-q[3]**2)
 aa=np.zeros(3) if np.isclose(den,0) else q[:3]*2*np.arccos(q[3])/den
 return {'image':camera('agentview_image'),'wrist':camera('robot0_eye_in_hand_image'),'state':np.r_[obs['robot0_eef_pos'],aa,obs['robot0_gripper_qpos']].astype(np.float32)}

class PoseHold:
 def __init__(self,obs,controller):
  assert controller.use_delta
  self.xyz=np.asarray(obs['robot0_eef_pos']).copy();self.rot=Rotation.from_quat(obs['robot0_eef_quat']).as_matrix();self.scale=(np.asarray(controller.output_max)-np.asarray(controller.output_min))/2
 def action(self,obs):
  rot=Rotation.from_quat(obs['robot0_eef_quat']).as_matrix()
  d=np.r_[self.xyz-obs['robot0_eef_pos'],Rotation.from_matrix(self.rot@rot.T).as_rotvec()]
  return np.r_[np.clip(d/self.scale,-1,1),0.]

class PrivateGoals:
 def __init__(self):
  from libero.libero import benchmark,get_libero_path
  from libero.libero.envs.bddl_utils import robosuite_parse_problem
  suite=benchmark.get_benchmark_dict()['libero_goal']()
  self.goals=[robosuite_parse_problem(str(Path(get_libero_path('bddl_files'))/suite.get_task(i).problem_folder/suite.get_task(i).bddl_file))['goal_state'] for i in range(10)]
 def measure(self,env):return [bool(all(env.env._eval_predicate(p) for p in goals)) for goals in self.goals]
