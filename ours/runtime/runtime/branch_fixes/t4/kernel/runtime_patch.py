"""T01 candidate: current ownership evidence and guarded late policy delivery.

Reads camera images, measured robot state and fresh YOLO only. It does not
choose a plan, generate a subgoal, change scoring, or write the simulator.
"""
import copy
import inspect
import math
from pathlib import Path
import textwrap
import time
import numpy as np


def revalidate_late_policy(bridge,context,old_points,before,proof,job):
    age=time.monotonic()-job['capture_monotonic']
    token=tuple(job['token'])
    reason=None
    if bridge.state.mode!='running' or token!=tuple(bridge.token()) or bridge.closed or bridge.terminal_reason:
        reason='identity_or_lifecycle_changed'
    elif not 3.<age<=10.:
        reason='outside_bounded_revalidation_window'
    elif proof.get('passed') is not True:
        reason='original_proprio_MAIN_continuity_failed'
    # A stable global MAIN mean cannot alone establish that the action's
    # relevant object is unchanged. Also inspect WRIST and fresh typed points.
    errors={}
    if reason is None:
        for key in ['agentview_image','robot0_eye_in_hand_image']:
            if key not in before or key not in bridge.obs or np.shape(before[key])!=np.shape(bridge.obs[key]):
                reason='missing_or_changed_camera';break
            errors[key]=float(np.abs(np.asarray(before[key],np.float32)-np.asarray(bridge.obs[key],np.float32)).mean())
            if errors[key]>1.:
                reason='current_camera_content_changed';break
    if reason is None:
        qa=np.asarray(before.get('robot0_eef_quat',[]),float)
        qb=np.asarray(bridge.obs.get('robot0_eef_quat',[]),float)
        if qa.shape!=(4,) or qb.shape!=(4,) or not np.isfinite(np.r_[qa,qb]).all() or min(np.linalg.norm(qa),np.linalg.norm(qb))<1e-9:
            reason='missing_rotation_evidence'
        elif 2*math.acos(float(np.clip(abs(np.dot(qa,qb)/(np.linalg.norm(qa)*np.linalg.norm(qb))),0,1)))>.02:
            reason='measured_hand_rotation_changed'
    details={}
    if reason is None:
        valid,details=bridge.observed_continuity('policy',context,old_points,copy.deepcopy(proof))
        ref=(context.get('decision')or{}).get('reference')or{}
        name=ref.get('entity','')+'.'+ref.get('keypoint','')
        if not valid or not ref or name not in details.get('point_displacements_MAIN224_px',{}):
            reason='current_required_reference_not_revalidated'
    passed=reason is None
    bridge.log('t01_late_policy_current_revalidation',passed=passed,reason=reason,
               original_capture_age_s=age,original_capture_monotonic=job['capture_monotonic'],
               dual_view_mean_pixel_error=errors,observed_reference_evidence=details,
               identity=list(token),creates_completion=False,rewrites_capture_time=False)
    return passed


def install_ownership(cls):
    if getattr(cls,'_t01_empty_gripper_guard',False):return
    original=cls._holding
    def holding(mon,sample):
        width=sample['width']
        was=mon.held
        contradicted=bool(np.isfinite(width) and width<mon.settings.min_width_m and was not in ('none','unknown'))
        if contradicted:
            mon.held='none'
            mon.held_width=None
            mon.last_held_frame=-10000
        original(mon,sample)
        if contradicted:
            mon.holding_evidence['negative_ownership_evidence']=dict(
                previous_estimate=was,current_estimate=mon.held,frame=sample['frame'],
                measured_width_m=width,existing_empty_threshold_m=mon.settings.min_width_m,
                reason='measured_fingers_below_existing_empty_threshold',
                source='current_robot_proprioception',creates_completion=False)
    cls._holding=holding
    cls._t01_empty_gripper_guard=True


