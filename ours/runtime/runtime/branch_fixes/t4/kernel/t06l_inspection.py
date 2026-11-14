"""Short, scoped initial contact checks; never plans, acts or completes stages.

Preserves both independently newer-frame supported-release observations and
the original release/clearance controllers. Stalled execution and missing-point
recovery keep their original prompt and full temporal image window.
"""
import copy
import json
from pathlib import Path
import inspect
import math
import textwrap

VERSION='scoped-current-pair-inspection-v3'
OBJECTS=('bowl','cheese','wine_bottle','plate')

COMMON='''You are the robot observation and recovery agent, not its task planner.
Use CURRENT MAIN/WRIST RGB, fresh YOLO and measured robot state. No simulator
object pose or reference answer is available. Report what is visible, not what
the user wants. A closed hand does not prove ownership. Width <0.060m is CLOSED,
width >=0.065m is OPEN; an almost closed empty hand <0.002m cannot contain a
bowl, cheese block or bottle. Never override measured width by perspective.
Each current image shows MAIN left and WRIST right. Only current_image_frames_shown
are visually supplied. Cite those frame IDs only. Older sensor_frames are robot,
YOLO and depth measurements, not additional RGB evidence. Historical images, if
provided, are appearance references, never current support or completion proof.
support_visible=true requires an actual visible supporting surface, not an
object suspended above it. If occluded or uncertain use null/unknown. Distinguish
bowl, plate and cheese from both views; do not echo a detector as independent
evidence. Do not declare stages completed or invent a next operation/coordinate.
Return JSON with held_object: bowl|cheese|wine_bottle|plate|none|unknown;
support_visible: {bowl:true|false|null,cheese:...,wine_bottle:...,plate:...};
evidence_frames:[actually shown current image IDs]; rationale:one short evidence sentence of at most18 words; recovery_request:an allowed tool below;
release_object:bowl|cheese|wine_bottle|plate|null.
This scoped response has no relations or bowl_location fields: do not make
unrequested scene-location claims. Keep ownership/support unknown when unclear.
Never infer future phases or support from missing pixels.
'''

TAKEOVER='''Scope: INITIAL CONTACT/OWNERSHIP CHECK, before any selected subgoal.
Allowed requests: release_supported_in_place, observe_only, none.
If measured CLOSED fingers visibly touch/grip a supported NON-target object and
the user's requested operation requires a different object, request
release_supported_in_place with that visible supported release_object. This
only requests opening fingers at the CURRENT pose, not moving the object.
Supported-rim ambiguity rule: when measured CLOSED fingers are close to or
around the rim of a CURRENTLY VISIBLE supported NON-target object, do not
require proof that it is actually grasped. Contact versus gripping may remain
unknown. If another object must be handled, request release_supported_in_place
with that supported object to free possible rim contact; this does NOT assert
ownership or task completion. In particular, an unknown holding label by itself
does not prohibit this guarded supported in-place opening. Never apply this
rule when support is hidden, airborne, or the object is the requested payload.
Never release an airborne object, an unidentified object, or the object the
user needs transported. If current support/contact is unclear, observe_only.
If hand is confidently empty/open and no obstructing contact is seen, none.
The controller still requires two accepted NEW-FRAME support confirmations and
all original robot guards before any release; your output is not execution.
Do not request clear_supported_object yet: release has NOT been executed.
'''

CLEARANCE='''Scope: AFTER AN ACTUALLY EXECUTED SUPPORTED IN-PLACE RELEASE.
The supplied context identifies the released object and measured open hand.
Allowed requests: clear_supported_object, observe_only, none.
Only if the hand is still near that visibly supported object, fingers are
measured OPEN, hand is empty, and CURRENT MAIN/WRIST show free overhead space,
request clear_supported_object. It means the original bounded6cm upward,
open-finger withdrawal before reaching for the next object. Never under an
overhead obstacle/drawer roof, with a held object, or with uncertain clearance.
If uncertain request observe_only; if already clear request none. The script
still rechecks its original measured open-hand, near-object and release guards.
Do not request a second release, grasp, placement or task change.
'''

def scope(rows,diagnostics):
    if not rows:return None
    sensor=rows[-1].get('sensor')or{}
    width=sensor.get('width')
    if not isinstance(width,(float,int))or not math.isfinite(width):return None
    diagnostics=diagnostics or{}
    context=diagnostics.get('observation_request_context')or{}
    if diagnostics.get('operation') or context.get('selected_stage'):return None
    reason=context.get('reason')
    if (reason=='supported_in_place_release_executed_but_hand_may_still_intersect_old_object'
        and context.get('released_object')in OBJECTS and context.get('gripper_open')is True
        and width>=.065):return 'post_release_clearance'
    if not context and diagnostics.get('status')!='completed':return 'initial_contact'
    return None

def prepare(payload,selected,diagnostics,folder=None,index=None):
    kind=scope(selected,diagnostics)
    shown=selected[-1:] if kind else selected
    if kind:
        if folder is not None:
            (Path(folder)/f'{index}_input_full_sensors.json').write_text(json.dumps(payload,indent=2))
        # Keep exact values and EVERY temporal sensor frame. K2/K3/facility
        # goals are not needed for this ownership/contact-only check.
        focused=[]
        for row in payload.get('sensor_frames',[]):
            item=copy.deepcopy(row)
            item['fresh_yolo_points']=[p for p in item.get('fresh_yolo_points',[])if p.get('entity')in OBJECTS and p.get('keypoint')=='K1']
            item['depth_xyz_m']={k:v for k,v in item.get('depth_xyz_m',{}).items()if k in {o+'.K1'for o in OBJECTS}}
            focused.append(item)
        payload['sensor_frames']=focused
        payload['point_scope']='All original temporal sensor frames, exact robot/K1 values; K2/K3 and fixture destinations omitted for ownership-only inspection; full sensors saved separately.'
        payload.update(scoped_inspection=kind,current_image_frames_shown=[r['frame']for r in shown],
            sensor_history_is_not_rgb_history=True)
    return kind,shown

