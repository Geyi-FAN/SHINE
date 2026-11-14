"""Read-only v2.5 facts; no reference plan, index, future stage or GT pixel input.

Benchmark semantics are imported from the frozen package. Controller-only grasp,
release and native-target gates are reported separately from benchmark scores.
"""
from collections import deque
import numpy as np
from benchmark_metrics import load_rules
from benchmark_metrics.events import restore_radius,restore_window,high_releases
from benchmark_metrics.predicates import drawer_gap
from sim_runtime import GeometryRuntime
from scene_memory import stationary_window

OBJECTS={'bowl':('akita_black_bowl_1',1),'cheese':('cream_cheese_1',6),
         'wine_bottle':('wine_bottle_1',2),'plate':('plate_1',5)}
TARGETS={'open_middle':0,'bowl_stove':1,'bottle_cabinet':2,'bowl_drawer':3,
         'bowl_cabinet':4,'push_plate':5,'cheese_bowl':6,'turn_on_stove':7,
         'bowl_plate':8,'bottle_rack':9}

class Completion:
    def __init__(self,env,initial_xyz,source_task,previous_instruction):
        self.env=env;self.rt=GeometryRuntime();self.rules=load_rules()
        self.context={'source_task':source_task,'previous_instruction':previous_instruction}
        self.initial_xyz=initial_xyz
        self.mon={k:self.rt.monitor(env,t) for k,(_,t) in OBJECTS.items()}
        self.windows={k:deque(maxlen=8) for k in OBJECTS}
        self.joints=deque(maxlen=5);self.goal_history=deque(maxlen=5)
        self.events=[];self.active=None;self.entered=None;self.last=-1;self.snapshot={}
        import os
        self.memory_window_translation=float(os.environ.get('HYBRID_OBJECT_STATIC_WINDOW_M','0.002'))
        self.memory_window_rotation=float(os.environ.get('HYBRID_OBJECT_STATIC_WINDOW_DEG','2'))
        if not 0<self.memory_window_translation<=.05 or not 0<self.memory_window_rotation<=45:raise ValueError('invalid static window tolerances')
        self.entry_positions={};self.drop_seen=set()
    def observe(self,step):
        if step<=self.last:
            if step==self.last:return None
            raise ValueError('noncausal physical observation')
        self.last=step
        rows={k:m.measure() for k,m in self.mon.items()}
        if not self.entry_positions:self.entry_positions={k:r['object_position'][:] for k,r in rows.items()}
        for k,r in rows.items():self.windows[k].append(r)
        self.joints.append(rows['bowl']['articulation'])
        goals={k:bool(self.rt.goals(self.env,t)) for k,t in TARGETS.items()}
        self.goal_history.append(goals)
        held=[k for k,r in rows.items() if r['bilateral_finger_contact'] and r['target_contact']]
        returns={}
        for k,(name,_) in OBJECTS.items():
            ref=self.initial_xyz.get(name)
            if ref is None:returns[k]=None;continue
            clause=dict(object=name,reference_position=ref,stable_required=True,withdraw_required=False)
            flags=restore_window(list(self.windows[k]),clause,restore_radius(self.context,clause,self.rules),self.rules)
            returns[k]=bool(flags['complete']) if len(self.windows[k])>=5 else None
        self.snapshot=dict(source='simulator_physical_facts_v2.5',observed_step=step,
            held_object=held[0] if len(held)==1 else 'none' if not held else 'unknown',
            objects={k:dict(robot_contact=bool(r['target_contact']),supported=bool(r['support_contact']),
                           bilateral_contact=bool(r['bilateral_finger_contact']),returned_and_released=returns[k]) for k,r in rows.items()},
            drawers={k:dict(open=bool(self.env.env._eval_predicate(['open','wooden_cabinet_1_'+k+'_region'])),
                           closed_current=drawer_gap(self.joints[-1][k])<=self.rules['close']['gap_m'],
                           closed_confirmed=len(self.joints)==5 and all(drawer_gap(r[k])<=self.rules['close']['gap_m'] for r in self.joints)) for k in ('top','middle')},
            native_goal_relations=goals)
        if self.active:
            op=self.active;obj=op.get('object');kind=op['kind'];complete=False;failed=False
            if kind=='return':
                name=OBJECTS[obj][0];ref=self.initial_xyz.get(name)
                if ref is not None:
                    clause=dict(object=name,reference_position=ref,stable_required=True,withdraw_required=op['operation'].endswith('_clear'))
                    w=list(self.windows[obj]);complete=restore_window(w,clause,restore_radius(self.context,clause,self.rules),self.rules)['complete']
                    # A confirmed release failure is reported, not silently relabelled complete.
                    failed=bool(high_releases(w[-4:],ref,self.rules))
            elif kind=='release':
                clause=dict(object=OBJECTS[obj][0],reference_position=self.entry_positions[obj],stable_required=True,withdraw_required=False)
                complete=restore_window(list(self.windows[obj]),clause,self.rules['restore']['radius_m'],self.rules)['complete']
            elif kind=='close':complete=self.snapshot['drawers']['top' if obj=='top_drawer' else 'middle']['closed_confirmed']
            elif kind=='grasp':
                w=list(self.windows[obj])[-5:]
                complete=len(w)==5 and all(r['bilateral_finger_contact'] and r['target_contact'] and not r['support_contact'] for r in w)
            elif kind=='open_top':complete=self.snapshot['drawers']['top']['open']
            elif op['operation'] in TARGETS:
                complete=goals[op['operation']]
                # Execution language promises stable release/disengagement. This is
                # an operator guard, never an extra v2.5 benchmark target criterion.
                if obj in OBJECTS:
                    clause=dict(object=OBJECTS[obj][0],reference_position=rows[obj]['object_position'],stable_required=True,withdraw_required=False)
                    complete=complete and restore_window(list(self.windows[obj]),clause,1e6,self.rules)['complete']
            if failed or complete:
                event=dict(operation=op['operation'],object=obj,outcome='failed' if failed else 'completed',
                           reason='high_unsupported_release' if failed else 'physical_condition_satisfied',
                           entered_step=self.entered,confirmed_step=step,source='simulator_v2.5_hybrid_monitor')
                self.events.append(event);self.active=None
                return event
        return None
    def select(self,stage):
        if self.active:raise ValueError('Cannot replace an unfinished operation without an explicit interruption')
        self.active=dict(stage);self.entered=self.last

    def memory_evidence(self):
        """Private cache validity evidence; no world positions go to planner or policy."""
        facts={}
        for entity,window in self.windows.items():
            rows=list(window)[-5:];pose=rows[-1]['object_position']+rows[-1]['object_quaternion_wxyz']
            static=stationary_window(rows,self.memory_window_translation,self.memory_window_rotation)
            # Acquisition needs a stationary observation window. Reuse tolerates
            # light touching while support and the original pose remain valid.
            reusable=bool(rows[-1]['support_contact'] and not rows[-1]['bilateral_finger_contact'])
            facts[entity]=dict(static=bool(static),cache_reusable=reusable,pose=pose)
        # Fixed facilities are cacheable only when their simulator body is resolved.
        core=self.env.env;sim=self.env.sim
        aliases={'stove_placement':'flat_stove_1','cabinet_top_placement':'wooden_cabinet_1','wine_rack_placement':'wine_rack_1','table_front_placement':'table'}
        for entity,name in aliases.items():
            try:
                bid=core.obj_body_id.get(name)
                if bid is None:bid=sim.model.body_name2id(name)
                if bid<0:continue
                facts[entity]=dict(static=True,pose=sim.data.body_xpos[bid].tolist()+sim.data.body_xquat[bid].tolist())
            except (KeyError,ValueError):pass
        cabinet=facts.get('cabinet_top_placement')
        if cabinet and len(self.joints)==5:
            top=[float(x['top']) for x in self.joints]
            facts['top_drawer_interior']=dict(
                static=bool(self.snapshot['drawers']['top']['open'] and max(top)-min(top)<=1e-5),
                pose=cabinet['pose']+[top[-1]])
        return facts
    def memory_camera_id(self):
        import hashlib
        sim=self.env.sim;cid=sim.model.camera_name2id('agentview')
        values=np.concatenate([sim.data.cam_xpos[cid],sim.data.cam_xmat[cid],np.atleast_1d(sim.model.cam_fovy[cid])])
        return 'main256-to224-fixed-v1:'+hashlib.sha256(values.tobytes()).hexdigest()[:20]
