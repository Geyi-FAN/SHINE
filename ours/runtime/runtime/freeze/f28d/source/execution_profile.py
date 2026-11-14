"""Model-specific wording only; Agent remains responsible for stage selection."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SMOL_PROFILE = 'smolvla_e3_v4'


def is_smol():
    return os.environ.get('HYBRID_EXECUTOR', 'pi05_v3r') in (SMOL_PROFILE, 'pi05_e3_v4')


def load_catalog():
    old = json.loads((ROOT / 'operators.json').read_text())
    if not is_smol():
        return old
    trained = json.loads((ROOT / 'smolvla_e3_skills.json').read_text())
    mapping = ['grasp_bowl', 'bowl_stove', 'grasp_wine_bottle', 'bottle_cabinet',
               'open_top', 'bowl_drawer', 'bowl_cabinet', 'push_plate',
               'grasp_cheese', 'cheese_bowl', 'turn_on_stove', 'bowl_plate',
               'bottle_rack', 'close_middle', 'open_middle', 'return_bowl',
               'return_wine_bottle', 'close_top', 'return_cheese',
               'return_bowl_clear', 'return_wine_bottle_clear', 'return_cheese_clear']
    result = {}
    import re
    for name, skill in zip(mapping, trained['skills'], strict=True):
        op = dict(old[name])
        reference = op['reference']
        if reference:
            symbolic = '.'.join(reference[k] for k in ('time_source', 'entity', 'keypoint'))
            op['template'] = re.sub(r'\{\w+\}', '{' + symbolic + '}', skill['instruction_grounded_original'])
        else:
            op['template'] = skill['instruction_grounded_original']
            assert '{' not in op['template']
        op['template_id'] = skill['template_id']
        result[name] = op
    return result


def policy_template(task, operator):
    if is_smol():
        return ('Task: ' + task + '.\nCurrent subgoal: ' + operator['template'] +
                '.\nCoordinates: MAIN, 224x224, <y,x> pixels.\n')
    return (task + '; Coordinates: MAIN, 224x224, <y,x> pixels; Current Subgoal: ' +
            operator['template'] + ('; The red arrow points to the referenced location in MAIN'
                                     if operator['kind'] == 'return' else ''))
