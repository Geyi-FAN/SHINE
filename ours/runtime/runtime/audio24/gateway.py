"""Instrument frozen G22 without editing its execution/Agent implementations.

Only additions: private observations, fixture-window release,40-physics-tick
benchmark hold. No new stage decision, point, motion policy or public GT tool.
"""
import sys
from pathlib import Path
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B))
source=(B/'g22/gateway.py').read_text()
old="return super().apply(action,'source_policy'if phase=='authorized_native_control'else phase)"
new="""owner=(self.state.task_id,self.state.version)
   result=super().apply(action,'source_policy'if phase=='authorized_native_control'else phase)
   if hasattr(self,'audit'):self.audit.record(phase,owner)
   return result"""
assert source.count(old)==1;source=source.replace(old,new)
needle="b.saved_points.initialize_episode(actual,b.cache_reader.memory_evidence(),b.cache_reader.memory_camera_id())"
source=source.replace(needle,needle+"\n from audio24.recorder import Recorder\n b.audit=Recorder(a.out,b);b.audit.record()")
needle="   if self.path=='/evaluator/status':"
source=source.replace(needle,"""   if self.path=='/evaluator/inspect':
    if not self.authenticated():return self.respond(401,{'error':'authentication_required'})
    # Only the owner publishes this immutable dict. The monitor never acquires
    # either simulation lock and never touches MuJoCo from an HTTP thread.
    sample=b.audit.last
    return self.respond(200,dict(sample=sample,physics_step=sample['step'],control_step=sample['policy_actions'],task_elapsed_s=time.monotonic()-b.task_started if b.task_started else 0,simulation_time=sample['simulation_time'],physical_state_sha256=sample['state_hash'],mode=sample['mode'],task_id=sample['task_id'],task_count=b.task_count,fixture_hold=b.fixture_hold,source_phase_reached=b.source_phase_streak>=3,hold_remaining=b.audit.hold_remaining,route=b.route,kernel_error=b.kernel_error))
"""+needle)
needle="   if self.path=='/evaluator/finish':"
source=source.replace(needle,"""   if self.path in('/evaluator/release_window','/evaluator/hold'):
    if not self.authenticated():return self.respond(401,{'error':'authentication_required'})
    with state.lock:
     if self.path.endswith('release_window'):b.fixture_hold=False;b.log('evaluator_fixture_window_released',not_a_user_command=True)
     else:
      if state.mode=='paused':return self.respond(409,{'error':'explicit_pause_forbids_env_step'})
      b.audit.hold_remaining=40;b.log('evaluator_terminal_hold_requested',physics_ticks=40,not_stage_completion=True)
    return self.respond(200,{'accepted':True})
"""+needle)
needle="   now=time.monotonic()\n   if state.task_id!=b.task"
source=source.replace(needle,"""   now=time.monotonic()
   if b.audit.hold_remaining and now>=tick and state.mode!='paused':
    with state.lock:
     if b.env_lock.acquire(blocking=False):
      try:b.apply(b.pose.action(b.obs),'evaluator_terminal_hold');b.audit.hold_remaining-=1;tick=time.monotonic()+.05
      finally:b.env_lock.release()
    time.sleep(.002);continue
   if b.env_lock.acquire(blocking=False):
    try:b.audit.passive()
    finally:b.env_lock.release()
   if state.task_id!=b.task""")
# Terminal hold is an evaluator observation, never an authorized policy action.
source=source.replace("if phase=='authorized_native_control'else phase)","if phase=='authorized_native_control'else 'async_wait_hold'if phase=='evaluator_terminal_hold'else phase)")
source=source.replace("b.close();archive();env.close();server.shutdown()","b.close();archive();b.audit.close();env.close();server.shutdown()")
assert '/evaluator/inspect'in source and 'Recorder(a.out,b)'in source and 'b.audit.passive()'in source
if __name__=='__main__':exec(compile(source,str(B/'g22/gateway.py'),'exec'),dict(__name__='__main__',__file__=str(B/'audio24/gateway.py')))
