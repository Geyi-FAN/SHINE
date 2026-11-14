"""Preserve a task, extend exhausted budget only after an actual user resume.

No new instruction/plan/point/action or automatic retry is generated. Ordinary
pause/resume retains the original remaining budget. Duplicate receipts cannot
grant an extension. Model-internal generation retries remain bounded.
"""
import time
def initialize(b,spec):
 b.live_base_control_budget=spec.get('task_control_budget',1200)
 b.live_control_limit=b.live_base_control_budget
 b.live_wall_allowance_s=900

def new_task(b):
 b.live_control_limit=b.live_base_control_budget
 b.live_wall_allowance_s=900

def install(b,state,spec):
 initialize(b,spec);original=state.command
 def command(name,args,request_id):
  with state.lock:
   before=(state.mode,state.task_id,state.version,state.task_intent_revision)
   receipt=original(name,args,request_id)
   real_resume=(name=='robot_resume' and receipt.get('status')=='accepted' and receipt.get('executed') is True and state.mode=='running' and state.task_id==before[1] and state.task_intent_revision==before[3] and state.version!=before[2])
   if real_resume:
    b.restart_count=0  # A distinct authorized resume is not an internal retry.
    if before[0]=='budget_exhausted':
     used=b.control_steps-b.task_start_control
     b.live_control_limit=used+b.live_base_control_budget
     b.live_wall_allowance_s=time.monotonic()-b.task_started+900
     state.event('task_budget_extended',dict(control_steps_already_used=used,new_control_limit=b.live_control_limit,added_control_budget=b.live_base_control_budget,reason='explicit_accepted_resume',task_id=state.task_id))
     b.log('explicit_resume_budget_extended',consumed=used,limit=b.live_control_limit,task_id=state.task_id)
   return receipt
 state.command=command
