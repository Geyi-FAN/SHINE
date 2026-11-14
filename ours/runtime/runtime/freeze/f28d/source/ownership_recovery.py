"""Measured guard for an Agent-requested empty-hand placement interruption.

This never declares a stage completed and never selects a replacement subgoal.
Only fresh RGB-D observations and measured robot state are read.
"""
import numpy as np


def empty_hand_replan_evidence(rows, stage, prediction, frame):
    if stage.get('operation') != 'cheese_bowl':
        return dict(passed=False, reason='not_supported_placement')
    if prediction.get('held_object') != 'none' or prediction.get('relations', {}).get('cheese_bowl') is not False or prediction.get('support_visible', {}).get('cheese') is not True:
        return dict(passed=False, reason='image_evidence_does_not_confirm_supported_object_outside_destination_and_empty_hand')
    recent = [r for r in rows if 0 <= frame-r['frame'] <= 12][-3:]
    if len(recent) != 3 or recent[-1]['frame'] != frame or recent[-1]['frame']-recent[0]['frame'] < 8:
        return dict(passed=False, reason='three_fresh_separated_observations_required')
    positions=[];distances=[]
    for r in recent:
        xyz=r.get('geometry', {}).get('cheese.K1');sensor=r.get('sensor', {})
        if xyz is None or sensor.get('width', 1) >= .002 or sensor.get('eef_xyz') is None:
            return dict(passed=False, reason='fresh_target_depth_and_almost_fully_closed_hand_required')
        xyz=np.asarray(xyz, float);hand=np.asarray(sensor['eef_xyz'], float)
        if not np.isfinite(xyz).all() or not np.isfinite(hand).all():
            return dict(passed=False, reason='invalid_depth')
        positions.append(xyz);distances.append(float(np.linalg.norm(xyz-hand)))
    spread=max(float(np.linalg.norm(a-b)) for a in positions for b in positions)
    passed=min(distances)>=.080 and spread<=.010
    return dict(passed=bool(passed), reason='supported_target_separate_from_empty_closed_hand' if passed else 'target_not_independently_separate_and_stable',
                evidence_frames=[r['frame'] for r in recent],hand_distances_m=distances,target_spread_m=spread,
                creates_completion=False,position_source='fresh YOLO K1 plus measured depth; no simulator object facts')
