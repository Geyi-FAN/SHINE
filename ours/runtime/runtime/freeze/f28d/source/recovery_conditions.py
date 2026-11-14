"""Transparent measured-state explanations and response validation, no new policy.

No object truth, code generation, completion decisions, model call or live motion.
Existing MotionBudget and validate_strategy remain the numerical authority.
"""
import math
from numbers import Real
from cap_program import InvalidProgram
from recovery_motion_contract import validate_strategy


def measured_motion_contract(context):
    for axis in ('x','y','z'):
        value=context.get('target_d'+axis+'_m')
        if isinstance(value,bool)or not isinstance(value,Real)or not math.isfinite(value):
            raise InvalidProgram('Missing or non-finite measured TARGET minus HAND offset')
    visible=context.get('target_visible')is True
    supported=context.get('target_supported')is True
    dz=float(context['target_dz_m'])
    # Only expose height when the current target is actually observed. Placeholder
    # deltas on a missing detection are not a measurement, even if they are zero.
    height=-dz if visible else None
    return dict(schema='measured_motion_contract_v1',
        offset_definition='TARGET minus HAND in WORLD meters',
        positive_world_z='up',
        hand_above_target_m=height,
        minimum_horizontal_height_m=.040,
        horizontal_geometry_satisfied=bool(visible and supported and dz<=-.040),
        empty_hand_evidence=context.get('hand_empty')is True,
        target_visible=visible,target_supported=supported,
        nominal_upward_gap_to_horizontal_m=max(0.,.040-height)if height is not None else None,
        upward_path_state='qualified_in_input'if context.get('clear_upward')is True else'not_qualified_in_input',
        note='Derived arithmetic only; not collision clearance or a permission. free_upward needs the same current visual evidence. Every actual tool rechecks live evidence.')


def review_response(response,context,diagnosis):
    """Keep the Agent output verbatim; return grounded correction feedback only."""
    errors=[];audit={};summary=None;measured=None
    if not isinstance(response,dict):
        return dict(ok=False,errors=['Return one JSON object'],feedback={},validated_plan_summary=None)
    try:measured=measured_motion_contract(context)
    except InvalidProgram as exc:errors.append(str(exc))
    status=response.get('status')
    if status not in ('program','observe_only'):errors.append('status must be program or observe_only')
    if type(response.get('free_upward'))is not bool:errors.append('free_upward must be a boolean')
    if not isinstance(response.get('reason'),str)or not response['reason'].strip():errors.append('reason must state current evidence and agree with the executable decision')
    if status=='observe_only':
        if response.get('intent')!='observe_only'or response.get('expected_progress')!='none':
            errors.append('observe_only requires intent=observe_only and expected_progress=none')
        if response.get('policy_code')!='':errors.append('observe_only requires empty policy_code; a proposed program cannot be hidden in an observation response')
    elif status=='program'and not errors:
        try:summary=validate_strategy(response,context,diagnosis,audit=audit)
        except (InvalidProgram,TypeError,KeyError,ZeroDivisionError,OverflowError)as exc:errors.append(str(exc))
    failed=next((step for step in audit.get('tool_path',[])if not step['authorized']),None)
    feedback=dict(measured_motion_contract=measured,preflight=audit,failed_tool=failed,
                  constraints_unchanged=True,code_rewritten=False,
                  instruction='Regenerate from the SAME observations. Match the measured sign, traversed branches and original tool bounds. If no permitted program is justified, return a consistent observe_only response. Do not declare completion.')
    return dict(ok=not errors,errors=errors,feedback=feedback,validated_plan_summary=summary)
