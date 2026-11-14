import copy
import inspect
import math
from pathlib import Path
import textwrap
import time
import numpy as np

def revalidate_late_policy(bridge, context, old_points, before, proof, job):
    age = time.monotonic() - job['capture_monotonic']
    token = tuple(job['token'])
    reason = None
    if bridge.state.mode != 'running' or token != tuple(bridge.token()) or bridge.closed or bridge.terminal_reason:
        reason = 'identity_or_lifecycle_changed'
    elif not 3.0 < age <= 10.0:
        reason = 'outside_bounded_revalidation_window'
    elif proof.get('passed') is not True:
        reason = 'original_proprio_MAIN_continuity_failed'
    errors = {}
    if reason is None:
        for key in ['agentview_image', 'robot0_eye_in_hand_image']:
            if key not in before or key not in bridge.obs or np.shape(before[key]) != np.shape(bridge.obs[key]):
                reason = 'missing_or_changed_camera'
                break
            errors[key] = float(np.abs(np.asarray(before[key], np.float32) - np.asarray(bridge.obs[key], np.float32)).mean())
            if errors[key] > 1.0:
                reason = 'current_camera_content_changed'
                break
    if reason is None:
        qa = np.asarray(before.get('robot0_eef_quat', []), float)
        qb = np.asarray(bridge.obs.get('robot0_eef_quat', []), float)
        if qa.shape != (4,) or qb.shape != (4,) or (not np.isfinite(np.r_[qa, qb]).all()) or (min(np.linalg.norm(qa), np.linalg.norm(qb)) < 1e-09):
            reason = 'missing_rotation_evidence'
        elif 2 * math.acos(float(np.clip(abs(np.dot(qa, qb) / (np.linalg.norm(qa) * np.linalg.norm(qb))), 0, 1))) > 0.02:
            reason = 'measured_hand_rotation_changed'
    details = {}
    if reason is None:
        (valid, details) = bridge.observed_continuity('policy', context, old_points, copy.deepcopy(proof))
        ref = (context.get('decision') or {}).get('reference') or {}
        name = ref.get('entity', '') + '.' + ref.get('keypoint', '')
        if not valid or not ref or name not in details.get('point_displacements_MAIN224_px', {}):
            reason = 'current_required_reference_not_revalidated'
    passed = reason is None
    bridge.log('t01_late_policy_current_revalidation', passed=passed, reason=reason, original_capture_age_s=age, original_capture_monotonic=job['capture_monotonic'], dual_view_mean_pixel_error=errors, observed_reference_evidence=details, identity=list(token), creates_completion=False, rewrites_capture_time=False)
    return passed

def install_ownership(cls):
    if getattr(cls, '_t01_empty_gripper_guard', False):
        return
    original = cls._holding

    def holding(mon, sample):
        # Only a causally confirmed IMAGE/PROPRIO release can retire grasp
        # history. Final target success alone is not release evidence.
        placements={'bowl_stove','bowl_plate','bowl_cabinet','bowl_drawer',
                    'cheese_bowl','bottle_cabinet','bottle_rack'}
        fence=getattr(mon,'ownership_released_frame',-1)
        for event in getattr(mon,'events',[]):
            frame=event.get('confirmed_step',-1)
            operation=event.get('operation','')
            if (event.get('outcome')!='completed' or event.get('source')!='s1_rgb_proprio_v1'
                    or not isinstance(frame,int) or not fence<frame<=sample['frame']
                    or frame<mon.last_held_frame
                    or not(operation in placements or operation.startswith(('return_','release_')))):
                continue
            obj=event.get('object')
            if mon.held not in (obj,'none','unknown'):
                continue
            mon.held='none';mon.held_width=None;mon.last_held_frame=-10000
            fence=mon.ownership_released_frame=frame
        width = sample['width']
        was = mon.held
        contradicted = bool(np.isfinite(width) and width < mon.settings.min_width_m and (was not in ('none', 'unknown')))
        if contradicted:
            mon.held = 'none'
            mon.held_width = None
            mon.last_held_frame = -10000
        history=mon.samples
        if fence>=0:
            from collections import deque
            mon.samples=deque((row for row in history if row['frame']>fence),maxlen=history.maxlen)
        try:
            original(mon, sample)
        finally:
            mon.samples=history
        if fence>=0:
            mon.holding_evidence['grasp_history_after_frame']=fence
        if contradicted:
            mon.holding_evidence['negative_ownership_evidence'] = dict(previous_estimate=was, current_estimate=mon.held, frame=sample['frame'], measured_width_m=width, existing_empty_threshold_m=mon.settings.min_width_m, reason='measured_fingers_below_existing_empty_threshold', source='current_robot_proprioception', creates_completion=False)
    cls._holding = holding
    cls._t01_empty_gripper_guard = True

def install_bridge(cls):
    if getattr(cls, '_t01_late_policy_revalidation', False):
        return
    original = cls.network
    source = textwrap.dedent(inspect.getsource(original))
    old = "if role=='policy'and time.monotonic()-job['capture_monotonic']>3.:"
    assert source.count(old) == 1, 'Unexpected bridge source; refuse to bypass lifecycle wrappers'
    new = "if role=='policy'and time.monotonic()-job['capture_monotonic']>3. and not _t01_revalidate(self,context,old_points,before,proof,job):"
    source = source.replace(old, new)
    namespace = dict(original.__globals__, _t01_revalidate=revalidate_late_policy)
    exec(compile(source, str(Path(__file__).resolve()), 'exec'), namespace)
    cls.network = namespace['network']
    original_init = cls.__init__

    def initialize(bridge, *args, **kwargs):
        original_init(bridge, *args, **kwargs)
        install_ownership(bridge.mon_class)
        bridge.log('currentness_ownership_guard_installed', source='reviewed_T4', creates_completion=False)
    cls.__init__ = initialize
    cls._t01_late_policy_revalidation = True
