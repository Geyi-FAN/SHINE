"""Independent RGB-D contradiction check; no simulator object states."""
import numpy as np

def container_consensus(rows,operation,frame):
    obj,target=('cheese','bowl') if operation=='cheese_bowl' else ('bowl','top_drawer_interior')
    estimates=[]
    for row in rows:
        if not 0<=frame-row['frame']<=12:continue
        a=row.get('geometry',{}).get(obj+'.K2');b=row.get('geometry',{}).get(target+'.K3')
        destination_source='fresh measured RGB-D'
        if b is None:
            entry=row.get('static_destination_geometry',{}).get(target+'.K3')
            if entry is not None:
                b=entry['xyz_m'];destination_source='valid static destination depth memory from frame '+str(entry['source_frame'])
        if a is None or b is None:continue
        delta=np.asarray(a)-np.asarray(b)
        if not np.isfinite(delta).all():continue
        inside=bool(np.linalg.norm(delta[:2])<=.045 and -.020<=delta[2]<=.065)
        estimates.append(dict(frame=row['frame'],delta_xyz_m=delta.tolist(),inside_proxy=inside,destination_source=destination_source,
            object_source='fresh current object RGB-D only; never cached'))
    contradiction=any(not x['inside_proxy'] for x in estimates)
    enough=len(estimates)>=2 and estimates[-1]['frame']-estimates[0]['frame']>=4
    passed=enough and not contradiction
    return dict(passed=bool(passed),estimates=estimates,
        reason='geometry_contradicts_containment' if contradiction else 'measured_container_proximity' if passed else 'insufficient_fresh_geometry',
        thresholds=dict(xy_m=.045,z_lower_m=-.020,z_upper_m=.065),
        note='Existing S1 RGB-D proximity proxy; not exact support or physical containment proof')
