"""Shared train / evaluation instruction and privileged-input schema (no policy)."""
import os
import hashlib
import json
import re
from pathlib import Path
import numpy as np

ROOT = Path(os.environ.get("MEMORY_DATA_ROOT", Path(__file__).resolve().parents[1].parent / "pi05_memory_ad_data_20261013"))
WORK = Path(os.environ.get("MEMORY_WORK_ROOT", ROOT.parent))
OBJECTS = ('akita_black_bowl_1', 'cream_cheese_1', 'wine_bottle_1', 'plate_1')
NAMES = ('bowl', 'cream cheese', 'wine bottle', 'plate')
ARTICULATIONS = ('middle', 'top', 'stove')
TASKS = ('open the middle drawer of the cabinet', 'put the bowl on the stove',
         'put the wine bottle on top of the cabinet', 'open the top drawer and put the bowl inside',
         'put the bowl on top of the cabinet', 'push the plate to the front of the stove',
         'put the cream cheese in the bowl', 'turn on the stove', 'put the bowl on the plate',
         'put the wine bottle on the rack')
SOURCE_OBJECT = {1: OBJECTS[0], 2: OBJECTS[2], 3: OBJECTS[0], 4: OBJECTS[0],
                 5: OBJECTS[3], 6: OBJECTS[1], 8: OBJECTS[0], 9: OBJECTS[2]}

def read(p): return json.loads(Path(p).read_text())
def write(p, x):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(8*1024*1024), b''): h.update(b)
    return h.hexdigest()
def textsha(s): return hashlib.sha256(s.encode()).hexdigest()
def name(obj): return NAMES[OBJECTS.index(obj)]

def explicit(row, meta, new=False):
    """Use verified obligations, never infer a new return from a bare target task."""
    original = row.get('instruction', row.get('current_instruction'))
    source = row.get('source_task_id', row.get('source_task'))
    target = row.get('target_task_id', row.get('target_task'))
    contract = meta.get('contract', row.get('contract', {}))
    audit = meta.get('completion_audit', {})
    events = {e['predicate']: e for e in audit.get('event_evidence', []) if e.get('passed')}
    invs = {e['predicate']: e for e in audit.get('invariant_evidence', []) if e.get('passed')}
    srcobj = contract.get('source_object') or meta.get('intent_axes', {}).get('source_object') or SOURCE_OBJECT.get(source)
    reasons = []
    restore_obj = None
    if new:
        return original, row['object_name'], ['new_explicit_instruction_preserved']
    # CONTINUE has historical contract fields which do not impose a new restoration.
    if row.get('branch') == 'CONTINUE': return original, None, ['continue_instruction_preserved']
    ret = bool(contract.get('restore') or 'source_object_restored_supported_released' in events)
    conditional = events.get('held_object_restored_supported_released', {}).get('evidence', {}).get('required') is True
    if ret or conditional:
        restore_obj = srcobj or OBJECTS[0]
        reasons.append('verified_restore' if ret else 'verified_conditional_held_restore')
    close = contract.get('close')
    if not close and 'required_articulation_closed' in events:
        pred = events['required_articulation_closed']['evidence'].get('predicate', [])
        close = next((j for j in ('middle','top') if any(j in str(v) for v in pred)), None)
    clauses = []
    if restore_obj:
        clauses.append(f'return the {name(restore_obj)} to its position at the beginning of this episode and release it stably')
    elif 'source_object_supported_released' in events:
        clauses.append(f'release the {name(srcobj)} stably at its current supported position')
        reasons.append('verified_release_in_place_not_restore')
    if close:
        clauses.append(f'close the {close} drawer'); reasons.append('verified_close')
    if clauses:
        instruction = 'First ' + ', then '.join(clauses + [TASKS[target]]) + '.'
    else:
        instruction = original
    if contract.get('closed_with_bowl') or 'payload_relation_preserved' in invs:
        instruction = 'Leave the bowl inside the top drawer. ' + instruction
        reasons.append('verified_payload_preserved')
    elif 'source_object_unchanged' in invs or (not audit and contract.get('preserve_object')):
        if srcobj:
            instruction += f' Keep the {name(srcobj)} at its current position.'
            reasons.append('verified_object_preserved')
    if 'source_articulation_unchanged' in invs or (not audit and contract.get('preserve_joints')):
        joints = contract.get('preserve_joints', {})
        if not joints:
            for inv in meta.get('acceptance_v2', {}).get('invariants', []):
                if inv['predicate'] == 'source_articulation_unchanged': joints = {inv['joint']: None}
        for joint in sorted(joints):
            label = f'{joint} drawer' if joint in ('middle','top') else 'stove switch'
            instruction += f' Keep the {label} in its current state.'
            reasons.append('verified_articulation_preserved_'+joint)
    return instruction, restore_obj, reasons or ['unchanged_no_extra_obligation']

def relevant(instruction):
    s = instruction.lower()
    objects = [o for o,n in zip(OBJECTS,NAMES) if re.search(r'\b'+n+r'\b',s)]
    joints = [j for j in ARTICULATIONS if (j+' drawer' in s if j!='stove' else 'stove' in s and ('turn on' in s or 'switch' in s))]
    return objects, joints

def gt_text(instruction, restore_obj, initial, current, articulation, available=True):
    """Only measured positions/state; no completion flags, next-stage labels or future GT."""
    if not available: return instruction + ' GT: unavailable.'
    objects, joints = relevant(instruction)
    parts = [instruction, 'GT world meters.']
    def vec(x):
        assert len(x)==3 and np.isfinite(x).all()
        return '('+','.join(f'{float(v)+0.:.3f}' if abs(v)>=.0005 else '0.000' for v in x)+')'
    if restore_obj:
        parts.append(f'Initial {name(restore_obj)} body xyz={vec(initial[restore_obj])}.')
    else: parts.append('Initial return target: none.')
    for obj in objects: parts.append(f'Current {name(obj)} body xyz={vec(current[obj])}.')
    for joint in joints:
        unit='rad' if joint=='stove' else 'm'
        parts.append(f'Current {joint} joint={float(articulation[joint]):.3f} {unit}.')
    return ' '.join(parts)

def gt_from_measurement(instruction, restore_obj, initial, measurement):
    return gt_text(instruction, restore_obj, initial,
                   {k:v['position'] for k,v in measurement['all_object_poses'].items()},
                   measurement['articulation'])
