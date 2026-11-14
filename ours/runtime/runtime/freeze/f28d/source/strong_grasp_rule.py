"""Conservative observed grasp evidence, initially OFFLINE ONLY.

No environment, contact label or scoring input. A candidate is not a ground-truth
grasp; held-out replay/closed-loop validation is required before any admission.
"""
import numpy as np


def inspect(rows,stage,entered,frame):
    obj=stage['object'];key=obj+'.K1'
    out=dict(ready=False,reason='unsupported_object',creates_completion=False)
    if stage.get('kind')!='grasp'or obj not in('cheese','wine_bottle'):return out
    def point(row):
        p=next((p for p in row.get('image_points',[])if p.get('entity')==obj and p.get('keypoint')=='K1'),None)
        if p is None or p.get('source')!='yolo_image_only'or p.get('frame',row['frame'])!=row['frame']:return None
        if min(p.get('det_confidence',0),p.get('keypoint_confidence',0))<.7:return None
        xyz=np.asarray(row.get('geometry',{}).get(key,[]),float)
        return xyz if xyz.shape==(3,)and np.isfinite(xyz).all()else None
    origin=[point(r)for r in rows if entered<=r['frame']<=entered+12]
    origin=[p for p in origin if p is not None]
    if len(origin)<3:return dict(out,reason='three_early_reference_frames_required')
    recent=[r for r in rows if max(entered,frame-24)<=r['frame']<=frame][-7:]
    if len(recent)!=7 or recent[-1]['frame']!=frame or recent[-1]['frame']-recent[0]['frame']<20:
        return dict(out,reason='seven_current_frames_over20steps_required')
    if any(b['frame']-a['frame']>4 for a,b in zip(recent,recent[1:])):return dict(out,reason='observation_gap')
    points=[point(r)for r in recent]
    if any(p is None for p in points):return dict(out,reason='fresh_high_confidence_depth_required')
    if not all(.002<=r.get('sensor',{}).get('width',0)<.060 for r in recent):
        return dict(out,reason='closed_nonempty_finger_width_not_sustained')
    hand=np.asarray([r['sensor']['eef_xyz']for r in recent],float);points=np.asarray(points)
    if hand.shape!=(7,3)or not np.isfinite(hand).all():return dict(out,reason='invalid_proprioception')
    origin_z=float(np.median(np.asarray(origin)[:,2]));lift=points[:,2]-origin_z;offsets=points-hand
    offset_spread=max(float(np.linalg.norm(a-b))for a in offsets for b in offsets)
    object_move=points[-1]-points[0];hand_move=hand[-1]-hand[0]
    metrics=dict(evidence_frames=[r['frame']for r in recent],minimum_target_lift_m=float(lift.min()),
        maximum_hand_distance_m=float(np.linalg.norm(offsets,axis=1).max()),relative_offset_spread_m=offset_spread,
        object_motion_m=float(np.linalg.norm(object_move)),hand_motion_m=float(np.linalg.norm(hand_move)),
        motion_disagreement_m=float(np.linalg.norm(object_move-hand_move)))
    good=(metrics['minimum_target_lift_m']>=.040 and metrics['maximum_hand_distance_m']<=.080 and
          offset_spread<=.006 and min(metrics['object_motion_m'],metrics['hand_motion_m'])>=.015 and
          metrics['motion_disagreement_m']<=.005)
    return dict(out,ready=bool(good),reason='sustained_high_confidence_target_lift_and_rigid_hand_comotion'if good else'strong_motion_evidence_not_satisfied',**metrics)
