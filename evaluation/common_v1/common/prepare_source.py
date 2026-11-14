"""Same preregistered T3 source actions/endpoint for every method, after real U0.

No reference controls count as method VLA actions. This module has no audio
transcripts/answers to inject and exposes no planner tool.
"""
import hashlib,json,sys,time
from pathlib import Path
import numpy as np
B=Path('/mnt/disk_4/geyi/audio_switch_benchmark')
BANK=B/'deployments/our_t3_prepared_judge_20261109/data/T3-controlled-source-prefix-v2-20261109'
RUNTIME=B/'deployments/ours_full930_readiness_20261114/code/runtime_v8/runtime'
sys.path[:0]=[str(RUNTIME/'continuation'),str(RUNTIME/'freeze/authority_src')]
from t3_source_window import reached
class SourcePreparer:
 def __init__(self,b):
  self.b=b;self.done=False;self.active=False;self.index=0;self.key=str(b.spec['source_task'])+'_'+b.spec['phase'];self.folder=BANK/self.key
  self.meta=json.loads((self.folder/'PREFIX.json').read_text())
  assert {k:v['sha256']for k,v in b.spec['fixture']['assets'].items()}=={k:v['sha256']for k,v in self.meta['fixture']['assets'].items()}
  assert b.spec['fixture']['scene_seed']==self.meta['fixture']['scene_seed']
  data=(self.folder/'actions.jsonl').read_bytes();assert hashlib.sha256(data).hexdigest()==self.meta['actions_sha256'];self.actions=[json.loads(x)['action']for x in data.splitlines()]
  assert len(self.actions)==self.meta['steps']
 def service(self):
  b=self.b;s=b.state
  if self.done or b.task_count!=1 or not s.task_id:return False
  if s.mode not in ['running','verifying']:return False
  if not self.active:
   from live.objectives import compile_objective
   goal=compile_objective(s.instruction,b.case['initial_xyz'],b.case['initial_xyz'],b.last['measurements']['bowl']['articulation'])
   if goal.target_task!=b.spec['source_task']:
    self.done=True;(b.root/'SOURCE_PREPARATION.json').write_text(json.dumps(dict(passed=False,reason='actual_U0_source_goal_mismatch',source_U0_precedes_preparation=True))+'\n');return False
   self.active=True;self.source_id=s.task_id;self.started=time.time();b.buffer=[]
  assert s.task_id==self.source_id,'source identity changed during preparation'
  for _ in range(6):
   if self.index==len(self.actions):break
   # 'policy_actions' is the historical generic control counter. The action
   # provenance flag remains False; independent source checks count references.
   b.control_steps+=1;b.apply(np.asarray(self.actions[self.index]),'T3_private_fixed_preparation_not_method_actions');self.index+=1
  if self.index==len(self.actions):
   from sim_state import capture,identity
   actual=identity(capture(b.env))
   sample=dict(b.last,policy_actions=self.index)
   valid=actual==self.meta['state_identity']and reached(sample,b.spec,self.source_id,b.initial_stove)
   proof=dict(passed=bool(valid),steps=self.index,source_key=self.key,actual_state_identity=actual,original_T3_predicate_passed=bool(valid),no_switch_audio_during_setup=True,source_U0_precedes_preparation=True,memory_from_actual_RGB=False,private_preparer_not_Agent_execution=True,seconds=time.time()-self.started)
   (b.root/'SOURCE_PREPARATION.json').write_text(json.dumps(proof,indent=2)+'\n')
   assert valid,'controlled source endpoint identity or physical predicate mismatch'
   self.done=True;self.active=False;b.task_start_control=b.control_steps;b.task_started=time.monotonic();b.freeze_fixture('common_registered_T3_reference_endpoint');b.publish()
  return True
