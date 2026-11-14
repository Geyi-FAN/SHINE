"""Declared M4 fixture preparation. Private facts never reach an Agent.

A source placement can finish with released fingers only 3cm apart, while the
unchanged M4 fixture requires >=4cm. Complete opening only AFTER native source
success, sustained physical release/support and stationary object. Keep arm pose.
This setup operation is logged separately; not actor credit or a new task.
"""
import math

def release_ready(ticks, source_task):
    if source_task not in (1,2,3,4,6,8,9):
        return False
    from t4_private_base_evidence import SOURCE, GOALS
    obj=SOURCE[source_task];window=list(ticks)[-8:]
    if len(window)!=8:return False
    subject={(t.get('episode_id'),t.get('task_id'))for t in window}
    if len(subject)!=1 or not window[-1].get('task_id'):return False
    ps=[]
    for t in window:
        f=t.get('physical',{});item=f.get('objects',{}).get(obj,{})
        p=t.get('measurements',{}).get(obj,{}).get('object_position')
        if (f.get('held_object')!='none' or f.get('native_goal_relations',{}).get(GOALS[source_task])is not True
                or item.get('supported')is not True or item.get('robot_contact')is not False
                or item.get('bilateral_contact')is not False or not p or len(p)!=3
                or not all(math.isfinite(x)for x in p)):
            return False
        ps.append(p)
    return max(math.dist(a,b)for a in ps for b in ps)<=.002

def tick(b,state,spec,due):
    if (not due or spec.get('evaluation_family')!='T4' or spec.get('phase')!='M4'
            or b.task_count!=1 or b.fixture_used or b.source_window_ready
            or state.mode!='completed' or state.completion_status!='verified'
            or state.task_id!=b.task):return False
    q=b.obs['robot0_gripper_qpos']
    if abs(float(q[0])-float(q[1]))>=.04:return False
    count=getattr(b,'source_handoff_open_ticks',0)
    if count>=20 or not release_ready(b.audit.tick.recent,spec['source_task']):return False
    with state.lock:
        if state.mode!='completed' or state.task_id!=b.task:return False
        if not b.env_lock.acquire(blocking=False):return False
        try:
            action=b.pose.action(b.obs);action[-1]=-1.0  # measured Panda open convention
            b.source_handoff_open_ticks=count+1
            b.log('source_fixture_release_opening',attempt=count+1,max_ticks=20,
                  original_gap_requirement_m=.04,source='private_fixture_preparation',
                  actor_credit=False,new_task=False)
            b.apply(action,'source_fixture_release_opening')
            return True
        finally:b.env_lock.release()


def fixture_pause(b):
    # A source already verified completed cannot accept a USER pause tool.
    # This private fixture freeze is explicitly not a measured Stop capability.
    s=b.state
    with s.lock:
        if not b.source_window_ready:
            raise ValueError('source_window_not_reached')
        if s.mode=='completed' and s.completion_status=='verified':
            s._hold('paused','T4_common_fixture_after_verified_source')
            b.log('source_fixture_completed_task_frozen',not_a_user_command=True,
                  scored_stop=False,task_id=s.task_id)
            return dict(status='accepted',executed=False,fixture_only=True,**s.snapshot())
        return b.command('robot_pause',reason='T4_common_fixture_not_scored_stop')
