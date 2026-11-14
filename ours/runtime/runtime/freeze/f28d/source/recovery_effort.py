"""Measured correction effort and predicted residual, no generated action code."""
import math
from recovery_conditions import review_response


def feasibility(context):
    xy=math.hypot(context['target_dx_m'],context['target_dy_m'])
    gap=max(0.,.040+context['target_dz_m'])
    lifts=math.ceil(gap/.030)
    steps=math.ceil(max(0.,xy-.008)/.015)
    return dict(initial_xy_error_m=xy,target_xy_residual_m=.008,
        absolute_axis_error_m=[abs(context['target_dx_m']),abs(context['target_dy_m'])],
        minimum_xy_reduction_required_m=max(0.,xy-.008),three_horizontal_tool_capacity_m=.045,
        maximum_program_ticks=48,maximum_motion_ticks_per_tool=16,
        minimum_horizontal_tools_to_target=steps,minimum_upward_tools_to_height=lifts,
        full_alignment_feasible_without_lift=bool(gap==0 and steps<=3 and xy<=.065),
        note='Arithmetic lower bound, not an action plan or path certificate. Agent chooses all tools/arguments. An unchanged partial offset may still prevent the VLA grasp.')


def review(response,context,diagnosis):
    out=review_response(response,context,diagnosis)
    if not out.get('feedback',{}).get('measured_motion_contract'):return out
    effort=feasibility(context);out['feedback']['correction_effort']=effort
    if out['ok']and response.get('status')=='program'and response.get('intent')in('align','clear_and_reapproach'):
        path=out['feedback']['preflight'].get('tool_path',[])
        state=path[-1].get('predicted_state_after',context)if path else context
        residual=math.hypot(state['target_dx_m'],state['target_dy_m'])
        out['feedback']['predicted_final_xy_m']=residual
        if effort['initial_xy_error_m']>.015 and effort['full_alignment_feasible_without_lift']and residual>.008:
            out['errors'].append('UNDER_CORRECTION: the measured offset can be reduced to <=8mm within the existing48ticks/translation bounds, but this program leaves %.4fm. Author a sufficient bounded correction from fresh context, or explain actual missing path/support evidence with observe_only. No extra ticks or relaxed bounds.'%residual)
            out['ok']=False
    return out
