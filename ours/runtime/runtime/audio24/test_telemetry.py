"""The HTTP observer must return an owner-published sample without simulator locks."""
import types,unittest
from audio24.gateway import source
class Forbidden:
 def __getattribute__(self,name):raise AssertionError('Observer touched state/simulator/lock: '+name)
class TestTelemetry(unittest.TestCase):
 def test_read_only_http_does_not_lock_or_touch_simulator(self):
  text=source[source.index(' class Handler(http.Handler):'):source.index(' server=http.GatewayHTTPServer')];text='\n'.join(line[1:]for line in text.splitlines())
  sample=dict(step=31,policy_actions=8,simulation_time=1.55,state_hash='published',mode='paused',task_id='task')
  b=types.SimpleNamespace(audit=types.SimpleNamespace(last=sample,hold_remaining=0),task_started=0,task_count=1,fixture_hold=False,source_phase_streak=0,route='native',kernel_error=None,env_lock=Forbidden())
  scope=dict(http=types.SimpleNamespace(Handler=object),b=b,state=Forbidden(),env=Forbidden(),time=Forbidden());exec(text,scope)
  handler=scope['Handler']();handler.path='/evaluator/inspect';handler.authenticated=lambda:True;handler.respond=lambda code,body:(code,body)
  code,body=handler.do_GET();self.assertEqual(code,200);self.assertIs(body['sample'],sample);self.assertEqual(body['physics_step'],31);self.assertEqual(body['mode'],'paused');self.assertEqual(body['physical_state_sha256'],'published')
if __name__=='__main__':unittest.main()
