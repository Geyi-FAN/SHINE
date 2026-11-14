"""Agent-authorized bounded observation before acquiring a DIFFERENT object.

This helper never creates a task/subgoal/completion event. It only offers an
existing open-hand6cm clearance tool after two fresh visual reports. Runtime
must suspend selection of the new grasp until the maneuver is finished.
"""
import math
import json
import hashlib

REASON = 'accepted_return_before_different_object_grasp'


class PostReturnHandoff:
    def __init__(self):
        self.attempted = set()
        self.pending = None

    def _evidence(self, mon, event, frame):
        if mon.held != 'none' or not mon.samples or mon.samples[-1]['width'] < .065:
            return None
        if not mon.rgb_rows or mon.rgb_rows[-1]['frame'] != frame:
            return None
        row = mon.rgb_rows[-1]
        old = event['object']
        point = next((p for p in row.get('image_points', []) if p.get('entity') == old and p.get('keypoint') == 'K1'
                      and p.get('source') == 'yolo_image_only' and p.get('frame', frame) == frame
                      and min(p.get('det_confidence', 0), p.get('keypoint_confidence', 0)) >= .35), None)
        xyz = row.get('geometry', {}).get(old + '.K1')
        hand = mon.samples[-1].get('eef_xyz')
        if point is None or hand is None or not mon.stable(old):
            return None
        source_frame=frame;resolution='current';pixel_drift=0.;camera_verified=False
        depth_missing=xyz is None
        if depth_missing:
            # This is proximity context ONLY. Never fill current detector geometry
            # or change the actor's coordinate. Current pixel is still fresh K1.
            current_cal=row.get('camera_calibration')
            if current_cal is None:return None
            camera_fingerprint=json.dumps(current_cal,sort_keys=True)
            for past in reversed(list(mon.rgb_rows)):
                age=frame-past['frame']
                if not 0<age<=24:continue
                prior_point=next((p for p in past.get('image_points',[])if p.get('entity')==old and p.get('keypoint')=='K1'
                    and p.get('source')=='yolo_image_only'and p.get('frame',past['frame'])==past['frame']
                    and min(p.get('det_confidence',0),p.get('keypoint_confidence',0))>=.35),None)
                measured=past.get('geometry',{}).get(old+'.K1')
                if prior_point is None or measured is None or past.get('camera_calibration')is None:continue
                if json.dumps(past['camera_calibration'],sort_keys=True)!=camera_fingerprint:continue
                if not all(math.isfinite(float(v))for v in list(measured)+list(prior_point['yx224'])+list(point['yx224'])):continue
                drift=math.sqrt(sum((a-b)**2 for a,b in zip(prior_point['yx224'],point['yx224'])))
                if drift>3.:continue
                xyz=measured;source_frame=past['frame'];resolution='cached_static_depth';pixel_drift=drift;camera_verified=True
                break
            if xyz is None:return None
        if not all(math.isfinite(float(v)) for v in list(xyz) + list(hand)):
            return None
        distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(xyz, hand)))
        if distance > .12:
            return None
        return dict(frame=frame, object=old, measured_hand_distance_m=distance,
                    gripper_width_m=mon.samples[-1]['width'],
                    old_K1_source='fresh_YOLO_plus_RGBD'if resolution=='current'else'phase_static_cached_YOLO_RGBD',
                    resolution=resolution,source_frame=source_frame,image_point_frame=frame,keypoint='K1',
                    current_depth_missing=depth_missing,cache_age_steps=frame-source_frame,max_cache_age_steps=24,
                    camera_verified=camera_verified,pixel_drift_px=pixel_drift,
                    image_stable=True, creates_completion=False)

    def _context(self, mon, event, stage, proof, phase):
        mon.diagnostics['observation_request_context'] = dict(reason=REASON,
            selected_stage=stage, preceding_observed_return=event, released_object=event['object'],
            measured_clearance_context=proof, phase=phase, allowed_tool='clear_supported_object',
            candidate_tool=dict(height_m=.060, direction='WORLD +z', hold_steps=16, gripper='remain open'),
            instruction='A cached depth, when explicitly labelled, is past proximity context only and NOT current support proof. Inspect current images for the old object independently supported and an empty open hand. Request clear_supported_object only if the short upward path is visibly clear; otherwise observe_only/none. This is an optional observation handoff, not a new user goal or completed grasp.')

    @staticmethod
    def _approved(prediction, old):
        return bool(prediction and prediction.get('held_object') == 'none'
                    and prediction.get('support_visible', {}).get(old) is True
                    and prediction.get('recovery_request') == 'clear_supported_object')

    def propose(self, mon, recovery, decision, frame):
        plan = decision.get('remaining_plan') or []
        if self.pending is not None or not plan or plan[0].get('kind') != 'grasp':
            return None
        prior = next((e for e in reversed(mon.events) if e.get('outcome') == 'completed'
                      and e.get('operation', '').startswith(('return_', 'release_'))), None)
        if prior is None or prior['object'] == plan[0].get('object'):
            return None
        key = (prior['operation'], prior['confirmed_step'])
        if key in self.attempted or recovery.inspection_limit - recovery.inspections < 2 or frame - recovery.last_check < 8:
            return None
        proof = self._evidence(mon, prior, frame)
        if proof is None:
            return None
        self.attempted.add(key)
        self._context(mon, prior, plan[0], proof, 'first_view')
        prediction = recovery.inspect(mon)
        recovery.events.append(dict(frame=frame, event='post_return_handoff_first_view', prior_event=dict(prior),
                                    old_object=prior['object'], next_agent_operation=plan[0]['operation'],
                                    observed_proof=proof, approved=self._approved(prediction, prior['object']),
                                    creates_completion=False))
        if not self._approved(prediction, prior['object']):
            return dict(phase='facts_changed') if prediction and prediction.get('held_object') != 'none' else None
        self.pending = dict(event=dict(prior), stage=dict(plan[0]), first_prediction=dict(prediction),
                            first_frame=frame, phase='wait', until=frame + 8)
        return dict(phase='wait', until=frame + 8, creates_completion=False)

    def advance(self, mon, recovery, frame):
        pending = self.pending
        if pending is None:
            return None
        if frame < pending['until']:
            return dict(phase=pending['phase'], until=pending['until'])
        if pending['phase'] == 'move':
            recovery.events.append(dict(frame=frame, event='post_return_handoff_finished', old_object=pending['event']['object'], creates_completion=False))
            self.pending = None
            mon.diagnostics.pop('observation_request_context', None)
            return dict(phase='finished', creates_completion=False)
        prior = pending['event']
        proof = self._evidence(mon, prior, frame)
        prediction = None
        if proof is not None and frame - pending['first_frame'] >= 8:
            self._context(mon, prior, pending['stage'], proof, 'corroborating_fresh_view')
            prediction = recovery.inspect(mon)
        if proof is None or not self._approved(prediction, prior['object']):
            recovery.events.append(dict(frame=frame, event='post_return_handoff_cancelled', reason='fresh independent visual/support/open-hand corroboration unavailable', creates_completion=False))
            self.pending = None
            mon.diagnostics.pop('observation_request_context', None)
            return dict(phase='finished', cancelled=True, creates_completion=False)
        pending.update(phase='move', until=frame + 16)
        recovery.events.append(dict(frame=frame, event='agent_requested_post_return_clearance', old_object=prior['object'],
            next_agent_operation=pending['stage']['operation'], evidence_frames=[pending['first_frame'], frame],
            height_m=.060, direction='WORLD +z', move_steps=16, gripper='remain open',
            source='two fresh Recovery Agent tool requests plus observed prerequisites', creates_completion=False,
            observed_proof=proof, oracle_pixel_used=False))
        return dict(phase='start_move', until=frame + 16, height_m=.060, creates_completion=False)
