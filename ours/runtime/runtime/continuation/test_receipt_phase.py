import unittest
from continuation.reference.receipt_phase import resume_receipt_consistent
class ReceiptPhase(unittest.TestCase):
 def setUp(self):
  self.tools=[dict(kind='voice_tool_receipt',tool='robot_resume',time=1.,receipt={'status':'accepted','state':'running','task_id':'t'})]
  self.events=[dict(kind='task_resumed',time=1.)]
  self.ticks=[dict(task_id='t',physics_tick=False,mode='paused',time=.98),dict(task_id='t',physics_tick=True,mode='running',time=1.1)]
 def test_ack_before_next_tick_is_not_false_resume(self):self.assertTrue(resume_receipt_consistent(1.05,'t',self.tools,self.events,self.ticks))
 def test_no_accepted_tool_no_evidence(self):self.assertFalse(resume_receipt_consistent(1.05,'t',[],self.events,self.ticks))
 def test_old_subject_does_not_authorize_new_task(self):self.assertFalse(resume_receipt_consistent(1.05,'other',self.tools,self.events,self.ticks))
 def test_stopped_again_cannot_claim_running(self):
  self.events.append(dict(kind='task_paused',time=1.02));self.assertFalse(resume_receipt_consistent(1.05,'t',self.tools,self.events,self.ticks))
 def test_no_actual_world_resume_does_not_pass(self):self.assertFalse(resume_receipt_consistent(1.05,'t',self.tools,self.events,self.ticks[:1]))
if __name__=='__main__':unittest.main()
