import copy,json,gzip,tempfile,unittest
from pathlib import Path
from repair6.reference.container_support import derive,PAIR
class ContainerContact(unittest.TestCase):
 def tick(self,contact=False):return dict(task_id='T',step=3,physical={'native_goal_relations':{'cheese_bowl':True}},measurements={'cheese':{'support_contact':False,**({'object_object_contacts':[{'objects':PAIR,'penetration':.0001}]}if contact else{})}})
 def test_exact_logged_contact_adds_support_without_mutating_original(self):
  with tempfile.TemporaryDirectory()as directory:
   d=Path(directory);(d/'tasks/T').mkdir(parents=True)
   with gzip.open(d/'tasks/T/trace.json.gz','wt')as f:json.dump({'measurements':[dict(world_physics_step=3,target={'object_object_contacts':[{'objects':PAIR,'penetration':.0001}]})]},f)
   original=self.tick();out,audit=derive([original],d);self.assertFalse(original['measurements']['cheese']['support_contact']);self.assertTrue(out[0]['measurements']['cheese']['support_contact']);self.assertFalse(out[0]['measurements']['cheese']['support_contact_raw']);self.assertEqual(audit['derived_frames'],1)
 def test_unknown_contact_never_becomes_support(self):
  with tempfile.TemporaryDirectory()as d:
   out,audit=derive([self.tick()],Path(d));self.assertFalse(out[0]['measurements']['cheese']['support_contact']);self.assertEqual(audit['derived_frames'],0)
 def test_contact_outside_container_not_enough(self):
  t=self.tick(True);t['physical']['native_goal_relations']['cheese_bowl']=False
  with tempfile.TemporaryDirectory()as d:self.assertFalse(derive([t],Path(d))[0][0]['measurements']['cheese']['support_contact'])
if __name__=='__main__':unittest.main()
