"""Read-only shadow-record compatibility; never decides stage completion or task success."""
import json,os
from pathlib import Path
from types import SimpleNamespace

class MaintainShadow:
 def __init__(self,plan):
  self.plan=plan;self.executor=SimpleNamespace(index=0,transitions=[])
 def observe(self,row):return None
 def stage(self):return dict(index=0,stage=self.plan['stages'][0])
 def snapshot(self,step):
  from sym_contract import COORDS
  return dict(step=step,mode='read-only canonical maintain reference; no intermediate completion controller',index=0,stage=self.plan['stages'][0],oracle_subgoal=self.plan['stages'][0]['grounded'],oracle_prompt=self.plan['task']+'; '+COORDS+'; Current Subgoal: '+self.plan['stages'][0]['grounded'],full_oracle_plan=self.plan['stages'],oracle_full_task=self.plan['task'],completion_scope='D1 final verifier; this record does not assert physical completion')

def install(runner):
 original=runner.ShadowOracle;cache={}
 def factory(env,case,contract,rules,initial,budget):
  path=os.environ['HYBRID_PLANS_FILE']
  if path not in cache:cache[path]=json.loads(Path(path).read_text())
  plan=cache[path][case['case_id']]
  if len(plan['stages'])==1 and plan['stages'][0]['kind']=='maintain':return MaintainShadow(plan)
  return original(env,case,contract,rules,initial,budget)
 runner.ShadowOracle=factory
