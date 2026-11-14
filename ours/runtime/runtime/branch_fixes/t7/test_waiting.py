import json,sys,types
from pathlib import Path
A=Path(__file__).parent;B=A.parent
sys.path[:0]=[str(A),str(B/'freeze/voice/robot_gateway')]
import waiting_contract as fixed
cases=json.loads(Path('/mnt/disk_2/geyi/t7_c3r_goal10_20261103/data/cases.private.json').read_text())
for c in cases:assert fixed.deferred_request(c['turns'][1]['text']),c['case_id']
negative=["Don't wait. Turn on the stove.",'Turn on the stove now.','After lunch, turn on the stove.','If the bowl is down, put the cheese in the bowl.','When the bowl is not down, put the cheese in the bowl.','Turn on the stove once you are done?']
for t in negative:assert fixed.deferred_request(t)is None,t
assert fixed.deferred_update_request('Cancel the bowl task. Keep going.','put the bowl on the stove')
assert not fixed.deferred_update_request('Cancel the cheese task. Keep going.','turn on the stove')
assert fixed.deferred_request('Put the bowl on the plate afterward instead.',replacing='push the plate')=='Put the bowl on the plate'
# Pending source is actual per-process state, never a benchmark answer.
import waiting_runtime,task_contract
class State:
 def __init__(self):self.deferred_task={'instruction':'put the cream cheese in the bowl'}
core=types.SimpleNamespace(RobotState=State);waiting_runtime.install(core);state=core.RobotState()
assert task_contract.deferred_update_request('Cancel the cheese task. Keep going.')
state.deferred_task={'instruction':'turn on the stove'}
assert not task_contract.deferred_update_request('Cancel the cheese task. Keep going.')
print('Waiting tests passed: ten original requests, six negatives, named pending binding, replacement, runtime state isolation')
