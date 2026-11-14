"""Credit actual asynchronous physics caused by an authorized task action.

Post-terminal evaluator holds, old tasks and action-free fixtures earn no hit.
"""
def first_authorized_hit(frames,flags,task_ids):
    started=set()
    for i,(row,flag)in enumerate(zip(frames,flags)):
        task=row['task_id']
        if row.get('policy_action')and task in task_ids:started.add(task)
        if (flag is True and task in started and row.get('mode')in('running','verifying')
                and row.get('physics_tick',True)and row.get('phase')!='evaluator_terminal_hold'):
            return i
    return None
