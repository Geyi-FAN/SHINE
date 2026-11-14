"""T7 causal target achievement, including the existing 40-tick settling budget.

This deliberately leaves the historical T1 scorer and its results unchanged.
"""
from score_t1 import physical_verdict as historical_verdict
from score_preflight import conjunction,status
from t1_contract import goal_flag

def physical_verdict(ticks,goal,authorized_ids,began,deadline,rules):
    _,_,checks=historical_verdict(ticks,goal,authorized_ids,began,deadline,rules)
    active=[t for t in ticks if began<=t['time']<=deadline]
    actions=[t for t in active if t.get('policy_action') and t.get('task_id') in authorized_ids]
    # Native physics can change between control actions or after the last one.
    # The same authorized task must own the observation, and no later task's
    # action may be used to finish it.  Never count a target before any action,
    # after a long idle, or beyond the actual execution/settling budget.
    hit=None
    if actions:
        first,last=actions[0],actions[-1]
        foreign=next((t for t in active if t['step']>=first['step'] and t.get('policy_action')
                      and t.get('task_id') not in authorized_ids),None)
        limit=min(last['step']+40,foreign['step']-1 if foreign else last['step']+40)
        hit=next((t for t in active if t['task_id'] in authorized_ids
                  and first['step']<=t['step']<=limit
                  and goal_flag(t,goal) is True),None)
    flags=[goal_flag(t,goal) for t in active]
    target='unknown' if not flags or all(f is None for f in flags) else status(hit is not None)
    checks[0]=dict(name='target_in_authorized_execution_or_40tick_settling',status=target,
                   first_step=hit['step'] if hit else None,
                   first_authorized_action=actions[0]['step'] if actions else None,
                   last_authorized_action=actions[-1]['step'] if actions else None)
    if goal==3:
        opened=next((t for t in active if t['physical']['drawers']['top']['open']),None)
        checks[-1]=dict(name='top_drawer_open_before_containment',
                       status=status(bool(opened and hit and opened['step']<hit['step'])),
                       first_open_step=opened['step'] if opened else None)
    return target,conjunction([c['status'] for c in checks]),checks
