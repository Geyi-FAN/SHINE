"""Pure, causal task compiler and oracle. No simulator writes or future labels.

RoboMME supplies grounded_subgoal_online to its OracleSubgoalPredictor; here the
same interface is provided by an explicit physical-contract state machine.
"""
import copy
import re
import numpy as np

OBJECTS = ('akita_black_bowl_1', 'cream_cheese_1', 'wine_bottle_1', 'plate_1')
NAMES = dict(zip(OBJECTS, ('bowl', 'cream cheese', 'wine bottle', 'plate')))
ROLES = ('bowl', 'cheese', 'bottle', 'plate', 'middle_handle', 'top_handle',
         'stove_button', 'return_target', 'release_target', 'destination')
OBJ_ROLES = dict(zip(OBJECTS, ROLES[:4]))
TASK_OBJECT = {1:OBJECTS[0], 2:OBJECTS[2], 3:OBJECTS[0], 4:OBJECTS[0],
               5:OBJECTS[3], 6:OBJECTS[1], 8:OBJECTS[0], 9:OBJECTS[2]}
COORDS = 'Coordinates: MAIN, 224x224, <y,x> pixels'


def marker(role):
    return '{' + role + '}'


def target_text(target, points=False, placement_only=False):
    def at(role):return (' at ' + marker(role)) if points else ''
    if target == 0:
        return 'open the middle drawer using its handle' + at('middle_handle') + ' and disengage from the cabinet'
    if target == 7:
        return 'turn on the stove using its switch' + at('stove_button') + ' and disengage from the stove'
    obj = TASK_OBJECT[target];name = NAMES[obj]
    src = '' if placement_only or not points else ' now' + at(OBJ_ROLES[obj])
    destinations = {1:'on the stove',2:'on top of the cabinet',3:'inside the top drawer',
                    4:'on top of the cabinet',5:'to the front of the stove',
                    6:'in the bowl at its current interior point',8:'on the plate',9:'on the rack'}
    destination = destinations[target]
    if points:destination += (' ' if target == 6 else ' at ') + marker('destination')
    verb = 'push' if target == 5 else 'place'
    result = f'{verb} the {name}{src} {destination}'
    if target != 5:result += ' and release it stably'
    if target == 3 and not placement_only:
        result = 'open the top drawer using its handle' + at('top_handle') + ', then ' + result
    return result


def compile_task(row, metadata=None):
    """Use the existing explicit instruction and declared obligations, not actor-end indices."""
    m = metadata or {};ct = copy.deepcopy(m.get('contract', row.get('contract', {})))
    acceptance = copy.deepcopy(m.get('acceptance_v2', {}))
    new = bool(row.get('new', row.get('kind') == 'new_revision'))
    source = int(row.get('source_task_id', row.get('source_task')))
    target = int(row.get('target_task_id', row.get('target_task')))
    instruction = row['instruction'];lower = instruction.lower()
    restore_obj = row.get('restore_object')
    if not restore_obj and ct.get('restore') and 'return' in lower:
        restore_obj = ct.get('source_object')
    events = acceptance.get('events', [])
    invariants = acceptance.get('invariants', [])
    source_obj = ct.get('source_object') or TASK_OBJECT.get(source)
    close = ct.get('close') if 'close' in lower else None
    if not close:
        found = re.search(r'(?:first |then )?close the (middle|top) drawer', lower)
        if found:close = found.group(1)
    release = not restore_obj and ('current supported position' in lower or any(
        c['predicate'] == 'source_object_supported_released' for c in events))
    done = 'that is done' in lower or 'without repeating' in lower or any(
        c['predicate'] == 'no_repeat_operation' for c in invariants)
    if new:
        ct.update(restore=True, source_object=restore_obj, close=None)
    stages=[];clauses_plain=[];clauses_grounded=[]
    def add(kind, text, grounded=None, frames=5, **extra):
        stages.append(dict(kind=kind, text=text, grounded=grounded or text,
                           stable_frames=frames, **extra))
    if restore_obj:
        suffix = ', release it stably' + (' and move the gripper clear' if new else '')
        plain = 'return the '+NAMES[restore_obj]+' to its episode-start position'+suffix
        grounded = 'return the '+NAMES[restore_obj]+' to its episode-start position at {return_target}'+suffix
        add('return',plain,grounded,object=restore_obj,clearance=new)
        clauses_plain.append(plain);clauses_grounded.append(grounded)
    elif release:
        if not source_obj:raise ValueError('Release obligation without an object')
        plain='release the '+NAMES[source_obj]+' stably at its current supported position'
        grounded=plain+' at {release_target}'
        add('release',plain,grounded,object=source_obj)
        clauses_plain.append(plain);clauses_grounded.append(grounded)
    if close:
        plain='turn off the stove' if close=='stove' else 'close the '+close+' drawer'
        role='stove_button' if close=='stove' else close+'_handle'
        grounded=plain+' using its '+('switch' if close=='stove' else 'handle')+' at '+marker(role)
        add('close',plain,grounded,frames=1,joint=close)
        clauses_plain.append(plain);clauses_grounded.append(grounded)
    if done:
        add('maintain','maintain the completed task without repeating the operation',frames=1)
        clauses_plain.append(instruction.rstrip('.'));clauses_grounded.append(instruction.rstrip('.'))
    else:
        if target==3:
            add('open_top','open the top drawer','open the top drawer using its handle at {top_handle}',frames=1)
        if target in TASK_OBJECT and target != 5:
            obj=TASK_OBJECT[target]
            plain='grasp and lift the '+NAMES[obj]+' clear of its support'
            grounded='grasp and lift the '+NAMES[obj]+' now at '+marker(OBJ_ROLES[obj])+' clear of its support'
            add('grasp',plain,grounded,object=obj)
        add('target',target_text(target,False,True),target_text(target,True,True))
        clauses_plain.append(target_text(target,False));clauses_grounded.append(target_text(target,True))
    preserved=[]
    # Only explicit or declared obligations, not stale source-side CONTINUE fields.
    for inv in invariants:
        pred=inv['predicate']
        if pred=='source_object_unchanged':
            preserved.append('keep the '+NAMES[inv['object']]+' where it was when this instruction began')
        elif pred=='restored_source_pose_preserved':
            preserved.append('keep the '+NAMES[inv['object']]+' at its returned position afterward')
        elif pred=='source_articulation_unchanged':
            preserved.append('keep the '+inv['joint']+(' drawer' if inv['joint']!='stove' else ' switch')+' in its initial switch-time state')
        elif pred=='required_closed_state_preserved' and close:
            preserved.append('keep the '+close+' drawer closed afterward' if close!='stove' else 'keep the stove off afterward')
        elif pred=='payload_relation_preserved':
            relation=inv['relation']
            if relation==['in','akita_black_bowl_1','wooden_cabinet_1_top_region']:
                preserved.append('leave the bowl inside the top drawer')
            elif relation==['on','cream_cheese_1','akita_black_bowl_1']:
                preserved.append('keep the cream cheese in the bowl throughout')
            else:raise ValueError(('Unsupported payload language',relation))
    # Mini cases may only expose the existing explicit instruction and contract.
    if not invariants:
        for match in re.finditer(r'(?:Keep|Leave)\s+[^.]+',instruction):
            clause=match.group(0)
            if 'result as it is' not in clause.lower():preserved.append(clause[0].lower()+clause[1:])
        if close:preserved.append('keep the '+close+' drawer closed afterward' if close!='stove' else 'keep the stove off afterward')
    if new:preserved.append('keep the '+NAMES[restore_obj]+' at its returned position afterward')
    preserved=list(dict.fromkeys(preserved))
    def join(parts):
        text=', then '.join(parts)
        if preserved:text+='; '+'; '.join(preserved)
        return text[0].upper()+text[1:]
    task_plain=join(clauses_plain);task_grounded=join(clauses_grounded)
    roles=sorted(set(re.findall(r'\{(\w+)\}',task_grounded)),key=ROLES.index)
    return dict(schema='symbolic_task.v3',source=source,target=target,new=new,
                source_object=source_obj,restore_object=restore_obj,close=close,
                stages=stages,task=task_plain,grounded_task=task_grounded,point_roles=roles,
                contract=ct,acceptance=acceptance,original_instruction=instruction,
                initial_xyz=copy.deepcopy(row.get('initial_xyz',{})))


