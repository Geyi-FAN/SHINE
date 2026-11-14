"""Consume verified FULL-task feedback, not a missing symbolic stage monitor.

No object pose, detector, grasp label or next-task answer is read here. The
existing full-contract supervisor and 40 real-physics receipt window must have
accepted THIS task. RobotState still owns cancellation/version/queue guards.
"""
def ready(state,decision,subject):
    execution=state.agent_execution or {}
    receipt=execution.get('completion_receipt')or{}
    return bool(state.mode=='completed' and state.completion_status=='verified'
        and execution.get('completion_current_verified')is True
        and decision and decision.get('accepted')is True
        and tuple(decision.get('subject',[]))==tuple(subject)
        and receipt.get('source')=='current_supervisor_verification_each_real_physics_frame'
        and receipt.get('required_physics_frames')==40
        and receipt.get('ready')is True
        and receipt.get('consecutive_verified_physics_frames',0)>=40)
