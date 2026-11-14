"""Evidence-bounded second correction, never an outcome retry or a completion rule.

The existing two-program case cap and all tool limits remain authoritative.
One interrupted correction can be followed by a newly authored policy after
fresh observations and resumed VLA progress have been checked.
"""
import math
from recovery_progress import entity_for,point_in


def assess(stage,entered,frame,rows,context,diagnosis,previous):
    result=dict(permit=False,reason='no_qualified_previous_program',new_policy_required=True,
                creates_completion=False,existing_case_program_cap=2)
    if not previous:return result
    end=previous.get('finish_frame')
    if end is None:return dict(result,reason='previous_program_not_finished')
    if frame-end<48:return dict(result,reason='wait_for_existing_vla_followup48')
    if previous.get('operation')!=stage['operation']or previous.get('entered_step')!=entered:
        return dict(result,reason='previous_program_belongs_to_other_stage')
    if not diagnosis.get('eligible'):return dict(result,reason='no_new_measured_stall')
    if not all(context.get(k)is True for k in('hand_empty','target_visible','target_supported')):
        return dict(result,reason='fresh_empty_hand_visibility_support_required')
    entity=entity_for(stage)
    recent=[r for r in rows if max(entered,frame-12)<=r['frame']<=frame][-3:]
    if len(recent)!=3 or recent[-1]['frame']!=frame or recent[-1]['frame']-recent[0]['frame']<8:
        return dict(result,reason='three_fresh_frames_over8steps_required')
    if any(b['frame']-a['frame']>4 for a,b in zip(recent,recent[1:])):
        return dict(result,reason='new_observation_gap')
    pixels=[point_in(r,entity)for r in recent]
    if any(p is None for p in pixels):return dict(result,reason='fresh_target_not_reacquired')
    if any(entity+'.K1'not in r.get('geometry',{})for r in recent):
        return dict(result,reason='fresh_target_depth_not_reacquired')
    old=previous.get('initial_target_yx')
    if old is None or len(old)!=2:return dict(result,reason='previous_target_identity_anchor_missing')
    distance=lambda a,b:math.hypot(float(a[0])-float(b[0]),float(a[1])-float(b[1]))
    if max(distance(a,b)for a in pixels for b in pixels)>3:
        return dict(result,reason='target_still_moving_or_unstable_detection')
    if max(distance(p,old)for p in pixels)>6:
        return dict(result,reason='target_changed_since_previous_correction')
    interrupted=previous.get('finish_reason')=='Fresh target observation lost during correction'
    changed_mode=(previous.get('followup_status')=='local_alignment_improved'and
                  diagnosis.get('failure_mode')!=previous.get('failure_mode'))
    measured_descent=(previous.get('followup_status')=='local_approach_improved'and
                      previous.get('followup_height_gain_m',0)>=.008 and diagnosis.get('failure_mode')=='vertical_standoff')
    if not interrupted and not changed_mode and not measured_descent:
        return dict(result,reason='same_failure_without_new_recovery_evidence')
    return dict(result,permit=True,reason='fresh_reacquired_target_after_interruption'if interrupted else'new_failure_mode_after_measured_alignment_progress'if changed_mode else'new_measured_height_after_actual_approach_progress',
                evidence_frames=[r['frame']for r in recent],previous_finish_frame=end,
                previous_finish_reason=previous.get('finish_reason'),previous_failure_mode=previous.get('failure_mode'),
                current_failure_mode=diagnosis.get('failure_mode'))
