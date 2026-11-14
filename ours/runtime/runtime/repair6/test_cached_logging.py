import json,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from repair6.cached_logging import install
class OwnerOnlyLogging(unittest.TestCase):
 def test_no_simulator_access_or_live_counter_mixing(self):
  with tempfile.TemporaryDirectory()as d:
   class Bridge:
    @property
    def env(self):raise AssertionError('logger must not access simulator')
   b=Bridge();b.root=Path(d);b.log_lock=threading.Lock();b.physics_steps=999;b.audit=SimpleNamespace(last=dict(step=10,policy_actions=3,simulation_time=.5,sample=17));install(b);b.log('voice_tool_receipt',task_id='new')
   r=json.loads((b.root/'gateway.jsonl').read_text());self.assertEqual(r['physics_step'],10);self.assertEqual(r['task_id'],'new');self.assertEqual(r['simulation_sample_id'],17)
if __name__=='__main__':unittest.main()
