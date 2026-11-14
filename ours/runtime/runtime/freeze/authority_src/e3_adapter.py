"""Confirmed pi05 V4 controller, renderer and verbatim grounding in the frozen simulator."""
import ast
import copy
import json
import sys
from pathlib import Path
import numpy as np
B=Path(__file__).resolve().parents[1]
R=B.parents[1]
SOURCE=Path(json.loads((R/'run_config.json').read_text())['model_repository'])
sys.path.insert(0,str(SOURCE/'src'))
from e3v4.benchmark_execution.agent_aligned import OnlineAgentAligned
from e3v4.benchmark_execution.legacy_boundary_geometry import LegacyPhysicalObserver
from e3v4.benchmark_execution.skill_catalog import identify_stage,render_prompt
import common
_grounder_class=None

def published_grounder():
 global _grounder_class
 if _grounder_class is None:
  # Original pure definitions, avoiding its training-only runtime path rewrites.
  import mujoco
  contract=ast.parse((SOURCE/'src/sym_contract.py').read_text())
  constants={node.targets[0].id:ast.literal_eval(node.value) for node in contract.body
   if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ['OBJECTS','ROLES']}
  original=ast.parse((SOURCE/'src/sym_geometry.py').read_text())
  nodes=[node for node in original.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in ['project','Grounder']]
  namespace=dict(np=np,mujoco=mujoco,GeometryRuntime=common.suite_runtime,**constants,OBJ_ROLES=dict(zip(constants['OBJECTS'],constants['ROLES'][:4])))
  exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE/'src/sym_geometry.py'),'exec'),namespace)
  _grounder_class=namespace['Grounder']
 return _grounder_class

class E3Adapter:
 def __init__(self,env,case,obs,measurement,native):
  self.plan=copy.deepcopy(json.loads((B/'helper_plans.json').read_text())[case['case_id']])
  assert self.plan['execution_version']=='agent_aligned_v4_20261028'
  for stage in self.plan['stages']:identify_stage(stage)
  returns=[s for s in self.plan['stages'] if s['kind']=='return']
  self.plan['restore_object']=returns[0]['object'] if returns else None
  self.plan['source_object']=self.plan['restore_object']
  self.grounder=published_grounder()(env,self.plan,include_handles=False)
  self.observer=LegacyPhysicalObserver(env,self.plan)
  self.online=OnlineAgentAligned(self.plan,self.evidence(measurement,native),start_step=0)
 def evidence(self,measurement,native):
  state=np.zeros(8,np.float64);state[6]=measurement['gripper_gap']
  return self.observer.measure(measurement,state,bool(native))
 def prompt(self):
  points,valid,counts,world=self.grounder.points();valid=valid.copy();valid[4:6]=False
  stage=self.plan['stages'][self.online.index];skill=identify_stage(stage)
  text=render_prompt(self.plan['task'],{'template_id':skill['template_id']},points,valid)
  return text,dict(stage=self.online.index,template_id=skill['template_id'],points_main224=points.tolist(),valid=valid.tolist(),simulator_gt=True,
   visual_arrows=False,drawer_handle_gt=False,coordinates='MAIN224 <y,x>',source='confirmed_pi05_E3_V4_616')
 def advance(self,obs,measurement,native,step,queue):
  return self.online.after_action(self.evidence(measurement,native),step,queue)
