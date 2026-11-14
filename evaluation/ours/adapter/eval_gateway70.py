"""Shared frozen C3r core plus private benchmark setup/observation endpoints.
No private evaluator facts or labels are given to any planning/audio model.
"""
from pathlib import Path
import sys,hashlib,os
R=Path(__file__).resolve().parents[1]
W=Path(os.environ['C3R_RUNTIME_ROOT'])
source=(W/'runtime/unified/gateway.py').read_text()
def replace(old,new):
 global source
 if source.count(old)!=1:raise RuntimeError(('evaluation composition anchor',old[:80],source.count(old)))
 source=source.replace(old,new)
replace(' core,runner,authority=configure(a.out,a.gpu)'," core,runner,authority=configure(a.out,a.gpu)\n sys.path.insert(0,"+repr(str(R/'adapter/evaluator_v2'))+")")
replace(' from repair6.recorder import Recorder'," from repair6.recorder import Recorder\n if spec.get('evaluation_family')=='T4':\n  from t4_private_recorder import Recorder\n  b.t4_spec=spec\n if spec.get('evaluation_family')=='T2':\n  from t2_private_recorder import Recorder\n if spec.get('evaluation_family')=='T3':\n  from t3_private_recorder import Recorder")
replace(" # Preserve episode memory across new tasks; only a new semantic task renews takeover."," t6=None\n if spec.get('evaluation_family')=='T6':\n  from t6_eval import Evaluator\n  t6=Evaluator(b,state,spec,a.out)\n # Preserve episode memory across new tasks; only a new semantic task renews takeover.")
replace('   now=time.monotonic()', "   now=time.monotonic()\n   from source_handoff import tick as source_handoff_tick\n   if source_handoff_tick(b,state,spec,now>=tick):tick=time.monotonic()+.05;continue\n   if spec.get('evaluation_family')=='T2':\n    if state.mode=='paused':b.audit.pause_snapshot()\n    budget_path=a.out/'budget.json'\n    if state.mode=='running' and budget_path.exists():\n     budget=json.loads(budget_path.read_text())\n     if now>budget['original_goal_deadline_monotonic']:state._hold('budget_exhausted','T2_original_600s_goal_budget_no_resume_extension')")
replace("result['execution_kernel']='C3r';", "result['execution_kernel']='C3r';result['t4_evaluation_adapter']='Easy10-original-causal-fixture-v1' if spec.get('evaluation_family')=='T4' else None;result['t6_evaluation_adapter']='MV20-real-physics-gate-clocked-v2' if t6 else None;")
replace("  def do_GET(self):\n   if self.path=='/evaluator/inspect':", "  def do_GET(self):\n   if self.path=='/evaluator/t6' and t6:\n    if not self.authenticated():return self.respond(401,{'error':'authentication_required'})\n    return self.respond(200,t6.query({'op':'inspect'}))\n   if self.path=='/evaluator/inspect':")
replace("  def do_POST(self):\n   if self.path in('/evaluator/release_window','/evaluator/hold'):", "  def do_POST(self):\n   if self.path=='/eval/t6' and t6:\n    if not self.authenticated():return self.respond(401,{'error':'authentication_required'})\n    try:\n     body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))));return self.respond(200,t6.query(body))\n    except Exception as error:return self.respond(409,{'error':str(error)})\n   if self.path=='/evaluator/pause' and spec.get('evaluation_family')=='T4':\n    if not self.authenticated():return self.respond(401,{'error':'authentication_required'})\n    if not b.source_window_ready:return self.respond(409,{'error':'source_window_not_reached'})\n    from source_handoff import fixture_pause\n    return self.respond(200,fixture_pause(b))\n   if self.path in('/evaluator/release_window','/evaluator/hold'):")
anchor='    return self.respond(200,dict(physics_step='
start=source.index(anchor);end=source.index('\n',start)
source=source[:start]+"    if spec.get('evaluation_family')=='T4':return self.respond(200,copy.deepcopy(b.audit.publication))\n"+source[start:]
replace("   if b.fixture_hold and state.task_id==b.task and state.mode=='running'and now>=tick:", "   if t6 and t6.pending and now>=tick:\n    if t6.service():tick=time.monotonic()+.05\n    if now-last_image>.2:jpeg();last_image=now\n    time.sleep(.002);continue\n   if state.mode=='paused' and spec.get('evaluation_family')=='T4' and now-getattr(b,'_pause_publication',0)>.1:\n    b.audit._record('paused_publication_no_physics');b._pause_publication=now\n   if b.fixture_hold and state.task_id==b.task and state.mode=='running'and now>=tick:")
# The T4 recorder uses the unchanged typed source predicates; remove the older
# Native-only generic bowl gate for this evaluator family only.
start=source.index("        if b.task_count==1 and spec.get('phase')and b.native:")
end=source.index('     finally:b.env_lock.release()',start)
block=source[start:end]
source=source[:start]+block.replace("spec.get('phase')and b.native", "spec.get('phase')and b.native and spec.get('evaluation_family')!='T4'")+source[end:]
if __name__=='__main__':
 exec(compile(source,str(R/'adapter/generated_eval_gateway.py'),'exec'),dict(__name__='__main__',__file__=str(W/'runtime/unified/gateway.py')))
