"""Only allowlisted observations and Agent-selected stage verdicts cross to LLM."""
import copy
ALLOWED_STATE={'episode_id','task_id','version','mode','instruction','robot_state','step','current_stage','completed_events','deferred_task','pending_proposal','pending_clarification'}
ALLOWED_STAGE={'operation','status','entered_step','confirmed_step','task_id','version'}
FORBIDDEN={'native_goal_relations','all_object_poses','private_contract','private_judge','required_invariants','target_task_id','source_task_id','standard_subgoal','oracle_next_stage','next_stage_answer'}
def stage_event(event):return {k:copy.deepcopy(v)for k,v in event.items()if k in ALLOWED_STAGE}
def public_state(state):
 result={k:copy.deepcopy(v)for k,v in state.items()if k in ALLOWED_STATE}
 result['completed_events']=[stage_event(e)for e in result.get('completed_events',[])]
 if result.get('current_stage'):result['current_stage']=stage_event(result['current_stage'])
 assert_clean(result);return result
def assert_clean(x):
 if isinstance(x,dict):
  bad=set(x)&FORBIDDEN
  if bad:raise ValueError('Privileged fields crossed Oracle boundary: '+str(sorted(bad)))
  for v in x.values():assert_clean(v)
 elif isinstance(x,list):
  for v in x:assert_clean(v)
