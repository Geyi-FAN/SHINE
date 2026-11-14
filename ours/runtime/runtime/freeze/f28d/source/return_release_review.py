"""Optional supported-return inspection, adapted from the isolated G22 repair.

Requests observation only. The original two-report support/release guards,
pose-hold finger opening and completion/scoring mechanisms remain unchanged.
"""
import numpy as np

ADDENDUM='''SUPPORTED RETURN REVIEW: The CURRENT selected return subgoal explicitly requires returning AND releasing this object. Historical YOLO K2 and fresh K2 establish a candidate location, never support or success. Inspect current MAIN and WRIST for actual surface support. If closed fingers still contact this independently supported return object, you may request release_supported_in_place with that release_object even though it is the current target. If airborne, uncertain or support is occluded, request observe_only. Never infer support from historical images. The request needs a second fresh corroborating inspection and existing measured guards; it never completes a subgoal.'''


def evidence(mon):
    stage=mon.active or{}
    if stage.get('kind')!='return':return None
    obj=stage.get('object');rows=list(mon.samples)[-4:]
    if len(rows)!=4 or rows[-1]['frame']-rows[0]['frame']<8:return None
    if any(b['frame']-a['frame']>4 for a,b in zip(rows,rows[1:])):return None
    ref=mon.history.get(('episode_start',obj,'K2'))
    if ref is None or min(ref.get('det_confidence',0),ref.get('keypoint_confidence',0))<mon.settings.confidence:return None
    if any(not mon.settings.min_width_m<=r['width']<mon.settings.closed_width_m for r in rows):return None
    if mon.held not in('unknown',obj):return None
    points=[mon.point(r,obj,'K2')for r in rows]
    if any(p is None for p in points):return None
    error=max(float(np.linalg.norm(np.asarray(p)-ref['yx224']))for p in points)
    spread=max(float(np.linalg.norm(np.asarray(p)-points[-1]))for p in points)
    motion=max(float(np.linalg.norm(np.asarray(r['eef_xyz'])-rows[-1]['eef_xyz']))for r in rows)
    near=mon.diagnostics.get('holding',{}).get('near_px',{}).get(obj)
    if (error>mon.settings.return_radius_px or spread>mon.settings.stable_radius_px or
        motion>mon.settings.motion_m or near is None or near>mon.settings.near_hand_px):return None
    return dict(object=obj,frames=[r['frame']for r in rows],historical_K2=ref['yx224'],max_return_error_px=error,
                point_spread_px=spread,eef_motion_m=motion,near_hand_px=near,
                source='fresh YOLO/proprioception; candidate location only, not support or completion')


def request(mon,recovery,step,decision):
    if not decision or decision.get('status')!='plan_ready'or not mon.active:return False
    if step-mon.entered<180 or recovery.pending is not None or recovery.inspections>recovery.inspection_limit-2:return False
    attempts=getattr(recovery,'return_review_attempts',{});key=(mon.active['operation'],mon.entered);count=attempts.get(key,0)
    if count>=2 or step-mon.entered<180*(count+1)or step-recovery.last_check<8:return False
    proof=evidence(mon)
    if proof is None:return False
    recovery.return_review_attempts=attempts;attempts[key]=count+1
    mon.diagnostics['observation_request_context']=dict(reason='return_in_position_but_fingers_closed',selected_stage=dict(mon.active),observed_return_alignment=proof,permission='inspection only; current support must be visually assessed')
    prediction=recovery.inspect(mon)
    recovery.events.append(dict(frame=step,event='stalled_return_review',observed_proof=proof,prediction=prediction,creates_completion=False))
    if prediction and prediction.get('recovery_request')=='release_supported_in_place':
        recovery.pending='holding';recovery.return_review_pending=True;return True
    return False


def specialize(recovery):
    base=recovery.__class__
    class SupportedReturnRecovery(base):
        def inspect(self,mon):
            if getattr(self,'return_review_pending',False)and self.grip_release_until is None:
                proof=evidence(mon)
                if proof is None:
                    self.return_review_pending=False
                    self.events.append(dict(frame=mon.last,event='supported_return_review_cancelled',reason='fresh alignment/closed-hand evidence lost',creates_completion=False))
                    return None
                mon.diagnostics['observation_request_context']=dict(reason='return_in_position_but_fingers_closed',selected_stage=dict(mon.active),observed_return_alignment=proof)
            result=super().inspect(mon)
            if self.grip_release_until is not None:self.return_review_pending=False
            return result
    recovery.__class__=SupportedReturnRecovery
    return recovery
