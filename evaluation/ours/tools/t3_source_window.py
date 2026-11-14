"""Private evaluator: same predicates as published T3 client, no Agent inputs."""
NAMES=['open_middle','bowl_stove','bottle_cabinet','bowl_drawer','bowl_cabinet','push_plate','cheese_bowl','turn_on_stove','bowl_plate','bottle_rack']
OBJECTS={1:'bowl',2:'wine_bottle',3:'bowl',4:'bowl',5:'plate',6:'cheese',8:'bowl',9:'wine_bottle'}

def reached(t,spec,task_id,initial_stove):
    if not t or t.get('task_id')!=task_id or t.get('mode')not in('running','verifying')or t.get('policy_actions',0)<1:return False
    p=t['physical'];src=spec['source_task'];phase=spec['phase']
    if p['native_goal_relations'][NAMES[src]]is not False:return False
    obj=OBJECTS.get(src)
    if phase in('M0','P0'):return p['held_object']=='none'and not p['objects'][obj]['robot_contact']
    if phase=='K0':return p['held_object']=='none'and abs(t['measurements']['bowl']['articulation']['stove']-initial_stove)<1e-4
    if phase=='D1':return abs(t['measurements']['bowl']['articulation']['middle'])>spec['rules']['close']['gap_m']and not p['drawers']['middle']['open']
    if phase in('M2','C4'):return p['held_object']==obj and not p['objects'][obj]['supported']and(phase!='C4'or p['drawers']['top']['open'])
    if phase=='C0':return p['held_object']=='none'and not p['objects']['bowl']['robot_contact']and abs(t['measurements']['bowl']['articulation']['top'])<=spec['rules']['close']['gap_m']and t.get('evaluator_extra',{}).get('cabinet_robot_contact')is False
    raise ValueError('unsupported_source_phase:'+phase)
