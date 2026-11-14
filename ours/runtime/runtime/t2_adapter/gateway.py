"""Full shared C3r/prefetch child plus the prior read-only T2 evaluator recorder."""
import runpy
import sys
from pathlib import Path

B = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(B))
source = runpy.run_path(str(B/'native_prefetch/gateway.py'), run_name='t2_parent')['source']
old = 'from repair6.recorder import Recorder'
assert source.count(old) == 1
source = source.replace(old, 'from t2_adapter.recorder import Recorder')
old = '   now=time.monotonic()'
assert source.count(old) == 1
source = source.replace(old, old + '''
   if state.mode=='paused':b.audit.pause_snapshot()
   budget_path=a.out/'budget.json'
   if state.mode=='running'and budget_path.exists():
    budget=json.loads(budget_path.read_text())
    if now>budget['original_goal_deadline_monotonic']:state._hold('budget_exhausted','T2_original_600s_goal_budget_no_resume_extension')''')
if __name__ == '__main__':
    exec(compile(source, str(B/'t2_adapter/generated_gateway.py'), 'exec'),
         dict(__name__='__main__', __file__=str(B/'c3r/gateway.py')))
