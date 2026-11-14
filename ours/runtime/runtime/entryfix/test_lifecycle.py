import unittest
from types import SimpleNamespace as NS
from entryfix.lifecycle import install,patch_loop
class Lifecycle(unittest.TestCase):
 def cls(self):
  class C:
   def __init__(self):self.task='old';self.state=NS(task_id='old');self.started=0;self.events=[]
   def start(self,*a,**kw):self.started+=1
   def install_hooks(self):pass
   def log(self,*a,**kw):self.events.append((a,kw))
  install(C);return C
 def test_retired_old_source_cannot_restart_under_new_task(self):
  b=self.cls()();b.state.task_id='new';b.start(None,resume=True);self.assertEqual(b.started,0);self.assertEqual(b.events[0][0][0],'old_kernel_restart_suppressed')
 def test_same_task_resume_is_preserved(self):
  b=self.cls()();b.start(None,resume=True);self.assertEqual(b.started,1)
 def test_authorized_new_activation_can_start(self):
  b=self.cls()();b.task=b.state.task_id='new';b.start(None,resume=True);self.assertEqual(b.started,1)
 def test_loop_never_enters_old_symbolic_resume_branch(self):
  s=patch_loop("elif b.route=='symbolic'and b.task:\n pass");self.assertIn('state.task_id==b.task',s)
 def test_takeover_refreshes_on_task_change_but_not_same_task_resume(self):
  b=self.cls()();p=NS(scene=NS(frame=1),memory={'episode_start':'original','instruction_takeover':'old'},captures=0)
  def evidence(f,*_):p.scene.frame=f
  p.update_evidence=evidence
  def begin(point,image,frame):point.captures+=1;point.memory['instruction_takeover']=image
  b.points_class=NS(begin_instruction=begin);b.cache_reader=NS(memory_evidence=lambda:{},memory_camera_id=lambda:'cam');b.runner=NS(Points=lambda *a,**kw:p);b.engine_start_step=2;b.token=lambda:('ep',b.state.task_id,1,99)
  b.install_hooks();q=b.runner.Points();q.begin_instruction('first',2);q.begin_instruction('resume',2);self.assertEqual(p.captures,1);self.assertEqual(p.memory['episode_start'],'original')
  b.state.task_id='new';b.engine_start_step=3;q.begin_instruction('new',3);self.assertEqual(p.captures,2);self.assertEqual(p.memory['instruction_takeover'],'new');self.assertEqual(p.memory['episode_start'],'original')
if __name__=='__main__':unittest.main()
