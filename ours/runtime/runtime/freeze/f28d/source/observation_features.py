"""Transparent summaries of already supplied measurements; no object truth.

These features do not choose a tool, complete a stage, or replace visual support.
"""
import copy
import json
import math
from pathlib import Path


def norm(a, b):
    if a is None or b is None or len(a) != len(b):
        return None
    if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in list(a) + list(b)):
        return None
    return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))


def finger(width):
    if width is None:
        return dict(width_m=None, category='unknown')
    return dict(width_m=width, category='open' if width >= .065 else 'almost_fully_closed' if width < .002 else 'closed' if width < .060 else 'transition',
                note='Closed describes the fingers, not ownership; support and gripping may coexist.')


def motion(rows, entity, point_field, geometry_field, sensor_field):
    observed = [r for r in rows if r.get(geometry_field, {}).get(entity+'.K1') is not None and r.get(sensor_field, {}).get('eef_xyz') is not None]
    if len(observed) < 2:
        return dict(usable_frames=[r['frame'] for r in observed], motion_available=False)
    first, last = observed[0], observed[-1]
    obj_a, obj_b = first[geometry_field][entity+'.K1'], last[geometry_field][entity+'.K1']
    hand_a, hand_b = first[sensor_field]['eef_xyz'], last[sensor_field]['eef_xyz']
    obj_d = [b-a for a,b in zip(obj_a,obj_b)]
    hand_d = [b-a for a,b in zip(hand_a,hand_b)]
    return dict(usable_frames=[r['frame'] for r in observed], motion_available=True,
                object_delta_xyz_m=obj_d, eef_delta_xyz_m=hand_d,
                relative_displacement_error_m=norm(obj_d,hand_d),
                note='Short-window RGB-D proxy. Both stationary is not proof of an empty hand; cavity/occluder depth may be unreliable.')


def recovery_features(payload):
    ctx = payload.get('observation_request_context') or {}
    stage = ctx.get('selected_stage') or {}
    width = payload.get('measured_gripper_width_m')
    near = (payload.get('fallible_holding_estimate') or {}).get('near_px', {})
    rows = payload.get('sensor_frames', [])
    return dict(schema='observed_prerequisite_features_v1', fingers=finger(width),
                selected_operation=stage.get('operation'), selected_kind=stage.get('kind'),
                context_reason=ctx.get('reason'),
                near_hand_candidates=[dict(entity=k, distance_MAIN224_px=v) for k,v in near.items() if v is not None and v <= 26],
                open_empty_gripper_measured_width_prerequisite=(width < .002) if width is not None else None,
                clear_supported_object_context_prerequisite=ctx.get('reason') in ('supported_in_place_release_executed_but_hand_may_still_intersect_old_object','accepted_return_before_different_object_grasp'),
                replan_has_selected_placement=bool(stage and stage.get('kind') == 'target'),
                object_hand_motion={e: motion(rows,e,'fresh_yolo_points','depth_xyz_m','sensor') for e in ('bowl','cheese','wine_bottle','plate')},
                limits='These are necessary conditions or numerical summaries, not tool permission or physical truth. Inspect images for identity, support and clearance. No motion in a stationary hand does not imply empty. No initial scene truth is supplied.')