def fill(template, points, valid):
    def replace(match):
        i=ROLES.index(match.group(1));p=np.asarray(points[i])
        if not valid[i] or not np.isfinite(p).all() or not ((p>=0).all() and (p<=223).all()):return 'unavailable'
        y,x=np.rint(p).astype(int);return f'<{y},{x}>'
    return re.sub(r'\{(\w+)\}',replace,template)


def prompt(plan, arm, stage, points, valid):
    if arm=='E1':return fill(plan['grounded_task'],points,valid)+'; '+COORDS
    if arm not in ('E3','V3R'):raise ValueError(arm)
    subgoal=plan['stages'][stage]['grounded']
    raw=plan['task']+'; '+COORDS+'; Current Subgoal: '+fill(subgoal,points,valid)
    if arm=='V3R':
        from v3_markers import marker_info,LEGEND,UNAVAILABLE
        info=marker_info(plan,stage,points,valid)
        if info['valid']:raw+=LEGEND
    return raw


class Oracle:
    """Input: current physical boolean guards only; output: active stage index.

    The takeover observation initializes state, without counting as a completed
    action. Later observe() calls correspond exactly to action results. Offline
    uses obs[t] with the same chronology, never next_metrics[t].
    """
    def __init__(self,plan):
        self.plan=plan;self.index=0;self.streak=0;self.r25=0;self.clear=0
        self.return_seen=False;self.clear_seen=False;self.events=[];self.initialized=False;self.entry_pending=True

    def observe(self,guards,step):
        first=not self.initialized;self.initialized=True
        # A grasp/opening already physically established at entry needs no repeat.
        while self.index < len(self.plan['stages'])-1:
            stage=self.plan['stages'][self.index];kind=stage['kind']
            # A target relation already established needs release/stabilization,
            # not a fresh grasp (e.g. a bottle already resting on its rack).
            skip=(kind=='grasp' and guards[-3]) or (kind in ('grasp','open_top') and self.entry_pending and guards[self.index])
            self.entry_pending=False
            if first and not skip:return self.index
            if kind=='return' and stage.get('clearance'):
                self.r25=self.r25+1 if guards[-2] else 0
                self.clear=self.clear+1 if guards[-1] else 0
                self.return_seen |= self.r25>=5;self.clear_seen |= self.clear>=5
                complete=self.return_seen and self.clear_seen
            else:
                self.streak=self.streak+1 if guards[self.index] else 0
                complete=self.streak>=stage['stable_frames']
            if skip or complete:
                self.events.append(dict(step=int(step),stage=self.index,kind=kind,already_satisfied=bool(skip)))
                self.index+=1;self.streak=0;self.entry_pending=True
                # Inspect skip conditions on entry; do not count this observation
                # repeatedly toward another stage's stable-frame requirement.
                first=True
            else:break
        return self.index
