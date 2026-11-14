"""One physical owner; goals compiled from the accepted task, not case labels.

Same file is used by the next audio round and the deployable service.
"""
import runpy,sys
from pathlib import Path
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B))
source=runpy.run_path(str(B/'repair/gateway.py'),run_name='live_source')['source']
def replace(old,new):
 global source
 assert source.count(old)==1,(old[:80],source.count(old));source=source.replace(old,new)
replace('from repair.completion import install as install_completion','from continuation.terminal.completion_r4 import install as install_completion')
replace(' def contract(target,revision=False):\n  clauses=[];', " objective_context=[None]\n def contract(target,revision=False):\n  if objective_context[0]is not None:return dict(case_id=case['case_id'],clauses=objective_context[0].clauses,budget=spec.get('task_control_budget',1200))\n  clauses=[];")
replace("  b.case.update(public_user_instruction=state.instruction,instruction=state.instruction,current_instruction=state.instruction,instruction_original=state.instruction)","  previous_instruction=b.case.get('public_user_instruction','');previous_target=b.case.get('target_task',0)\n  b.case.update(kind='normal'if b.task_count==1 else'revision',public_user_instruction=state.instruction,instruction=state.instruction,current_instruction=state.instruction,instruction_original=state.instruction,previous_instruction=previous_instruction,source_task=previous_target)")
old="  source=b.task_count==1 and bool(spec.get('context_turns'));target=spec.get('source_task',1)if source else spec.get('target_task',0)\n  if target is None:target=0\n  b.return_only=bool(not source and spec.get('return_only'));b.completion_gate=None\n  b.custom_goal_predicate=spec.get('custom_goal_predicate')if not source else None"
new="""  source=b.task_count==1 and bool(spec.get('context_turns'))
  from continuation.live.objectives import compile_objective,UnsupportedObjective,OBJECT_TASK
  current={name:value['position']for name,value in rt.monitor(env,0).measure()['all_object_poses'].items()}
  try:objective=compile_objective(state.instruction,xyz,current,b.source.measure()['articulation'],case['case_id'],previous_instruction=previous_instruction)
  except UnsupportedObjective as error:
   b.scoring_active=False;b.live_objective_error=str(error);state.failure_detail=dict(code='unsupported_current_goal_verifier',detail=str(error),recovery='完整要求未被删除；当前终验尚不能可靠覆盖该表达，需要澄清或补充支持。');state._hold('needs_review','unsupported_current_goal_verifier');b.log('current_goal_verifier_rejected',reason=str(error));return
  objective_context[0]=objective;target=objective.target_task
  b.return_only=objective.return_only;b.completion_gate=None;b.live_close_only=objective.close_only;b.live_open_only=objective.open_only;b.custom_goal_predicate=objective.custom_predicate
  if objective.restore_object:b.source=rt.monitor(env,OBJECT_TASK[objective.restore_object])
  from continuation.live.scoped_score import score as current_score
  b.score=lambda:current_score(b)
"""
replace(old,new)
# Extend the final goal only; this never creates a drawer-closing subgoal.
# Compilation/insertion is explicit in the candidate module, no frozen edit.
replace("while not b.stopping and time.monotonic()-started<1600:", "while not b.stopping and(spec.get('serve_live')or time.monotonic()-started<1600):")
# Startup is not an authorized task; no physical goal can complete it.
replace("b.audit=Recorder(a.out,b);b.audit.record()", "b.audit=Recorder(a.out,b);b.scoring_active=False;b.audit.record()")
replace("VOICE_ROBOT_DATA_DIR=str(a.out/'gateway')", "VOICE_ROBOT_DATA_DIR=spec.get('state_directory',str(a.out/'gateway'))")
replace("state.reset_count=1;state.mode='loading'", "state.reset_count=spec.get('reset_count',1);state.version=spec.get('initial_version',0);state.mode='loading'")
source=source.replace('F28d_G22_G3','F28d_R4_live').replace('F28d_G3','F28d_R4_live')
# Production exposes the normal authenticated API, not private evaluator facts.
replace("server=http.GatewayHTTPServer(('127.0.0.1',a.port),Handler)", "server=http.GatewayHTTPServer(('127.0.0.1',a.port),http.Handler if spec.get('serve_live')else Handler)")
replace("  b.close();archive();b.audit.close();env.close();server.shutdown()", "  if state.reset_pending:state.event('episode_ended',dict(reason='operator_reset_process_handoff'))\n  b.close();archive();b.audit.close();env.close();server.shutdown()")
replace("self.pose=PoseHold(self.obs,self.env.env.robots[0].controller)", "self.pose=PoseHold(self.obs,self.env.env.robots[0].controller)\n    self.state.agent_execution['source']='current_selected_instruction_physical_supervisor'")
if __name__=='__main__':exec(compile(source,str(B/'continuation/generated_live_gateway.py'),'exec'),dict(__name__='__main__',__file__=str(B/'continuation/live_gateway.py')))
