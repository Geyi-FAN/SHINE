"""One current-task terminal gate for both execution routes.

Private physical facts are used only for final acceptance, never to write a plan,
subgoal or point. Native target contact alone cannot stop a placement policy.
"""
from collections import deque
import copy
import math

PLACEMENTS={5:'plate',1:'bowl',2:'wine_bottle',3:'bowl',4:'bowl',6:'cheese',8:'bowl',9:'wine_bottle'}

def physical_support(frame):
    return bool(frame.get('support_contact')or any(p.get('objects')==['akita_black_bowl_1','cream_cheese_1']and p.get('penetration',0)>0 for p in frame.get('object_object_contacts',[])))

class CompletionGate:
    def __init__(self, subject, rules, hold_ticks=40):
        self.subject=tuple(subject);self.rules=rules;self.hold_ticks=hold_ticks
        self.rows=deque(maxlen=8);self.holding=False;self.hold_seen=0;self.accepted=False
    def observe(self,row,subject,target_task,return_only=False,full_contract=False):
        if tuple(subject)!=self.subject:return False
        self.rows.append(row)
        is_placement=target_task in PLACEMENTS or return_only
        ready=bool(row['adjusted_goal'])
        if is_placement:
            from benchmark_metrics.events import restore_window
            frames=[r['source'] if return_only else r['target'] for r in self.rows]
            ready=ready and bool(frames) and restore_window(frames,dict(reference_position=frames[-1]['object_position'],stable_required=True,withdraw_required=False),1e6,self.rules)['complete']
            if target_task==6 and not return_only and len(frames)>=5:
                w=frames[-5:]
                diameter=max(math.dist(a['object_position'],b['object_position'])for a in w for b in w)
                ready=(bool(row['adjusted_goal']) and all(r['adjusted_goal']for r in list(self.rows)[-5:])
                       and all(not f['target_contact']for f in w)and diameter<=self.rules['restore']['stable_diameter_m']
                       and physical_support(w[-1])and sum(physical_support(f)for f in w)>=self.rules['restore']['support_min_true'])
        if row.get('requires_open_handoff'):
            ready=ready and row.get('gripper_aperture_m',0)>=.065
        if row.get('requires_disengage'):
            clear=[r.get('metric_evidence',{}).get('hand_clear_of_cabinet')for r in self.rows]
            ready=ready and len(clear)>=3 and all(value is True for value in clear[-3:])
        if not ready or not full_contract:
            self.holding=False;self.hold_seen=0;return False
        if not self.holding:self.holding=True;self.hold_seen=0
        else:self.hold_seen+=1
        return self.hold_seen>=self.hold_ticks

def install(bridge_class):
    def measure(b,phase):
        from benchmark_metrics.events import restore_window,restore_radius
        from g21.private_acceptance import CurrentContractAcceptance
        sm=b.source.measure();tm=b.target.measure();goal=b.rt.frame(b.target,b.case['target_task']);ev=b.authority.published.evidence(b.env,b.case,b.contract)
        adjusted=bool(goal['goal'])
        for site,x in ev.get('regions',{}).items():adjusted=adjusted or bool(b.runner.region_contains(x,b.rules['target_regions'][site]['margin_m']))
        if getattr(b,'custom_goal_predicate',None):
            goal=copy.deepcopy(goal);goal['goal']=bool(b.env.env._eval_predicate(b.custom_goal_predicate));goal['goal_kind']='explicit_custom_predicate';adjusted=goal['goal']
        if getattr(b,'live_open_only',None):
            goal=copy.deepcopy(goal);goal['goal']=bool(b.env.env._eval_predicate(['open','wooden_cabinet_1_'+b.live_open_only+'_region']));goal['goal_kind']='selected_open_only';adjusted=goal['goal']
        if getattr(b,'live_close_only',None):
            from benchmark_metrics.predicates import drawer_gap
            goal=copy.deepcopy(goal);goal['goal']=drawer_gap(sm['articulation'][b.live_close_only])<=b.rules['close']['gap_m'];goal['goal_kind']='selected_close_only';adjusted=goal['goal']
        if getattr(b,'return_only',False):
            clause=next(c for c in b.contract['clauses'] if c['kind']=='restore_episode_start')
            frames=[r['source'] for r in b.measurements[-7:]]+[sm]
            adjusted=bool(restore_window(frames,clause,restore_radius(b.case,clause,b.rules),b.rules)['complete']);goal=copy.deepcopy(goal);goal['goal']=adjusted;goal['goal_kind']='return_released_only'
        row=dict(step=len(b.measurements)+1,world_physics_step=b.physics_steps,phase='policy',actual_phase=phase,engine_control_step=b.control_steps,simulation_time=float(b.env.sim.data.time),source=sm,target=tm,goal_frame=goal,metric_evidence=ev,adjusted_goal=adjusted)
        import re
        if b.case['target_task']==0 or getattr(b,'live_close_only',None)or getattr(b,'live_open_only',None)or('cabinet'in b.state.instruction.lower()and re.search(r'disengage|withdraw|move.+(?:hand|gripper).+clear',b.state.instruction,re.I)):
            from repair.physical_extra import evidence
            extra=evidence(b.env,b.obs);distance=extra['hand_to_cabinet_geom_center_m']
            row['requires_disengage']=True;row['metric_evidence']['hand_clear_of_cabinet']=extra['cabinet_robot_contact']is False and distance is not None and distance>=b.rules['restore']['withdraw_distance_m']
        row['requires_open_handoff']=bool(b.state.deferred_task and b.route=='native'and b.case['target_task']in PLACEMENTS)
        row['gripper_aperture_m']=float(sum(abs(x)for x in b.obs['robot0_gripper_qpos']))
        b.measurements.append(row)
        if b.acceptance is None:
            b.acceptance=CurrentContractAcceptance(b.case,b.contract,b.rules,b.initial,b.score,b.terminal)
            b.completion_gate=CompletionGate(b.token()[:3],b.rules)
        gate=b.completion_gate
        # Expensive independent contract scoring only after the physical target.
        full=bool(adjusted and b.score().get('instruction_adjusted',{}).get('success'))
        was=gate.holding;allowed=gate.observe(row,b.token()[:3],0 if getattr(b,'live_open_only',None)else b.case['target_task'],getattr(b,'return_only',False),full)
        if gate.holding and not was:
            from hold_gate import PoseHold
            b.pose=PoseHold(b.obs,b.env.env.robots[0].controller);b.state.queue.clear()
            if b.native:b.native.invalidate(b.state)
            b.log('completion_settling_started',task_id=b.state.task_id,hold_ticks=gate.hold_ticks,source='current_goal_release_support_stability_and_contract')
        if was and not gate.holding:b.log('completion_settling_invalidated',reason='current_physical_or_contract_condition_lost')
        # Suppress only the stop candidate; preserve the raw full trace for the
        # independent final scorer and for failures of ordering/preservation.
        checked=copy.deepcopy(row)
        if not allowed:checked['adjusted_goal']=False;checked['goal_frame']['goal']=False
        decision=b.acceptance.observe(checked,b.token()[:3])
        if decision:b.commit_acceptance(decision)
    bridge_class.measure=measure
