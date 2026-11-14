"""Additional task-contract probes. Private benchmark only; no evidence goes to Agent."""
from collections import deque
from copy import deepcopy
import numpy as np
from benchmark_metrics.events import restore_window

def prerequisite_order(measurements):
 first=next((m['step'] for m in measurements if m.get('metric_evidence',{}).get('probe_prerequisite',{}).get('ready')),None)
 target=next((m['step'] for m in measurements if m.get('adjusted_goal',m['goal_frame']['goal'])),None)
 return dict(passed=first is not None and target is not None and first<target,prerequisite_first=first,target_first=target)

def install(runner):
 original_run=runner.run;original_evidence=runner.metric_evidence;original_evaluate=runner.evaluate_episode;OriginalTerminal=runner.SwitchTerminal
 active={}
 def run(case,*args,**kwargs):
  active.clear();active.update(case=case,monitor=None,window=deque(maxlen=5),rt=runner.GeometryRuntime(),rules=runner.load_rules());return original_run(case,*args,**kwargs)
 def evidence(env,case,contract):
  out=original_evidence(env,case,contract);task=case['probe_prerequisite_task']
  if active['monitor'] is None:active['monitor']=active['rt'].monitor(env,task)
  row=active['monitor'].measure();active['window'].append(row);goal=bool(active['rt'].goals(env,task));w=list(active['window'])
  if task==5:
   other=dict(case,target_task=5);ev=original_evidence(env,other,contract)
   for site,e in ev.get('regions',{}).items():goal=goal or bool(runner.region_contains(e,active['rules']['target_regions'][site]['margin_m']))
   stable=len(w)==5 and np.max(np.linalg.norm(np.asarray([r['object_position'] for r in w])[:,None]-np.asarray([r['object_position'] for r in w])[None,:],axis=-1))<=.005
   ready=goal and stable
  else:
   clause=dict(reference_position=row['object_position'],release_required=True,stable_required=True,withdraw_required=False)
   ready=goal and restore_window(w,clause,1e6,active['rules'])['complete']
  out['probe_prerequisite']=dict(task_id=task,ready=bool(ready),native_goal=goal)
  return out
 def evaluate(trace,case,contract,rules=None):
  score=original_evaluate(trace,case,contract,rules);order=prerequisite_order(trace['measurements']);score['probe_order']=order;score['contract_extension']='D1-P012-compositional-v1'
  for key in ('instruction_adjusted','instruction_native'):
   x=score[key];x['success']=x['success'] is True and order['passed'];x['clauses_at_evaluation_step']['probe_prerequisite_order']=dict(value=order['passed'],reason_code=None if order['passed'] else 'PREREQUISITE_OR_ORDER_NOT_SATISFIED',reason_zh='先前放置/推盘必须稳定完成，再完成最终抽屉目标')
   x['status']='pass' if x['success'] else 'fail'
   if not x['success']:x['first_step']=None
  return score
 class Terminal(OriginalTerminal):
  def check(self,measurements,decision):
   out=super().check(measurements,decision);guard=prerequisite_order(measurements);out['probe_order']=guard;out['passed']=out['passed'] and guard['passed'];return out
 runner.run=run;runner.metric_evidence=evidence;runner.evaluate_episode=evaluate;runner.SwitchTerminal=Terminal
