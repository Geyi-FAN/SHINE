"""Fresh observed clearance corroborates a visual empty-hand assessment.

This never emits a grasp/placement completion, opens fingers, or reads truth.
"""
import math

OBJECTS=('bowl','cheese','wine_bottle','plate')


def norm(a,b):return math.sqrt(sum((float(x)-float(y))**2 for x,y in zip(a,b)))


def measured_clearance(rows, frame, confidence=.35):
    recent=[r for r in rows if frame-8<=r['frame']<=frame][-3:]
    if len(recent)!=3 or recent[-1]['frame']!=frame or recent[-1]['frame']-recent[0]['frame']<8:
        return None
    if any(b['frame']-a['frame']>4 for a,b in zip(recent,recent[1:])):return None
    distances={};pixels={}
    for row in recent:
        sensor=row.get('sensor')or{};hand=sensor.get('eef_xyz');hand_yx=sensor.get('eef_yx')
        if hand is None or hand_yx is None:return None
        points={}
        for point in row.get('image_points',[]):
            if point.get('source')!='yolo_image_only' or point.get('frame')!=row['frame']:continue
            if min(point.get('det_confidence',0),point.get('keypoint_confidence',0))<confidence:continue
            if point.get('keypoint')=='K1':points[point['entity']]=point
        for obj in OBJECTS:
            point=points.get(obj);xyz=(row.get('geometry')or{}).get(obj+'.K1')
            if point is None or xyz is None:return None
            yx=point.get('yx224')
            if yx is None or not all(math.isfinite(v)for v in list(xyz)+list(yx)):return None
            distance=norm(hand,xyz);pixel=norm(hand_yx,yx)
            if distance<.12 or pixel<40:return None
            distances[obj]=min(distances.get(obj,float('inf')),distance)
            pixels[obj]=min(pixels.get(obj,float('inf')),pixel)
    if max(norm(a['sensor']['eef_xyz'],b['sensor']['eef_xyz'])for a in recent for b in recent)>.015:return None
    return dict(frame=frame,measurement_frames=[r['frame']for r in recent],
        minimum_object_hand_distance_m=distances,minimum_object_hand_distance_px=pixels,
        source='fresh image-only YOLO K1, measured RGB-D and robot proprioception',
        planning_ownership_only=True,creates_completion=False)


def certify(rows, frame, current, previous):
    if previous is None or frame-previous.get('frame',frame)<8:return None
    if current.get('held_object')!='none' or previous.get('held_object')!='none':return None
    if any(current.get('support_visible',{}).get(obj)is not True or
           previous.get('support_visible',{}).get(obj)is not True for obj in OBJECTS):return None
    proof=measured_clearance(rows,frame)
    if proof:proof['visual_evidence_frames']=[previous['frame'],frame]
    return proof
