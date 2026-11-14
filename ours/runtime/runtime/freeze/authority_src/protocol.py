"""Execution termination and independent scoring; no policy prompts/guards are scored."""
from benchmark_metrics import load_rules
from metric_extensions import evaluate_episode
from benchmark_metrics.predicates import drawer_gap
class StopController:
 def __init__(self,case,contract,rules=None):
  self.case=case;self.contract=contract;self.rules=rules or load_rules();self.first_native=None;self.close_streak=0
  self.joint=next((c['joint'] for c in contract['clauses'] if c['kind']=='close_event'),None)
 def observe(self,row):
  step=row['step'];native=bool(row['goal_frame']['goal'])
  if native and self.first_native is None:self.first_native=step
  if self.case['stop_policy']=='first_native_target_or_budget':return 'native_target_reached' if native else None
  if self.case['stop_policy']!='target_then_close_or_budget':raise ValueError(self.case['stop_policy'])
  closed=drawer_gap(row['source']['articulation'][self.joint])<=self.rules['close']['gap_m']
  self.close_streak=self.close_streak+1 if closed else 0
  # Physical end condition independent of permanent Instruction failures.
  # Five closing-confirmation steps must occur after first target success.
  if native and self.first_native is not None and step-self.first_native>=self.rules['close']['confirmation_steps'] and self.close_streak>=self.rules['close']['confirmation_steps']:
   return 'target_and_trailing_close_completed'
  return None

def evidence(env,case,contract):
 import numpy as np
 from libero.libero.envs.predicates.base_predicates import In
 core=env.env;sim=env.sim;out={};site={5:'main_table_stove_front_region',9:'wine_rack_1_top_region'}.get(case['target_task'])
 if site:
  obj='wine_bottle_1' if case['target_task']==9 else 'plate_1';state=core.object_states_dict[site];siteobj=core.object_sites_dict[site];center=np.asarray(sim.data.get_site_xpos(site));M=np.asarray(sim.data.get_site_xmat(site)).reshape(3,3);pos=sim.data.body_xpos[core.obj_body_id[obj]];size=np.asarray(siteobj.size);parent=core.get_object(state.parent_name)
  out['regions']={site:dict(local_position=(M@(pos-center)).tolist(),lower=[-float(size[0]),-float(size[1]),float(size[2]-.005)],upper=[float(size[0]),float(size[1]),float(size[2]+.10)],parent_contact_required=parent is not None,parent_contact=True if parent is None else bool(core.check_contact(parent,core.get_object(obj))))}
 for c in contract['clauses']:
  if c['kind']=='preserve_containment':out.setdefault('containment',{})[c['id']]=bool(In()(core.object_states_dict[c['object']],core.object_states_dict[c['container']]))
  if c['kind']=='preserve_predicate_state':out.setdefault('predicates',{})[c['id']]=bool(core._eval_predicate(c['predicate']))
  if c['kind']=='preserve_relation':out.setdefault('relations',{})[c['id']]=bool(core._eval_predicate(c['relation']))
 return out
