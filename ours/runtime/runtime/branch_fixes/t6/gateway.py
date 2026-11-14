"""T6 observations/gates on the shared C3r owner; no second simulator."""
import runpy
import sys
from pathlib import Path

B = Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102')
A = Path(__file__).resolve().parent
sys.path[:0] = [str(A), str(B)]
source = runpy.run_path(str(B/'c3r/gateway.py'), run_name='t6_c3r_parent')['source']

def replace(old, new):
    global source
    assert source.count(old) == 1, old
    source = source.replace(old, new)

replace(" core,runner,authority=configure(a.out,a.gpu)",
        " core,runner,authority=configure(a.out,a.gpu)\n sys.path.insert(0,"+repr(str(A))+")")
replace(" # Preserve episode memory across new tasks; only a new semantic task renews takeover.",
        " from t6_eval import Evaluator\n t6=Evaluator(b,state,spec,a.out)\n # Preserve episode memory across new tasks; only a new semantic task renews takeover.")
replace(" class Native(NativeExecution):",
        " from native_prefetch.scheduler import NativePrefetchMixin\n class Native(NativePrefetchMixin,NativeExecution):")
replace("result['execution_kernel']='C3r';",
        "result['execution_kernel']='C3r';result['native_scheduler']='prefetch-frame-aligned-v1';result['t6_evaluation_adapter']='MV20-real-physics-gate-clocked-v2';result['scene_inventory']=None;")
replace("  return receipt\n state.command=command",
        "  if isinstance(receipt,dict) and isinstance(receipt.get('qa_evidence'),dict):receipt['qa_evidence']['drawer_facts']=None\n  return receipt\n state.command=command")
replace("  def do_GET(self):\n   if self.path=='/evaluator/inspect':",
        "  def do_GET(self):\n   if self.path=='/evaluator/t6':\n    if not self.authenticated():return self.respond(401,{'error':'authentication_required'})\n    return self.respond(200,t6.query({'op':'inspect'}))\n   if self.path=='/evaluator/inspect':")
replace("  def do_POST(self):\n   if self.path in('/evaluator/release_window','/evaluator/hold'):",
        "  def do_POST(self):\n   if self.path=='/eval/t6':\n    if not self.authenticated():return self.respond(401,{'error':'authentication_required'})\n    try:\n     body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))));return self.respond(200,t6.query(body))\n    except Exception as error:return self.respond(409,{'error':str(error)})\n   if self.path in('/evaluator/release_window','/evaluator/hold'):")
replace("   if b.fixture_hold and state.task_id==b.task and state.mode=='running'and now>=tick:",
        "   if t6.pending and now>=tick:\n    if t6.service():tick=time.monotonic()+.05\n    if now-last_image>.2:jpeg();last_image=now\n    time.sleep(.002);continue\n   if b.fixture_hold and state.task_id==b.task and state.mode=='running'and now>=tick:")

replace("    stepped=b.pump(now>=tick)\n    if stepped:tick=time.monotonic()+.05",
        "    stepped=b.pump(now>=tick)\n    from terminal_observation import tick as terminal_hold_tick\n    if not stepped:stepped=terminal_hold_tick(b,state,now>=tick)\n    if stepped:tick=time.monotonic()+.05")

if __name__ == '__main__':
    exec(compile(source, str(A/'generated_gateway.py'), 'exec'),
         dict(__name__='__main__', __file__=str(B/'c3r/gateway.py')))
