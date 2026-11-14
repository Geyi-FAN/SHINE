"""Input-only tool preconditions. Returns feedback; never selects the next action."""
def errors(pred,payload):
    result=[];tool=pred.get('recovery_request');context=payload.get('observation_request_context') or {}
    stage=context.get('selected_stage') or {};width=payload.get('measured_gripper_width_m')
    if context.get('reason')=='current_target_reference_missing' and tool=='none':
        result.append('The required symbolic coordinate is unavailable. Recognizing the object in an image does not supply a usable YOLO point. Request observe_only or an applicable bounded observation tool; none cannot resume the current policy. If stationary observation already failed, assess observe_above from the actual overhead clearance in these images; never invent a coordinate.')
    if tool=='observe_clear_cabinet':
        close_scope=stage.get('kind')=='close' and context.get('reason')=='close_candidate_needs_clearer_geometry_or_visual_identity'
        open_scope=stage.get('operation') in ('open_top','open_middle','close_top','close_middle') and context.get('reason')=='drawer_has_not_completed_after_bounded_execution'
        if not(close_scope or open_scope):result.append('Cabinet withdrawal requires the selected close-view context or explicitly supplied stalled-drawer context; it is not an initial scene-inspection tool.')
        if pred.get('held_object')!='none':result.append('Cabinet withdrawal requires an EMPTY hand; unknown or carried-object evidence cannot authorize it.')
        if width is None or not(width>=.065 or width<.002):result.append('Cabinet withdrawal needs open fingers or an almost-fully-closed EMPTY hand; partially closed possibly occupied fingers are not allowed.')
    if context.get('reason')=='drawer_has_not_completed_after_bounded_execution' and tool not in ('observe_only','observe_clear_cabinet','none'):
        result.append('This context only allows a guarded cabinet observation reset or observation/no tool. Do not introduce placement, payload release or grasp tools.')
    if tool=='open_empty_gripper':
        placement_recovery=stage.get('operation')=='cheese_bowl' and pred.get('held_object')=='none' and pred.get('support_visible',{}).get('cheese') is True and pred.get('relations',{}).get('cheese_bowl') is False
        if stage.get('kind')!='grasp' and not placement_recovery:result.append('open_empty_gripper needs a CURRENTLY SELECTED stalled grasp, or a stalled cheese placement with visible supported cheese outside the bowl and an empty hand. It is not an initial takeover tool. Reconsider supported-contact release or observe_only from the same images.')
        if width is not None and width>=.002:result.append('Measured width is not the almost-fully-closed EMPTY threshold <.002m. Do not use open_empty_gripper. A closed hand touching a visibly supported object requires release_supported_in_place, with release_object identifying that supported object; otherwise observe_only.')
    if tool=='release_supported_in_place':
        obj=pred.get('release_object')
        if obj not in ('bowl','cheese','wine_bottle','plate') or pred.get('support_visible',{}).get(obj) is not True:
            result.append('Supported release requires an identified release_object and clearly visible existing support; never release an airborne or unidentified object.')
    if tool=='clear_supported_object':
        legacy=context.get('reason')=='supported_in_place_release_executed_but_hand_may_still_intersect_old_object'
        prior=context.get('preceding_observed_return')or{}
        proof=context.get('measured_clearance_context')or{}
        frames=payload.get('sensor_frames')or[];now=frames[-1].get('frame')if frames else None
        distance=proof.get('measured_hand_distance_m')
        returned=(context.get('reason')=='accepted_return_before_different_object_grasp'and prior.get('outcome')=='completed'
                  and str(prior.get('operation','')).startswith(('return_','release_'))
                  and prior.get('object')==context.get('released_object')and prior.get('object')!=stage.get('object')
                  and stage.get('kind')=='grasp'and now is not None and prior.get('confirmed_step',now+1)<=now
                  and proof.get('frame')==now and proof.get('object')==prior.get('object')
                  and(proof.get('old_K1_source')=='fresh_YOLO_plus_RGBD'or(
                      proof.get('old_K1_source')=='phase_static_cached_YOLO_RGBD'and proof.get('resolution')=='cached_static_depth'
                      and proof.get('image_point_frame')==now and proof.get('current_depth_missing')is True
                      and proof.get('camera_verified')is True and 0<proof.get('cache_age_steps',999)<=24
                      and isinstance(proof.get('source_frame'),int)and now-proof['source_frame']==proof['cache_age_steps']
                      and 0<=proof.get('pixel_drift_px',999)<=3.))and proof.get('image_stable')is True
                  and isinstance(distance,(int,float))and 0<=distance<=.12
                  and width is not None and width>=.065)
        if not(legacy or returned):result.append('clear_supported_object requires an executed supported-release context, or the explicitly supplied accepted-return/different-object context with fresh open-hand, stable near-object measurements. Do not invent a prior release or substitute for an initial release.')
        if returned and(pred.get('held_object')!='none'or pred.get('support_visible',{}).get(prior.get('object'))is not True):result.append('Post-return clearance requires independently visible support for the OLD object and an empty open hand; unknown or carried-object reports cannot authorize movement.')
    if tool=='replan_current_task':
        obj=stage.get('object')
        if pred.get('held_object')!='none':result.append('This recovery tool is for an EMPTY hand after a failed placement; you report an object still held. Reconsider observation/reposition or continuing; do not falsely claim ownership loss.')
        if obj and pred.get('support_visible',{}).get(obj) is not True:result.append('Reacquisition recovery requires the released object supported somewhere; airborne/unknown is not enough evidence.')
    if width is not None and width<.002 and pred.get('held_object') in ('cheese','wine_bottle','bowl'):
        result.append('Measured fingers are almost fully closed below2mm. A clearly grasped cheese block/bottle/bowl cannot fit that gap. Recheck whether WRIST only sees an object in front of the hand; use unknown/none if attachment is not supported.')
    if tool=='replan_current_task' and (not stage or stage.get('kind')!='target'):
        result.append('replan_current_task requires a CURRENTLY SELECTED stalled placement. Initial scene inspection must report facts or request observation; do not invent a placement to replan.')
    if tool=='release_supported_in_place' and stage.get('kind')=='grasp' and pred.get('release_object')==stage.get('object'):
        result.append('The proposed release_object is the CURRENT GRASP TARGET, not a non-target object blocking the hand. Recheck support/ownership from current views; do not rename the target as a non-target.')
    return result
