"""Run exactly existing post-verifier geometry guards before spending an API call."""
import json
import os
from pathlib import Path


def check(stage,entered,frame,rows):
    selected=[r for r in rows if entered<=r['frame']<=frame][-4:]
    op=stage['operation']
    if op in('cheese_bowl','bowl_drawer')and os.environ.get('REPAIR_CONTAINER_GUARD','0')=='1':
        from container_guard import container_consensus
        result=container_consensus(selected,op,frame)
    elif op.startswith('close_')and os.environ.get('REPAIR_DRAWER_GUARD','0')=='1':
        from drawer_guard import closing_evidence
        from drawer_ray import estimate
        level='top'if op.endswith('top')else'middle'
        cal=json.loads(Path(os.environ['P012_DRAWER_CALIBRATION']).read_text());ref=cal['closed_handles'][level]
        rays=[]
        for row in selected:
            point=next((p for p in row.get('image_points',[])if p['entity']==level+'_handle'and p['keypoint']=='K1'),None)
            value=estimate(point,row.get('camera_calibration'),ref)
            if value is not None:rays.append(dict(frame=row['frame'],**value))
        result=closing_evidence(selected,level,frame,ref,rays)
    else:return dict(applicable=False,permit=True,reason='original_admission_unchanged')
    contradiction=result['reason']in('geometry_contradicts_containment','depth_contradicts_closed','geometry_contradicts_closed')
    return dict(applicable=True,permit=not contradiction,reason=result['reason'],evidence=result,
                missing_evidence_keeps_original_visual_recovery_path=not result['passed']and not contradiction,
                source='same existing post-API guard, preflight only; never creates completion')
