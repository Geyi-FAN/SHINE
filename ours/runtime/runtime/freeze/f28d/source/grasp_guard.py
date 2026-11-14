"""Current object motion relative to measured hand motion, using fresh RGB-D only."""
import numpy as np

def fast_rgbd_ready(rows,operation,entered,frame):
    obj=operation['object'];key=obj+'.K1'
    if obj not in ('cheese','wine_bottle'):return False
    visible=[r for r in rows if entered<=r['frame']<=frame and key in r.get('geometry',{}) and r.get('sensor')]
    if len(visible)<3 or visible[-1]['frame']!=frame:return False
    recent=visible[-3:]
    if recent[-1]['frame']-recent[0]['frame']<6 or any(recent[i+1]['frame']-recent[i]['frame']>4 for i in range(2)):return False
    width=recent[-1]['sensor']['width']
    if not .002<=width<.060:return False
    origin=np.asarray(visible[0]['geometry'][key]);current=np.asarray(recent[-1]['geometry'][key])
    if current[2]-origin[2]<.020:return False
    offsets=[np.asarray(r['geometry'][key])-np.asarray(r['sensor']['eef_xyz']) for r in recent]
    if np.linalg.norm(offsets[-1])>.080:return False
    if max(np.linalg.norm(a-b) for a in offsets for b in offsets)>.010:return False
    a=np.asarray(recent[-1]['geometry'][key])-np.asarray(recent[0]['geometry'][key])
    b=np.asarray(recent[-1]['sensor']['eef_xyz'])-np.asarray(recent[0]['sensor']['eef_xyz'])
    return bool(np.linalg.norm(a)>=.008 and np.linalg.norm(b)>=.008 and np.linalg.norm(a-b)<=.010)

def grasp_motion(rows,operation,entered,frame):
    obj=operation['object'];key=obj+'.K1'
    if obj not in ('cheese','wine_bottle'):
        return dict(passed=True,applicable=False,reason='retain original RGB/proprioception grasp detector; bowl point depth can intersect cavity or occluder',note='No new depth reliability claim for bowls')
    visible=[r for r in rows if entered<=r['frame']<=frame and key in r.get('geometry',{}) and r.get('sensor')]
    if not visible or visible[-1]['frame']!=frame:return dict(passed=False,reason='current_object_depth_missing')
    origin=visible[0];end=visible[-1]
    lift=float(np.asarray(end['geometry'][key])[2]-np.asarray(origin['geometry'][key])[2])
    near=float(np.linalg.norm(np.asarray(end['geometry'][key])-np.asarray(end['sensor']['eef_xyz'])))
    pairs=[]
    recent=[r for r in visible if frame-r['frame']<=80]
    for before in recent:
        for after in recent:
            if not 4<=after['frame']-before['frame']<=24:continue
            motion=np.asarray(after['geometry'][key])-np.asarray(before['geometry'][key])
            hand=np.asarray(after['sensor']['eef_xyz'])-np.asarray(before['sensor']['eef_xyz'])
            if np.linalg.norm(motion)>=.008 and np.linalg.norm(hand)>=.008 and np.linalg.norm(motion-hand)<=.030:
                pairs.append([before['frame'],after['frame']])
    passed=lift>=.020 and near<=.120 and bool(pairs)
    return dict(passed=bool(passed),reason='measured_target_lift_and_hand_comotion' if passed else 'no_measured_target_lift_or_ownership_motion',
        target_lift_m=lift,current_hand_distance_m=near,agreeing_frame_pairs=pairs[-4:],
        note='YOLO K1 + measured depth + robot proprioception; not a simulator grasp/contact label')
