"""Evaluator-only supplement to R6 recorder. Never supplies facts to Agent."""
import json,time,sys
from pathlib import Path
B=Path(__file__).resolve().parents[1]
W=Path(__file__).resolve().parent
sys.path.append(str(B/'freeze/voice'));sys.path.insert(0,str(B/'freeze/voice/robot_gateway'))
from evaluation_recording import EvaluationRecorder
from repair6.recorder import Recorder as OriginalRecorder
class Recorder(OriginalRecorder):
 def __init__(self,root,bridge):
  super().__init__(root,bridge);self.independent=EvaluationRecorder(Path(root)/'recordings',bridge.env);self.last_recorded_step=None;self.last_pause_at=0
  self.pause_file=(Path(root)/'pause_observations.jsonl').open('w')
 def _record(self,phase='passive',owner=None):
  result=super()._record(phase,owner)
  b=self.b;s=b.state
  if self.last_recorded_step!=b.physics_steps:
   self.last_recorded_step=b.physics_steps;s.policy_action=phase in('authorized_kernel_control','source_policy','authorized_native_control')
   s.captured_wall_time=self.last['time'];s.captured_monotonic=self.last['monotonic']
   self.independent.record(s,b.obs)
  return result
 def pause_snapshot(self):
  b=self.b;s=b.state;now=time.monotonic()
  if s.mode!='paused'or now-self.last_pause_at<.1:return
  self.last_pause_at=now
  row=dict(time=time.time(),monotonic=now,episode_id=s.episode,task_id=s.task_id,version=s.version,mode=s.mode,physics_step=b.physics_steps,control_step=b.control_steps,simulation_time=float(b.env.sim.data.time),physical_state_sha256=b.state_hash(),held_object=self.independent.observer.snapshot.get('held_object'),source='read_only_pause_sample_no_env_step')
  self.pause_file.write(json.dumps(row)+'\n');self.pause_file.flush()
 def close(self):
  self.independent.close();self.pause_file.close();super().close()
