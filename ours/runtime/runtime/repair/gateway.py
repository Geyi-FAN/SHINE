"""Candidate integration; unchanged agents, action model and points."""
import sys
from pathlib import Path
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B))
# Reuse the read-only recorder/instrumentation, then make explicit guarded
# integration edits. Every anchor must occur exactly once.
scope={'__name__':'repair_source','__file__':str(B/'audio24/gateway.py')}
exec(compile((B/'audio24/gateway.py').read_text(),scope['__file__'],'exec'),scope)
source=scope['source'].replace('from audio24.recorder import Recorder','from repair.recorder import Recorder')
def replace(old,new):
 global source
 assert source.count(old)==1,(old[:90],source.count(old));source=source.replace(old,new)
replace(' core,runner,authority=configure(a.out,a.gpu)', ' core,runner,authority=configure(a.out,a.gpu)\n from repair.wording_guard import install as install_wording_guard\n install_wording_guard()')
replace(' install_release(SingleOwnerBridge)',' install_release(SingleOwnerBridge)\n from repair.completion import install as install_completion\n install_completion(SingleOwnerBridge)')
replace("  clauses.append(clause(id='target',kind='native_target',task_id=target))","  clauses.append(clause(id='target',kind='native_target',task_id=target,goal_kind='return_released_only'if revision and spec.get('return_only')else'libero_native'))")
replace("  if revision and spec.get('restore'):clauses.append(clause(id='order_restore_target',kind='completion_order',before='restore',after='target'))","  if revision and spec.get('restore')and not spec.get('return_only'):clauses.append(clause(id='order_restore_target',kind='completion_order',before='restore',after='target'))")
replace("  b.case['target_task']=target;b.target=rt.monitor(env,target);", "  b.return_only=bool(not source and spec.get('return_only'));b.completion_gate=None\n  b.case['target_task']=target;b.target=rt.monitor(env,target);")
start=source.index('   if not b.native_goal_hold:',source.index(' class Native('));end=source.index('\n def archive():',start)
source=source[:start]+"   self._status(state,'target_candidate_waiting_for_release_and_current_acceptance')\n"+source[end:]
replace("   if b.audit.hold_remaining and now>=tick and state.mode!='paused':", "   gate=getattr(b,'completion_gate',None)\n   if gate and gate.holding and tuple(gate.subject)==b.token()[:3]and state.mode=='running'and now>=tick:\n    with state.lock:\n     if b.env_lock.acquire(blocking=False):\n      try:b.apply(b.pose.action(b.obs),'async_wait_hold');tick=time.monotonic()+.05\n      finally:b.env_lock.release()\n    time.sleep(.002);continue\n   if b.audit.hold_remaining and now>=tick and state.mode!='paused':")
replace("   now=time.monotonic()\n   gate=getattr(b,'completion_gate',None)", "   now=time.monotonic()\n   if http.priority_stop_enabled:http.priority_stop.drain(state.command)\n   gate=getattr(b,'completion_gate',None)")
replace("   if state.mode=='completed'and state.completion_status=='verified'and b.route=='symbolic':", "   if state.mode=='completed'and state.completion_status=='verified':")
# A reusable controlled observation window for the expanded task family.
replace("   gate=getattr(b,'completion_gate',None)", """   if spec.get('held_source_entity')and b.task_count==spec.get('source_window_task_count',1)and state.mode=='running'and not b.fixture_used:
    entity=spec['held_source_entity'];facts=b.cache_reader.snapshot
    if getattr(b,'fixture_checked_physics',-1)!=b.physics_steps:
     b.fixture_checked_physics=b.physics_steps
     b.source_phase_streak=b.source_phase_streak+1 if facts['held_object']==entity and not facts['objects'][entity]['supported']else 0
    if b.source_phase_streak>=3:
     from hold_gate import PoseHold
     b.pose=PoseHold(b.obs,env.env.robots[0].controller);b.fixture_hold=True;b.fixture_used=True;state.queue.clear()
     if b.native:b.native.invalidate(state)
     b.log('controlled_source_window_latched',entity=entity,world_clock_continues=True)
   if b.fixture_hold and state.task_id==b.task and state.mode=='running'and now>=tick:
    with state.lock:
     if b.env_lock.acquire(blocking=False):
      try:b.apply(b.pose.action(b.obs),'async_wait_hold');tick=time.monotonic()+.05
      finally:b.env_lock.release()
    time.sleep(.002);continue
   gate=getattr(b,'completion_gate',None)""")
replace("  b.case['target_task']=target;b.target=rt.monitor(env,target);", "  b.custom_goal_predicate=spec.get('custom_goal_predicate')if not source else None\n  b.case['target_task']=target;b.target=rt.monitor(env,target);")
# Do not combine a predecessor's immutable sample with live successor metadata.
replace("task_elapsed_s=time.monotonic()-b.task_started if b.task_started else 0", "task_elapsed_s=time.monotonic()-sample['task_started']if sample['task_started']else 0")
replace("task_count=b.task_count,fixture_hold=b.fixture_hold,source_phase_reached=b.source_phase_streak>=3,hold_remaining=b.audit.hold_remaining,route=b.route,kernel_error=b.kernel_error", "task_count=sample['task_count'],fixture_hold=sample['fixture_hold'],source_phase_reached=sample['source_phase_reached'],hold_remaining=sample['hold_remaining'],route=sample['route'],kernel_error=sample['kernel_error']")
replace("b.log('g3_task_activated',task_id=b.task,route=b.route,instruction=state.instruction)", "b.log('g3_task_activated',task_id=b.task,route=b.route,instruction=state.instruction)\n  b.audit.record()")
# Keep current camera views live during asynchronous physical settling too.
assert source.count('    time.sleep(.002);continue')==3
source=source.replace('    time.sleep(.002);continue','    if now-last_image>.2:jpeg();last_image=now\n    time.sleep(.002);continue')
start=source.index("    return self.respond(200,dict(sample=sample,")
end=source.index('\n',start)
source=source[:start]+"    from repair.telemetry import inspect as inspect_snapshot\n    return self.respond(200,inspect_snapshot(sample))"+source[end:]
if __name__=='__main__':exec(compile(source,str(B/'repair/generated_gateway.py'),'exec'),dict(__name__='__main__',__file__=str(B/'repair/gateway.py')))