def verifier_features(payload):
    rows = payload.get('recent_frames', [])
    stage = payload.get('selected_subgoal') or {}
    obj = stage.get('object')
    ref = stage.get('reference')
    recent = rows[-1] if rows else {}
    width = (recent.get('robot_proprioception') or {}).get('width')
    target = None
    target_source = None
    if ref and ref.get('time_source') in ('episode_start','instruction_takeover'):
        for p in payload.get('historical_target_references', []):
            if all(p.get(k) == ref.get(k) for k in ('time_source','entity','keypoint')):
                target = p.get('MAIN224_yx_px'); target_source = ref['time_source']
    elif ref:
        p = next((p for p in recent.get('fresh_MAIN224_yx_points', []) if p.get('entity') == ref['entity'] and p.get('keypoint') == ref['keypoint']), None)
        if p:
            target = p['yx_px'];target_source = 'current fresh YOLO'
    positions = []
    for row in rows:
        p = next((p for p in row.get('fresh_MAIN224_yx_points', []) if p.get('entity') == obj and p.get('keypoint') == 'K2'), None)
        if p:
            positions.append(dict(frame=row['frame'], MAIN224_yx_px=p['yx_px']))
    current = positions[-1]['MAIN224_yx_px'] if positions and rows and positions[-1]['frame'] == rows[-1]['frame'] else None
    error = norm(current, target)
    span = positions[-1]['frame'] - positions[0]['frame'] if positions else None
    # The existing S1 constants are explicitly named; neither is a full success condition.
    proximity_applicable = stage.get('kind') in ('return','release') or stage.get('operation') in ('cheese_bowl','bowl_drawer','bowl_stove','bowl_plate','bowl_cabinet','bottle_cabinet','bottle_rack','push_plate')
    radius = (6. if stage.get('kind') in ('return','release') else 14.) if proximity_applicable else None
    start = payload.get('stage_start')
    motion_rows = ([start] if start and (not rows or start['frame'] != rows[0]['frame']) else []) + rows
    return dict(schema='observed_numeric_features_v1', fingers=finger(width),
                selected_object=obj, reference=ref, target_MAIN224_yx_px=target, target_source=target_source,
                current_object_K2_MAIN224_yx_px=current, reference_distance_MAIN224_px=error,
                original_S1_proximity_radius_px=radius, proximity_summary_applicable=proximity_applicable,
                object_K2_recent_positions=positions, observed_position_span_steps=span,
                recent_open_finger_widths_m=[(r.get('robot_proprioception') or {}).get('width') for r in rows],
                object_hand_motion=motion(motion_rows,obj,'fresh_MAIN224_yx_points','depth_WORLD_xyz_m','robot_proprioception') if obj else None,
                limits='Proximity is not support or containment. These numbers summarize the existing measurements and original S1 settings, not an instruction to pass. MAIN224 coordinates refer to the original camera, not an atlas. Reaching a front region need not mean an exact center or an image-left/right relation to the stove. Preserve independent gates and required_checks.')


def augment(body, role):
    output = copy.deepcopy(body)
    # The code-policy recovery interface has its own documented language.
    for message in body.get('messages',[]):
        content=message.get('content')
        if message.get('role')=='user' and isinstance(content,list) and content and content[0].get('type')=='text':
            try: schema=json.loads(content[0]['text']).get('schema')
            except (ValueError,AttributeError): schema=None
            if schema in('recovery_code_policy_v1','recovery_code_policy_v2','recovery_code_policy_v3','recovery_code_policy_v4','recovery_code_policy_v5','recovery_code_policy_v6'):return output
    addendum = Path(__file__).with_name(role+'_addendum.txt')
    if addendum.exists():
        output['messages'][0]['content'] += '\n\nOBSERVATION INTERPRETATION ADDENDUM:\n' + addendum.read_text()
    for message in output['messages']:
        content = message.get('content')
        if message.get('role') != 'user' or not isinstance(content,list) or not content or content[0].get('type') != 'text':
            continue
        try:
            payload = json.loads(content[0]['text'])
        except ValueError:
            continue
        if payload.get('schema') == 'recovery_observation_v1':
            payload['transparent_observation_features'] = recovery_features(payload)
            context=payload.get('observation_request_context') or {}
            if context.get('reason')=='accepted_return_before_different_object_grasp':
                output['messages'][0]['content']+='\nPOST-RETURN OBSERVATION TOOL SCOPE: The previously accepted return/release concerns the object named released_object. The Agent has selected a DIFFERENT object to acquire next, but has not executed that grasp. clear_supported_object is specifically available in this context, even without a separate recovery release command. Request it only if the old object is visibly independently supported, the open hand is empty, and the short WORLD+z6cm path is visibly clear. Otherwise use observe_only/none; do not assume support from the old event. Two fresh corroborating reports and independent current measurements are checked before any movement. This is optional camera/hand clearance, not a new user task or proof of completion.'
            if context.get('reason')=='drawer_has_not_completed_after_bounded_execution':
                output['messages'][0]['content']+='\nCURRENT-CONTEXT TOOL SCOPE: This selected stalled drawer opening or closing is an explicitly authorized cabinet-observation context, even without a close-completion candidate. All original empty-hand, finger-state, path and bounded-retry checks still apply; no goal is declared completed.'
        elif payload.get('schema') == 'causal_visual_verifier_v2':
            payload['transparent_observation_features'] = verifier_features(payload)
        else:
            continue
        content[0]['text'] = json.dumps(payload)
    return output
