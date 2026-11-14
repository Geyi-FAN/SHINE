"""Private T4 evidence, current C3r owner; never supplied as Agent state."""
import copy,time
from hold_gate import PoseHold
from repair6.recorder import Recorder as Parent
from t4_private_evidence import TickRecorder,source_ready

class Recorder(Parent):
 def __init__(self,root,bridge):
  super().__init__(root,bridge);self.bridge=bridge
  self.spec=bridge.t4_spec;self.last_physics=None;self.terminal_subject=None;self.publication_sequence=0
  bridge.source_window_ready=False;bridge.t4_terminal_ticks=0
  self.tick=TickRecorder(bridge,bridge.case['initial_xyz'],self.spec);bridge.t4_recorder=self.tick
  self._record('initial_observation')
 def _record(self,phase='passive',owner=None):
  result=super()._record(phase,owner);b=self.bridge
  if self.last_physics!=b.physics_steps:
   self.last_physics=b.physics_steps;self.tick.record(phase,stepped=phase!='initial_observation')
   if phase=='evaluator_terminal_hold':b.t4_terminal_ticks+=1
   if b.task_count==1 and not b.fixture_used and source_ready(self.tick.recent,self.spec):
    b.pose=PoseHold(b.obs,b.env.env.robots[0].controller)
    b.fixture_hold=True;b.fixture_used=True;b.source_window_ready=True;b.source_phase_streak=5
    b.state.queue.clear()
    if b.native:b.native.invalidate(b.state)
    b.log('T4_common_fixture_observation_window',phase=self.spec['phase'],source_predicate='unchanged_Easy10',not_a_user_command=True)
  if b.task_count>=2 and b.state.mode in ('completed','needs_review','budget_exhausted','cancelled','error') and self.terminal_subject!=b.state.task_id:
   self.terminal_subject=b.state.task_id;self.hold_remaining=40;b.t4_terminal_ticks=0
   b.pose=PoseHold(b.obs,b.env.env.robots[0].controller)
  self.publication_sequence+=1
  self.publication=dict(episode_id=b.state.episode,task_version=b.state.version,task_intent_revision=b.state.task_intent_revision,
   publication_sequence=self.publication_sequence,source_window=source_ready(self.tick.recent,self.spec,retained=True),source_window_ready=b.source_window_ready,
   terminal_hold_ticks=b.t4_terminal_ticks,physics_step=b.physics_steps,control_step=b.control_steps,simulation_time=float(b.env.sim.data.time),
   physical_state_sha256=b.state_hash(),fixture_hold=b.fixture_hold,task_count=b.task_count,task_control_steps=b.control_steps-b.task_start_control,
   io_role=None if b.io is None else b.io['role'],source_phase_reached=b.source_window_ready,task_id=b.state.task_id,mode=b.state.mode,published_monotonic=time.monotonic())
  return result
 def close(self):
  self.tick.stream.close();super().close()
