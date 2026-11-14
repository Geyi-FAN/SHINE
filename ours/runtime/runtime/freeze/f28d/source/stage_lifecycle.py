"""Admit an Agent-selected plan without resetting or completing unfinished work.

Same-stage regeneration is idempotent. A fresh, observed empty hand can admit
the Agent's same-object reacquisition prerequisite ONLY if its very next goal
is the still-unfinished return. No goal or completion is generated here.
"""
def key(stage):return tuple(stage.get(k)for k in('operation','kind','object'))


def classify(active,plan,frame,width,held,visual):
    if not plan:return dict(mode='reject',reason='nonempty_plan_required',creates_completion=False)
    if active is None:return dict(mode='select',reason='no_unfinished_stage',creates_completion=False)
    first=plan[0]
    if key(active)==key(first):return dict(mode='keep',reason='same_unfinished_stage_keep_original_clock',creates_completion=False)
    obj=active.get('object');v=visual or{}
    fresh=0<=frame-v.get('frame',-1000)<=8
    reacquire=(active.get('kind')=='return'and first.get('kind')=='grasp'and first.get('object')==obj and
        len(plan)>=2 and key(plan[1])==key(active))
    proof=fresh and held=='none'and width>=.065 and v.get('held_object')=='none'and v.get('support_visible',{}).get(obj)is True
    if reacquire and proof:
        return dict(mode='interrupt_for_reacquisition',reason='Agent_selected_same_object_grasp_then_resume_unfinished_return',
            interrupted_operation=active['operation'],creates_completion=False,unfinished_goal_retained=True,evidence_frame=v['frame'])
    return dict(mode='reject',reason='cannot_skip_or_replace_unfinished_stage_without_observed_prerequisite',
        active_operation=active['operation'],proposed_operation=first.get('operation'),fresh_empty_support_proof=bool(proof),creates_completion=False)


def apply(mon,stage,admission):
    if admission['mode']=='keep':return False
    if admission['mode']=='reject':raise ValueError('Rejected stage transition must not reach selection')
    if admission['mode']=='interrupt_for_reacquisition':mon.active=None
    mon.select(stage);return True
