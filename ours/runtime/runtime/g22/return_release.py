"""Observed stalled-return review. No simulator poses or completion labels."""
import numpy as np

ADDENDUM='''\nSUPPORTED RETURN REVIEW: If observation_request_context.reason is return_in_position_but_fingers_closed, the CURRENT selected task explicitly requires returning AND releasing this object. The supplied historic YOLO K2 and fresh K2 are image references, not proof of support or success. Inspect CURRENT MAIN and WRIST for actual existing surface support. If closed fingers are still contacting the supported return object, request release_supported_in_place with that release_object, even though it is the current return target. Opening in place fulfils the requested release without transporting it. If it is airborne or support is occluded/uncertain, request observe_only. Never infer current support from the initial image. A request needs a second fresh independently corroborating inspection and measured guards; it never marks return completed.'''

def evidence(mon):
    stage=mon.active or {}
    if stage.get('kind')!='return':return None
    obj=stage.get('object');rows=list(mon.samples)[-4:]
    if len(rows)<4 or rows[-1]['frame']-rows[0]['frame']<8:return None
    ref=mon.history.get(('episode_start',obj,'K2'))
    if ref is None or min(ref.get('det_confidence',0),ref.get('keypoint_confidence',0))<mon.settings.confidence:return None
    if any(not mon.settings.min_width_m<=r['width']<mon.settings.closed_width_m for r in rows):return None
    if mon.held not in ('unknown',obj):return None
    points=[mon.point(r,obj,'K2') for r in rows]
    if any(p is None for p in points):return None
    err=max(float(np.linalg.norm(np.asarray(p)-ref['yx224'])) for p in points)
    spread=max(float(np.linalg.norm(np.asarray(p)-points[-1])) for p in points)
    motion=max(float(np.linalg.norm(np.asarray(r['eef_xyz'])-rows[-1]['eef_xyz'])) for r in rows)
    if err>mon.settings.return_radius_px or spread>mon.settings.stable_radius_px or motion>mon.settings.motion_m:return None
    near=mon.diagnostics.get('holding',{}).get('near_px',{}).get(obj)
    if near is None or near>mon.settings.near_hand_px:return None
    return dict(object=obj,frames=[r['frame']for r in rows],historical_K2=ref['yx224'],max_return_error_px=err,point_spread_px=spread,eef_motion_m=motion,near_hand_px=near,source='fresh YOLO + measured robot; no object GT')

def inspect_stalled_return(mon,recovery,step,decision):
    if not decision or decision.get('status')!='plan_ready' or not mon.active:return False
    if step-mon.entered<180 or recovery.pending is not None or recovery.inspections>recovery.inspection_limit-2:return False
    attempts=getattr(recovery,'g22_return_attempts',{})
    key=(mon.active['operation'],mon.entered);count=attempts.get(key,0)
    if count>=2 or step-mon.entered<180*(count+1) or step-recovery.last_check<8:return False
    proof=evidence(mon)
    if proof is None:return False
    recovery.g22_return_attempts=attempts;attempts[key]=count+1
    mon.diagnostics['observation_request_context']=dict(reason='return_in_position_but_fingers_closed',selected_stage=dict(mon.active),observed_return_alignment=proof,permission='request inspection only; support must be judged from current images')
    prediction=recovery.inspect(mon)
    recovery.events.append(dict(frame=step,event='stalled_return_review',observed_proof=proof,prediction=prediction,creates_completion=False))
    if prediction and prediction.get('recovery_request')=='release_supported_in_place':
        recovery.pending='holding';recovery.g22_release_review_pending=True;return True
    return False

def install(bridge_class):
    """Opt-in generated-kernel extension; frozen source remains byte-identical."""
    import recovery_observer
    if ADDENDUM not in recovery_observer.SYSTEM:recovery_observer.SYSTEM+=ADDENDUM
    original=bridge_class.build_run_function
    def build(bridge):
        base=bridge.recovery_class
        class ReturnRecovery(base):
            def inspect(self,mon):
                if getattr(self,'g22_release_review_pending',False) and self.grip_release_until is None:
                    proof=evidence(mon)
                    if proof is None:
                        self.g22_release_review_pending=False
                        self.events.append(dict(frame=mon.last,event='supported_return_review_cancelled',reason='fresh alignment/closed-hand evidence no longer valid',creates_completion=False))
                        return None
                    mon.diagnostics['observation_request_context']=dict(reason='return_in_position_but_fingers_closed',selected_stage=dict(mon.active),observed_return_alignment=proof)
                result=super().inspect(mon)
                if self.grip_release_until is not None:self.g22_release_review_pending=False
                return result
        bridge.recovery_class=ReturnRecovery
        original(bridge)
        import ast
        path=bridge.root/'generated_kernel.py';tree=ast.parse(path.read_text());changed=0
        # Insert directly before the unique stagnation branch, retaining the
        # existing pending-release controller and its two-frame guards.
        for parent in ast.walk(tree):
            for field,value in ast.iter_fields(parent):
                if not isinstance(value,list):continue
                for i,node in enumerate(list(value)):
                    if not changed and isinstance(node,ast.If) and 'REPAIR_STAGNATION_OBSERVATION' in ast.unparse(node.test):
                        extra=ast.parse('if not observation_wait and G22_INSPECT_RETURN(mon,recovery,step,decision):\n recovery_wait_until=step+8\n observation_wait=True').body[0]
                        value.insert(i,extra);changed+=1
        assert changed==1,changed
        ast.fix_missing_locations(tree);ns=dict(bridge.run_function.__globals__,G22_INSPECT_RETURN=inspect_stalled_return)
        exec(compile(tree,str(path),'exec'),ns);bridge.run_function=ns['run'];path.write_text(ast.unparse(tree)+'\n')
    bridge_class.build_run_function=build
