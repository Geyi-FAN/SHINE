"""Reject redundant CURRENT return preparation from supplied observed facts.

Does not read simulator/evaluator data, generate a next step, alter a plan, or
use case IDs. The Agent still produces every plan and training-format subgoal.
"""
import re

ADDENDUM = '''
OBSERVED GOAL SATISFACTION: physical_state.objects[object].returned_and_released
is a current observed GOAL predicate, not merely a previous action label. When
it is true with fresh supported/released evidence and no contrary ownership,
the requested return is already satisfied. Do not start an unnecessary grasp
followed by returning that SAME object just to re-enact it. Generate your own
remaining plan using the original user order and evidence. Later requested
transport of the same object can still legitimately need grasping; an explicit
pick-up/repeat request is different. False/null/stale evidence never establishes
completion. Do not infer this fact from the instruction, a historical target
point, or a cached coordinate. This rule supplies no next stage or coordinate.
Reference availability gates the action you actually need NOW, not an already
satisfied operation you are omitting. Missing episode_start K2 cannot block
continuation solely to re-confirm a fresh returned_and_released=true goal.
Inspect all remaining user requirements; generate your own next operation and
validate ITS current prerequisites and reference. Do not declare overall hold
unless every requested goal is supported as currently satisfied.
'''


def errors(inp, output):
    if not isinstance(output, dict):
        return []
    plan = output.get('remaining_plan') or []
    facts = inp.get('physical_state', {})
    if facts.get('observed_step') != inp.get('frame'):
        return []
    names = {'bowl': r'bowl', 'wine_bottle': r'(?:wine\s+)?bottle',
             'cheese': r'(?:cream\s+)?cheese', 'plate': r'plate'}
    if output.get('status') == 'need_observation':
        request = str(output.get('request') or '')
        for obj,name in names.items():
            evidence=facts.get('objects',{}).get(obj,{})
            satisfied=(evidence.get('returned_and_released') is True
                       and evidence.get('supported') is True
                       and facts.get('held_object') not in (obj,'unknown',None)
                       and re.search(r'\breturn\s+(?:the\s+)?'+name+r'\b',inp['user_message'],re.I))
            recheck=(re.search(name,request,re.I) and
                     ('episode_start' in request or
                      re.search(r'confirm.*(?:already|original|initial|returned)',request,re.I)))
            if satisfied and recheck:
                return ['SATISFIED_RETURN_REFERENCE_IS_NOT_A_PREREQUISITE: '+obj+
                        ' is freshly observed returned_and_released=true and supported=true. '
                        'A missing episode-start point for RE-EXECUTING that satisfied return '
                        'does not block a different remaining user goal. Do not ask to reconfirm '
                        'this same satisfied goal solely for coordinate availability. Generate '
                        'your own remaining plan and check the references for the action you '
                        'actually select. Different genuine missing prerequisites remain unknown.']
        return []
    if output.get('status') != 'plan_ready' or not plan:
        return []
    first = plan[0]
    obj = first.get('object')
    if obj not in names:
        return []
    words = inp['user_message']
    name = names[obj]
    if not re.search(r'\breturn\s+(?:the\s+)?' + name + r'\b', words, re.I):
        return []
    if re.search(r'\b(?:grasp|lift|pick\s+up)\s+(?:the\s+)?' + name + r'\b', words, re.I):
        return []
    evidence = facts.get('objects', {}).get(obj, {})
    if (evidence.get('returned_and_released') is not True or evidence.get('supported') is not True
            or facts.get('held_object') in (obj, 'unknown', None)):
        return []
    redundant = first.get('kind') == 'return'
    if first.get('kind') == 'grasp' and len(plan) > 1:
        redundant |= plan[1].get('kind') == 'return' and plan[1].get('object') == obj
    if not redundant:
        return []
    return ['CURRENT_RETURN_ALREADY_OBSERVED: Your supplied fresh object state at frame '
            + str(inp['frame']) + ' reports ' + obj + '.returned_and_released=true and supported=true, '
            'with no contrary current ownership. Your current return, or grasp immediately '
            'preparing that return, redundantly re-enacts a satisfied requested state. '
            'Re-read the complete task and generate your OWN remaining plan. Keep later '
            'requested transports of that same object, and do not invent a new completion '
            'event or next-stage answer. This feedback uses input observations only.']


def install(planner_module):
    if getattr(planner_module.validate, '_g21_goal_guard', False):
        return
    original = planner_module.validate
    def validate(inp, out, *args, **kwargs):
        return original(inp, out, *args, **kwargs) + errors(inp, out)
    validate._g21_goal_guard = True
    planner_module.validate = validate
