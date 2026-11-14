"""Evaluator-only T3 contract and causal phase helpers."""
import math
from t1_contract import GOALS,goal_flag

OBJECT_NAMES={'bowl':'akita_black_bowl_1','wine_bottle':'wine_bottle_1','cheese':'cream_cheese_1','plate':'plate_1'}
SOURCE_OBJECT={1:'bowl',2:'wine_bottle',3:'bowl',4:'bowl',5:'plate',6:'cheese',8:'bowl',9:'wine_bottle'}
def dist(a,b):return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))

def trigger_ready(spec,tick,source_id,source_actions,initial,rules):
    if not tick or tick.get('task_id')!=source_id or tick.get('mode') not in ('running','verifying') or source_actions<1:return False
    src=spec['source_task'];phase=spec['phase'];facts=tick['physical']
    if goal_flag(tick,src) is not False:return False
    obj=SOURCE_OBJECT.get(src)
    if phase in ('M0','P0'):
        return facts['held_object']=='none' and not facts['objects'][obj]['robot_contact']
    if phase=='K0':
        q=tick['measurements']['bowl']['articulation']['stove'];q0=initial['measurements']['bowl']['articulation']['stove']
        return facts['held_object']=='none' and abs(q-q0)<1e-4
    if phase=='D1':
        return abs(tick['measurements']['bowl']['articulation']['middle'])>rules['close']['gap_m'] and not facts['drawers']['middle']['open']
    if phase in ('M2','C4'):
        return facts['held_object']==obj and not facts['objects'][obj]['supported'] and (phase!='C4' or facts['drawers']['top']['open'])
    raise ValueError(phase)

def compile_specs(draft, scripts):
    lookup={s['script_id']:s for s in scripts};result=[]
    for case in draft:
        s=lookup[case['script_id']];v=next(v for v in s['variants'] if v['variant']==case['variant'])
        result.append(dict(case,source_task=s['source_task'],target_task=s['target_task'],phase=s['reference']['phase'],
                           family=s['reference']['family'],source_text=s['source_instruction'],task_text=v['task_text'],spoken_text=v['spoken_text'],
                           source_audio_id='T1C_G%02d_P0'%s['source_task'],switch_audio_id=s['script_id']+'_'+case['variant']))
    return result
