"""Admit an Agent's observed same-object reacquisition before its old placement.

The original C3r path only admits this prerequisite for return stages. Keep
its fresh image/proprioception proof and exact-next-goal guard for recognized
placements too. Do not invent a grasp, coordinates, completion or a new goal.
"""
from functools import wraps
import math

VERSION='observed-placement-reacquisition-v1'
_logger=None

def bind_logger(logger):
    global _logger
    _logger=logger

def placement_admission(active,plan,frame,width,held,visual,destinations):
    if not active or active.get('kind')!='target' or not isinstance(plan,list) or len(plan)<2:
        return None
    obj=active.get('object');destination=destinations.get(active.get('operation'))
    if not destination or destination[0]!=obj:
        return None
    key=lambda s:tuple(s.get(k)for k in ('operation','kind','object'))
    first=plan[0]
    if first.get('kind')!='grasp' or first.get('object')!=obj or first.get('operation')!='grasp_'+obj or key(plan[1])!=key(active):
        return None
    v=visual or {};age=frame-v.get('frame',-1000)
    if not (0<=age<=8 and isinstance(width,(int,float)) and math.isfinite(width) and width>=.065
            and held=='none' and v.get('held_object')=='none' and v.get('support_visible',{}).get(obj)is True):
        return None
    return dict(mode='interrupt_for_reacquisition',reason='Agent_selected_same_object_grasp_then_resume_unfinished_placement',
        interrupted_operation=active['operation'],unfinished_goal_retained=True,
        evidence_frame=v['frame'],creates_completion=False,source='image_observation_and_measured_open_empty_hand')

def install(module=None,destinations=None):
    if module is None:
        import stage_lifecycle as module
    if destinations is None:
        from observed_completion import DESTINATIONS as destinations
    old=module.classify
    if getattr(old,'_t01r_placement_reacquisition',False):return
    @wraps(old)
    def classify(active,plan,frame,width,held,visual):
        if active and active.get('kind')=='target' and (not isinstance(width,(int,float)) or not math.isfinite(width)):
            return dict(mode='reject',reason='current_measured_gripper_width_unavailable',creates_completion=False)
        original=old(active,plan,frame,width,held,visual)
        if original['mode']!='reject':return original
        result=placement_admission(active,plan,frame,width,held,visual,destinations)
        if result is None:return original
        if _logger:_logger('t01r_placement_reacquisition_admitted',version=VERSION,**result)
        return result
    classify._t01r_placement_reacquisition=True
    module.classify=classify
