"""Opt-in evaluator-only recording. Never provides expected answers to the Agent."""
import json,subprocess,time,os
from pathlib import Path
import numpy as np

class EvaluationRecorder:
    def __init__(self, root, env):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.env=env;self.episode=None;self.writer=None;self.f=None;self.last=0
        self.tick_file=None
    def record(self,state,obs):
        if self.episode!=state.episode:
            self.close();self.episode=state.episode;directory=self.root/state.episode;directory.mkdir(exist_ok=True)
            self.f=(directory/'observations.jsonl').open('a')
            if os.environ.get('VOICE_BENCHMARK_TICK_LOG')=='1':
                self.tick_file=(directory/'control_ticks.jsonl').open('a')
            self.writer=subprocess.Popen(['ffmpeg','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','512x256','-r','5','-i','-','-an','-c:v','libx264','-threads','1','-preset','ultrafast','-crf','25','-pix_fmt','yuv420p',str(directory/'environment.mp4')],stdin=subprocess.PIPE)
            from hybrid_planner.completion import Completion
            initial={n:self.env.sim.data.body_xpos[self.env.env.obj_body_id[n]].tolist() for n in ('akita_black_bowl_1','cream_cheese_1','wine_bottle_1','plate_1')}
            self.observer=Completion(self.env,initial,0,'')
        # Independent observer, no selected/next Oracle stage. Every physical tick
        # maintains the same v2.5 release windows; results remain scorer-only.
        self.observer.observe(state.step)
        if self.tick_file:
            # Additional evaluator-only relations for the 96-case development
            # suite; never returned through planner/status or used as a plan.
            extra={}
            try:extra['cheese_stove']=bool(self.env.env._eval_predicate(['on','cream_cheese_1','flat_stove_1_cook_region']))
            except (KeyError,ValueError,AttributeError):extra['cheese_stove']=None
            try:
                sim=self.env.sim;cabinet=int(self.env.env.obj_body_id['wooden_cabinet_1'])
                bodies=set()
                for bid in range(sim.model.nbody):
                    parent=bid
                    while parent>0 and parent!=cabinet:parent=int(sim.model.body_parentid[parent])
                    if parent==cabinet:bodies.add(bid)
                geoms={g for g in range(sim.model.ngeom) if int(sim.model.geom_bodyid[g]) in bodies}
                robot=self.observer.mon['bowl'].robot_geoms
                extra['cabinet_robot_contact']=any(c.dist<=.001 and ((int(c.geom1) in geoms and int(c.geom2) in robot) or (int(c.geom2) in geoms and int(c.geom1) in robot)) for c in sim.data.contact[:sim.data.ncon])
            except (KeyError,ValueError,AttributeError):extra['cabinet_robot_contact']=None
            try:
                sim=self.env.sim;stove=int(self.env.env.obj_body_id['flat_stove_1'])
                bodies=set()
                for bid in range(sim.model.nbody):
                    parent=bid
                    while parent>0 and parent!=stove:parent=int(sim.model.body_parentid[parent])
                    if parent==stove:bodies.add(bid)
                geoms={g for g in range(sim.model.ngeom) if int(sim.model.geom_bodyid[g]) in bodies}
                robot=self.observer.mon['bowl'].robot_geoms
                extra['stove_robot_contact']=any(c.dist<=.001 and ((int(c.geom1) in geoms and int(c.geom2) in robot) or (int(c.geom2) in geoms and int(c.geom1) in robot)) for c in sim.data.contact[:sim.data.ncon])
            except (KeyError,ValueError,AttributeError):extra['stove_robot_contact']=None
            # Evaluator-only causal evidence. Never fed to planner/status/YOLO.
            tick=dict(time=getattr(state,"captured_wall_time",time.time()),monotonic=getattr(state,"captured_monotonic",time.monotonic()),episode_id=state.episode,
                      step=state.step,task_id=state.task_id,version=state.version,mode=state.mode,evaluator_extra=extra,
                      policy_action=bool(getattr(state,'policy_action',False)),
                      policy_actions=state.action_steps,physical=self.observer.snapshot,
                      measurements={obj:{k:value for k,value in measured.items() if k in (
                          'object_position','object_quaternion_wxyz','eef_position','target_contact',
                          'support_contact','articulation')} for obj,measured in self.observer.latest_rows.items()},
                      episode_initial_positions=self.observer.initial_xyz,
                      proprioception={k:obs[k].tolist() for k in ('robot0_eef_pos','robot0_eef_quat','robot0_gripper_qpos')})
            self.tick_file.write(json.dumps(tick,default=lambda x:x.tolist() if hasattr(x,'tolist') else x.item())+'\n')
            self.tick_file.flush()
        if time.monotonic()-self.last<.2:return
        self.last=time.monotonic()
        from benchmark_metrics.events import restore_window
        released={}
        for obj,window in self.observer.windows.items():
            rows=list(window)
            if rows:
                clause=dict(object=obj,reference_position=rows[-1]['object_position'],stable_required=True,withdraw_required=False)
                released[obj]=bool(restore_window(rows,clause,1e6,self.observer.rules)['complete'])
        # Evaluator-only pose evidence for offline invariant/return scoring.
        # This opt-in file is never part of status, planner or policy inputs.
        poses={name:dict(position=row['object_position'],quaternion_wxyz=row['object_quaternion_wxyz'])
               for name,row in self.observer.latest_rows.items()}
        self.f.write(json.dumps(dict(time=getattr(state,"captured_wall_time",time.time()),episode_id=state.episode,step=state.step,task_id=state.task_id,version=state.version,mode=state.mode,instruction=state.instruction,completion=state.completion_status,policy_actions=state.action_steps,physical=self.observer.snapshot,stable_release=released,evaluator_only_poses=poses))+'\n');self.f.flush()
        frame=np.concatenate([obs['agentview_image'][::-1,::-1],obs['robot0_eye_in_hand_image'][::-1,::-1]],axis=1)
        self.writer.stdin.write(np.ascontiguousarray(frame,dtype=np.uint8).tobytes())
    def close(self):
        if self.writer:
            self.writer.stdin.close();self.writer.wait(timeout=15);self.writer=None
        if self.f:self.f.close();self.f=None
        if self.tick_file:self.tick_file.close();self.tick_file=None
