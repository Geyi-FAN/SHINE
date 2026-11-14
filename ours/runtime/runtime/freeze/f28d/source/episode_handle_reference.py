"""Typed historical handle reference from known-closed RGB-D initialization.

No object/joint truth, score labels or plans are read. Opening axes are unchanged.
"""
import copy
import numpy as np
from depth_sensor import xyz_from_point


def build(points,depth,camera,fixture_calibration):
    result=copy.deepcopy(fixture_calibration);proof={}
    for level,reference in result['closed_handles'].items():
        p=next((x for x in points if x['entity']==level+'_handle'and x['keypoint']=='K1'),None)
        status=dict(source='original_development_global_reference',reason='initial_handle_unavailable')
        if p and p.get('source')=='yolo_image_only'and min(p.get('det_confidence',0),p.get('keypoint_confidence',0))>=.8:
            xyz=xyz_from_point(p['yx224'],depth,camera)
            if xyz is not None:
                delta=np.asarray(xyz)-np.asarray(reference['xyz']);axis=np.asarray(reference['opening_axis']);axis/=np.linalg.norm(axis)
                parallel=float(np.dot(delta,axis));perpendicular=float(np.linalg.norm(delta-parallel*axis))
                if abs(parallel)<=.025 and perpendicular<=.020:
                    original=reference['xyz'];reference['xyz']=xyz
                    status=dict(source='episode_start_image_YOLO_K1_plus_RGBD',known_closed_initialization_prior=True,initial_point=copy.deepcopy(p),original_global_xyz=original,observed_xyz=xyz,parallel_shift_m=parallel,perpendicular_shift_m=perpendicular,oracle_object_pose_used=False)
                else:status['reason']='initial_measurement_outside_calibrated_fixture_envelope'
            else:status['reason']='initial_depth_invalid'
        proof[level]=status
    result['reference_provenance']=proof
    result['source']='Per-episode same-typed historical image/depth origin where high-confidence and valid; original calibrated axis and physical thresholds retained.'
    return result
