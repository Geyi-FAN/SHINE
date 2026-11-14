"""Evaluation input builder matching the training prompt / reference schema."""
import numpy as np
from PIL import Image
from schema import gt_from_measurement,gt_text

def resize(rgb):
    return np.asarray(Image.fromarray(np.asarray(rgb,np.uint8)).resize((224,224),Image.Resampling.BILINEAR))

def build_inputs(case,variant,obs,episode_initial_policy_rgb,measurement=None,first_state=None):
    """obs is raw LIBERO observation; initial RGB is already policy-oriented.

    first_state pins the saved same-time proprio on the first call only. The
    caller must measure live GT at every subsequent inference, not replay GT.
    """
    assert variant in 'ABCD'
    q=np.asarray(obs['robot0_eef_quat'],np.float64).copy();q[3]=np.clip(q[3],-1.,1.)
    den=np.sqrt(1-q[3]*q[3]);aa=np.zeros(3) if np.isclose(den,0.) else q[:3]*2*np.arccos(q[3])/den
    state=np.r_[obs['robot0_eef_pos'],aa,obs['robot0_gripper_qpos']].astype(np.float32)
    if first_state is not None:state=np.asarray(first_state,np.float32).copy()
    instruction=case['instruction']
    if variant in 'CD':
        if case['kind']=='normal':instruction=gt_text(instruction,None,{}, {},{},available=False)
        else:
            if measurement is None:raise ValueError('Current live measurement required for privileged GT inference')
            instruction=gt_from_measurement(instruction,case['restore_object'],case['initial_xyz'],measurement)
    out={'observation/image':resize(obs['agentview_image'][::-1,::-1]),
         'observation/wrist_image':resize(obs['robot0_eye_in_hand_image'][::-1,::-1]),
         'observation/state':state,'prompt':instruction}
    if variant in 'BD':out['observation/initial_image']=resize(episode_initial_policy_rgb)
    return out
