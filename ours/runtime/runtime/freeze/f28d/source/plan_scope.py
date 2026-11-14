"""Reject unrequested post-goal closure; never write or edit an Agent plan.

Implicit settlement cases remain under human review. This module does not add,
remove or authorize any return operation, or read an evaluator contract.
"""
import re


def errors(utterance, plan):
    if not isinstance(plan, list):
        return []
    # A close/shut request can be expressed with pronouns. Object-specific
    # disambiguation remains the planner's responsibility; do not reject it
    # merely because the exact template is absent from the original speech.
    requested_close = bool(re.search(r'\b(?:close|closing|closed|shut|shutting)\b|关上|关闭|关好|关掉|合上', utterance, re.I))
    if requested_close:
        return []
    containment_request = (bool(re.search(r'\b(?:put|putting|place|placing)\b',utterance,re.I))
                           and 'drawer' in utterance.lower() and bool(re.search(r'\b(?:in|inside)\b',utterance,re.I))) or ('放' in utterance and '抽屉' in utterance)
    seen_containment = containment_request
    for stage in plan:
        operation = stage.get('operation')
        if operation == 'bowl_drawer':
            seen_containment = True
        if seen_containment and operation in ('close_top', 'close_middle'):
            return ['UNREQUESTED_POST_GOAL_CLOSURE: Putting an object inside a drawer does not by itself request closing it afterward. Your remaining plan appends drawer closure after containment without user authorization. Regenerate the plan from the original utterance. Retain explicitly requested closing and genuinely necessary opening/grasping prerequisites; do not invent a return task.']
    return []


ADDENDUM = '''
PLAN SCOPE: Inspect every remaining operation, including operations after the
current target. Putting an object inside a drawer does not imply closing that
drawer afterward. Do not append closure unless the user requests it. Preserve
explicit close/shut requests, including pronouns, and necessary opening/grasping
prerequisites. Task completion is the requested physical state; do not invent a
new requested state after it. The planner still generates every subgoal.
'''