def system(original,kind):
    return original if kind is None else COMMON+(TAKEOVER if kind=='initial_contact'else CLEARANCE)

def extra_errors(pred,payload):
    kind=payload.get('scoped_inspection')
    if not kind:return []
    allowed={'release_supported_in_place','observe_only','none'}if kind=='initial_contact'else{'clear_supported_object','observe_only','none'}
    errors=[]
    if pred.get('recovery_request')not in allowed:errors.append('Only tools allowed by the CURRENT scoped inspection may be requested; do not invent a prior release or selected subgoal.')
    frames=pred.get('evidence_frames')or[]
    if not frames or not set(frames)<=set(payload['current_image_frames_shown']):errors.append('Cite only actually supplied CURRENT RGB frame IDs; older sensor history is not RGB evidence.')
    return errors

def contract(body,role,original):
    output=original(body,role)
    if role!='recovery':return output
    payload=None
    for message in body.get('messages',[]):
        content=message.get('content')
        if message.get('role')!='user' or not isinstance(content,list)or not content:continue
        if content[0].get('type')!='text':continue
        try:data=json.loads(content[0]['text'])
        except (ValueError,TypeError):continue
        if data.get('scoped_inspection')in ('initial_contact','post_release_clearance'):payload=data
    if payload is None:return output
    schema=output['response_format']['json_schema']['schema']
    # Auxiliary scene relation/location claims are unnecessary in these two
    # scoped checks. Preserve every fact the unchanged tool guards consume.
    for field in ['relations','bowl_location']:
        schema['properties'].pop(field,None)
        schema['required']=[x for x in schema['required']if x!=field]
    schema['properties']['rationale']['maxLength']=120
    schema['properties']['evidence_frames']['items']['enum']=list(payload['current_image_frames_shown'])
    schema['properties']['recovery_request']['enum']=(['release_supported_in_place','observe_only','none']
        if payload['scoped_inspection']=='initial_contact'else['clear_supported_object','observe_only','none'])
    output['messages'][0]['content']+='\nSCOPED OUTPUT: Use at most18 words for rationale. Return only the six scoped fields; no relations or bowl_location. Do not describe alternative tools. Unknown ownership remains allowed; it does not prohibit a supported-contact release request.'
    return output

def install_schema(module=None):
    if module is None:import output_contract as module
    original=module.constrain
    if getattr(original,'_t06l_scoped_contract',False):return
    def constrain(body,role):return contract(body,role,original)
    constrain._t06l_scoped_contract=True
    constrain._t06l_original=original
    module.constrain=constrain

def install(cls=None):
    if cls is None:
        from recovery_observer import RecoveryObserver as cls
    old=cls.check
    if getattr(old,'_t06l_scoped_inspection',False):return
    source=textwrap.dedent(inspect.getsource(old))
    replacements={
        "context=payload.get('observation_request_context') or {}":"inspection_scope,visual_rows=_t06l_prepare(payload,selected,diagnostics,self.folder,i)\n    context=payload.get('observation_request_context') or {}",
        'for r in selected:\n':'for r in visual_rows:\n',
        'system=SYSTEM':'system=_t06l_system(SYSTEM,inspection_scope)',
        'available={r[\'frame\'] for r in selected}':'available={r[\'frame\'] for r in visual_rows}',
        'validation=tool_errors(pred,payload)':'validation=tool_errors(pred,payload)+_t06l_errors(pred,payload)',
    }
    # Keep the existing inspector validation, frame corroboration and model loop.
    # Fail closed if the source shape changes rather than leaving a patch unused.
    for before,after in replacements.items():
        if source.count(before)!=1:raise ValueError('Unexpected actual observer source: '+before)
        source=source.replace(before,after)
    # Source transformation copies globals. The single-owner bridge installs
    # its I/O wrapper later; a copied request_json would silently bypass it,
    # holding the simulator lock and leaving the next policy image stale.
    # Resolve the original module's current transport at CALL time instead.
    transport_globals=old.__globals__
    def current_transport(*args,**kwargs):
        return transport_globals['request_json'](*args,**kwargs)
    namespace=dict(old.__globals__,request_json=current_transport,
        _t06l_prepare=prepare,_t06l_system=system,_t06l_errors=extra_errors)
    exec(compile(source,__file__,'exec'),namespace)
    check=namespace['check'];check._t06l_scoped_inspection=True
    cls.check=check
    install_schema()

def identity():
    from recovery_observer import RecoveryObserver
    return dict(version=VERSION,actual_observer_guarded=bool(getattr(RecoveryObserver.check,'_t06l_scoped_inspection',False)),
        actual_output_contract_guarded=bool(getattr(__import__('output_contract').constrain,'_t06l_scoped_contract',False)),
        image_change='latest CURRENT paired MAIN/WRIST only in initial ownership and measured post-release clearance',
        original_temporal_sensor_frames_and_exact_robot_K1_preserved=True,full_sensor_input_saved=True,original_release_corroboration_preserved=True,
        original_controllers_preserved=True,stalled_execution_recovery_unchanged=True,
        planner_or_subgoal_changed=False,independent_score_changed=False)