def install_bridge(cls):
    if getattr(cls,'_t01_late_policy_revalidation',False):return
    original=cls.network
    source=textwrap.dedent(inspect.getsource(original))
    old="if role=='policy'and time.monotonic()-job['capture_monotonic']>3.:"
    assert source.count(old)==1,'Unexpected bridge source; refuse to bypass lifecycle wrappers'
    new="if role=='policy'and time.monotonic()-job['capture_monotonic']>3. and not _t01_revalidate(self,context,old_points,before,proof,job):"
    source=source.replace(old,new)
    namespace=dict(original.__globals__,_t01_revalidate=revalidate_late_policy)
    exec(compile(source,str(Path(__file__).resolve()),'exec'),namespace)
    cls.network=namespace['network']
    original_init=cls.__init__
    def initialize(bridge,*args,**kwargs):
        original_init(bridge,*args,**kwargs)
        install_ownership(bridge.mon_class)
        import text_transport
        import t06_goal_language
        from t4_adapter import objectives as t4_objectives
        t06_goal_language.bind_logger(bridge.log)
        from t09_lifecycle import identity as t09_identity
        bridge.log('t09_lifecycle_candidate_installed',**t09_identity(bridge.__class__))
        from t06l_observation_handoff import identity as t06l_handoff_identity
        bridge.log('t06l_observation_handoff_installed',**t06l_handoff_identity(bridge.__class__))
        from t06l_inspection import identity as t06l_identity
        bridge.log('t06l_inspection_candidate_installed',**t06l_identity())
        import t01r_reacquisition,stage_lifecycle
        t01r_reacquisition.bind_logger(bridge.log)
        bridge.log('t01r_runtime_candidate_installed',version='observed-placement-reacquisition-v1',actual_classify_guarded=bool(getattr(stage_lifecycle.classify,'_t01r_placement_reacquisition',False)),agent_generates_plan=True,no_completion_created=True,source=str(Path(__file__).resolve()))
        import t09_goal_prefix
        t09_goal_prefix.bind_logger(bridge.log)
        bridge.log('t09_runtime_candidate_installed',version='keep-prefix-determiner-order-v1',actual_goal_prefix_guarded=bool(getattr(t4_objectives.normalize_selected_task,'_t09_prefix_determiner',False)),agent_task_rewritten=False,thresholds_changed=False,source=str(Path(__file__).resolve()))
        bridge.log('t06_runtime_candidate_installed',version='explicit-noun-determiner-v1',actual_goal_language_guarded=bool(getattr(t4_objectives.normalize_selected_task,'_t06_explicit_noun_determiner',False)),actual_recovery_transport_guarded=bool(getattr(__import__('local_transport').connection,'_t06_recovery_affinity',False)),changes='goal-language parsing only; original Agent Task and scoring thresholds preserved',source=str(Path(__file__).resolve()))
        from t3repair import wording
        bridge.log('t03_runtime_candidate_installed',version='intrinsic-wording-reuse-v1',actual_wording_guarded=bool(getattr(wording.exact_authorized_task,'_t03_intrinsic_guard',False)),source=str(Path(__file__).resolve()),generates_subgoal=False)
        bridge.log('t02_runtime_candidate_installed',version='planning-174-affinity-v1',actual_transport_guarded=bool(getattr(text_transport.connection,'_t02_planning_affinity',False)),planning_endpoint='http://127.0.0.1:18184/v1',actual_bridge_module=bridge.__class__.__module__,prompt_rewritten=False,model_changed=False)
        bridge.log('t01_runtime_candidate_installed',
                   version='ownership-currentness-v3',
                   actual_bridge_module=bridge.__class__.__module__,
                   actual_monitor_guarded=bool(getattr(bridge.mon_class,'_t01_empty_gripper_guard',False)),
                   scope='image/proprioception input guards; no new planner or scoring',
                   source=str(Path(__file__).resolve()))
    cls.__init__=initialize
    cls._t01_late_policy_revalidation=True


def install(bridge_class=None):
    from t06_recovery_transport import install as install_t06_recovery
    install_t06_recovery()
    from t06_goal_language import install as install_t06_goal_language
    install_t06_goal_language()
    from t09_goal_prefix import install as install_t09_goal_prefix
    install_t09_goal_prefix()
    from t03_wording import install as install_t03_wording
    install_t03_wording()
    from t02_transport import install as install_t02_transport
    install_t02_transport()
    from observed_completion import ObservedCompletion
    if bridge_class is None:
        from g2.bridge import SingleOwnerBridge
        bridge_class=SingleOwnerBridge
    install_ownership(ObservedCompletion)
    install_bridge(bridge_class)
    from t09_lifecycle import install as install_t09_lifecycle
    install_t09_lifecycle(bridge_class)
    from t01r_reacquisition import install as install_t01r
    install_t01r()
    from t01r_video_shape import install as install_t01r_video
    install_t01r_video(bridge_class)
    from t06l_inspection import install as install_t06l
    install_t06l()
    from t06l_observation_handoff import install as install_t06l_handoff
    install_t06l_handoff(bridge_class)

