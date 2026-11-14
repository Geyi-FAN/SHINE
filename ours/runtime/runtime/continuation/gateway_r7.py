"""R6 core plus same-task, explicitly authorized budget continuation."""
import runpy,sys
from pathlib import Path
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B))
source=runpy.run_path(str(B/'repair6/gateway.py'),run_name='r7_source')['source']
anchor=' install_release(SingleOwnerBridge)';assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n from continuation.dispatched_policy_index import install as install_dispatch_index\n install_dispatch_index(SingleOwnerBridge)')
anchor=' install_waiting_prefetch(b,state)';assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n from continuation.authorized_resume import install as install_authorized_resume\n install_authorized_resume(b,state,spec)')
anchor='b.task_count+=1;b.task_start_control=b.control_steps;';assert source.count(anchor)==1
source=source.replace(anchor,'b.task_count+=1;from continuation.authorized_resume import new_task;new_task(b);b.task_start_control=b.control_steps;')
anchor="b.control_steps-b.task_start_control>=spec.get('task_control_budget',1200) or now-b.task_started>900";assert source.count(anchor)==1
source=source.replace(anchor,'b.control_steps-b.task_start_control>=b.live_control_limit or now-b.task_started>b.live_wall_allowance_s')
anchor="   if state.task_id==b.task and state.mode=='running'and(b.control_steps-b.task_start_control>=b.live_control_limit or now-b.task_started>b.live_wall_allowance_s):state._hold('budget_exhausted','G3_shared_1200_control_or_900_wall_budget')"
assert source.count(anchor)==1
source=source.replace(anchor,"   with state.lock:\n "+anchor)
anchor="result=bind_execution(result);result['note']=";assert source.count(anchor)==1
source=source.replace(anchor,"result=bind_execution(result);result['execution_budget']=dict(authorized_control_steps=max(0,b.control_steps-b.task_start_control),control_limit=b.live_control_limit,base_control_allowance=b.live_base_control_budget,scope='current_task_cumulative; only explicit exhausted resume extends allowance');result['note']=")
if __name__=='__main__':exec(compile(source,str(B/'continuation/generated_gateway_r7.py'),'exec'),dict(__name__='__main__',__file__=str(B/'continuation/gateway_r7.py')))
