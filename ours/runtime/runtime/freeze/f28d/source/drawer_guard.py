"""Prefer measured RGB-D displacement; calibrated 2D ray is a missing-depth fallback."""
import numpy as np
from drawer_ray import closed_consensus

def closing_evidence(rows,level,frame,reference,ray_estimates):
    depth=[];axis=np.asarray(reference['opening_axis'],float);axis/=np.linalg.norm(axis)
    origin=np.asarray(reference['xyz'],float)
    for row in rows:
        if not 0<=frame-row['frame']<=12:continue
        point=row.get('geometry',{}).get(level+'_handle.K1')
        if point is None:continue
        gap=float(np.dot(np.asarray(point)-origin,axis))
        residual=float(np.linalg.norm(np.asarray(point)-origin-gap*axis))
        if np.isfinite(gap) and residual<=.012:depth.append(dict(frame=row['frame'],gap_m=gap,axis_residual_m=residual))
    if depth:
        # Exactly the original S1 4-observation/9-step closed-depth condition.
        enough=len(depth)>=4 and depth[-1]['frame']-depth[0]['frame']>=9
        passed=enough and all(abs(x['gap_m'])<=.010 for x in depth)
        return dict(passed=bool(passed),primary_sensor='fresh RGB-D displacement',depth_estimates=depth,
            auxiliary_ray_estimates=ray_estimates,closed_tolerance_m=.010,
            reason='measured_closed_depth' if passed else 'depth_contradicts_closed' if any(abs(x['gap_m'])>.010 for x in depth) else 'insufficient_sustained_depth',
            priority='Select sensor by depth availability, never by which result passes; a 2D-ray estimate cannot override valid depth.')
    result=closed_consensus(ray_estimates,frame)
    result.update(primary_sensor='calibrated 2D ray fallback; no valid current depth',depth_estimates=[])
    return result
