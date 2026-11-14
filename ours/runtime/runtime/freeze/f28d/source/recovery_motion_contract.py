"""Validate Agent-chosen recovery intent, predicted progress and live tool direction.

Validation rejects a strategy; it never writes a replacement program or subgoal.
"""
import math
import numpy as np
from cap_program import Program,MotionBudget,InvalidProgram,refresh_vector_properties
from recovery_progress import PLACEMENTS

EXPECTED={'align':'reduce_target_xy_error','clear_and_reapproach':'reduce_target_xy_error',
          'orientation_test':'grasp_progress','reacquire':'planner_reacquires_object',
          'lower_approach':'reduce_target_vertical_gap'}


def validate_live(command,context,intent,diagnosis):
    if intent not in EXPECTED:raise InvalidProgram('Documented recovery intent required')
    name=command['tool'];a=command['arguments'];target=np.array([context['target_dx_m'],context['target_dy_m'],context['target_dz_m']],float)
    if intent!='reacquire'and(np.linalg.norm(target)>.16 or np.linalg.norm(target[:2])>.065):raise InvalidProgram('Target outside bounded local recovery scope; observe/replan, not a cosmetic rotation')
    if intent=='lower_approach'and np.linalg.norm(target[:2])>.015:raise InvalidProgram('A vertical approach requires current horizontal alignment within1.5cm')
    if name=='move_relative':
        move=np.array([a.get(k,0.)for k in ['dx_m','dy_m','dz_m']])
        if intent=='lower_approach'and(math.hypot(move[0],move[1])>0 or move[2]>=0):raise InvalidProgram('lower_approach is a strictly downward approach only, within the original descent/clearance limits')
        if intent=='reacquire':raise InvalidProgram('Reacquire requires planner handoff, not speculative relocation')
        if np.linalg.norm(move[:2])>0:
            if np.dot(move[:2],target[:2])<=0:raise InvalidProgram('Horizontal direction moves away from the observed target')
            if np.linalg.norm(target[:2]-move[:2])>np.linalg.norm(target[:2])+.0005:raise InvalidProgram('Horizontal correction overshoots the observed target')
    if name=='rotate_relative':
        if intent!='orientation_test'and not diagnosis.get('orientation_test_allowed',False):raise InvalidProgram('Rotation lacks repeated near-target failed-grasp evidence')
        if not diagnosis.get('orientation_test_allowed',False)or np.linalg.norm(target[:2])>.015:raise InvalidProgram('A rotation-only correction cannot repair a large position error')
    if intent=='orientation_test'and name=='move_relative'and math.hypot(a.get('dx_m',0),a.get('dy_m',0))>0:raise InvalidProgram('Separate approach alignment from an orientation test')


def validate_strategy(response,context,diagnosis,audit=None):
    intent=response.get('intent');expected=response.get('expected_progress')
    if intent not in diagnosis.get('allowed_intents',[]):raise InvalidProgram('Intent is unsupported by the measured failure diagnosis')
    if intent=='reacquire'and context.get('operation')not in PLACEMENTS:raise InvalidProgram('This action does not require prior ownership; do not invent a grasp')
    if expected!=EXPECTED.get(intent):raise InvalidProgram('Use the expected_progress contract for the selected intent')
    if intent=='lower_approach'and(context.get('stage_kind')!='grasp'or context['target_dz_m']>-.080):raise InvalidProgram('lower_approach needs an observed empty-hand grasp standoff at least8cm above target')
    c=dict(context,clear_upward=response.get('free_upward')is True);p=Program(response.get('policy_code'),trace_conditions=audit is not None);budget=MotionBudget();commands=[];steps=0;rotated=False
    if audit is not None:audit.update(source='measured_initial_state_then_ideal_prediction',not_executed=True,conditions=p.condition_trace,tool_path=[])
    initial_xy=float(np.hypot(c['target_dx_m'],c['target_dy_m']))
    initial_height=-float(c['target_dz_m'])
    for _ in range(9):
        cmd=p.next(c)
        if cmd is None:break
        if audit is not None:audit['tool_path'].append(dict(command=cmd,state_before=dict(c),authorized=False))
        budget.authorize(cmd,c);validate_live(cmd,c,intent,diagnosis);commands.append(cmd)
        if audit is not None:audit['tool_path'][-1]['authorized']=True
        name,a=cmd['tool'],cmd['arguments'];steps+=int(a.get('steps',8))if name=='observe'else 12 if name=='open_gripper'else 16
        if name=='move_relative':
            for axis in ('x','y','z'):c['target_d'+axis+'_m']-=a.get('d'+axis+'_m',0.)
            refresh_vector_properties(c)
        if audit is not None:audit['tool_path'][-1]['predicted_state_after']=dict(c)
        rotated|=name=='rotate_relative'
    if steps>48:raise InvalidProgram('Correction must fit48control steps; leave room for fresh observation and the64-step window boundary')
    if intent in ('align','clear_and_reapproach')and initial_xy-float(np.hypot(c['target_dx_m'],c['target_dy_m']))<.003:raise InvalidProgram('Program predicts no >=3mm alignment gain; do not substitute an unrelated small motion')
    if intent=='orientation_test'and not rotated:raise InvalidProgram('An orientation test must contain the supported small rotation')
    if intent=='lower_approach'and initial_height+float(c['target_dz_m'])<.003:raise InvalidProgram('lower_approach must reduce measured vertical standoff by at least3mm; no cosmetic hold')
    if intent=='reacquire'and not p.replan:raise InvalidProgram('Reacquire must explicitly hand control back to the planning Agent')
    if intent!='reacquire'and p.replan:raise InvalidProgram('A different intent cannot silently request a new plan')
    return dict(intent=intent,expected_progress=expected,planned_control_steps=steps,commands=commands,planned_xy_gain_m=initial_xy-float(np.hypot(c['target_dx_m'],c['target_dy_m'])),creates_completion=False)
