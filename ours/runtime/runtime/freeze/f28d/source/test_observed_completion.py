import unittest
from observed_completion import ObservedCompletion,Settings

def point(e,k,xy,**kw):return dict(entity=e,keypoint=k,yx224=xy,det_confidence=.99,keypoint_confidence=.99,source='yolo_image_only',**kw)
def obs(m,t,points=(),width=.08,eef=(0,0,1),yx=(50,50)):
 return m.observe(t,list(eef),[width/2,-width/2],list(yx),list(points))
def history(e='bowl',xy=(100,100)):return {('episode_start',e,'K2'):point(e,'K2',list(xy))}
def stage(op='return_bowl',kind='return',obj='bowl'):return dict(operation=op,kind=kind,object=obj)
class TestCompletion(unittest.TestCase):
 def test_open_empty_gripper_not_grasp(self):
  m=ObservedCompletion();obs(m,0);m.select(stage('grasp_bowl','grasp'))
  for t in range(3,40,3):self.assertIsNone(obs(m,t,eef=(0,0,1+t*.01)))
 def test_closed_empty_hand_lift_not_grasp(self):
  m=ObservedCompletion();obs(m,0,width=.01);m.select(stage('grasp_bowl','grasp'))
  for t in range(3,40,3):self.assertIsNone(obs(m,t,width=.01,eef=(0,0,1+t*.01)))
 def test_static_object_under_moving_hand_not_grasp(self):
  m=ObservedCompletion();ps=[point('bowl','K1',[60,50])];obs(m,0,ps,width=.03);m.select(stage('grasp_bowl','grasp'))
  for t in range(3,22,3):self.assertIsNone(obs(m,t,ps,width=.03,eef=(0,0,1+t*.01),yx=(50-t,50)))
 def test_correct_comotion_grasp(self):
  m=ObservedCompletion();obs(m,0,[point('bowl','K1',[60,50])],width=.03);m.select(stage('grasp_bowl','grasp'));events=[]
  for t in range(3,25,3):
   ev=obs(m,t,[point('bowl','K1',[60-t,50])],width=.03,eef=(0,0,1+t*.01),yx=(50-t,50))
   if ev:events.append(ev)
  self.assertEqual(len(events),1)
 def test_wrong_object_motion_not_grasp(self):
  m=ObservedCompletion();obs(m,0);m.select(stage('grasp_bowl','grasp'))
  for t in range(3,25,3):self.assertIsNone(obs(m,t,[point('cheese','K1',[60-t,50])],width=.03,eef=(0,0,1+t*.01),yx=(50-t,50)))
 def test_history_alone_does_not_return(self):
  m=ObservedCompletion(history());obs(m,0);m.select(stage())
  for t in range(3,30,3):self.assertIsNone(obs(m,t))
 def test_return_requires_release(self):
  m=ObservedCompletion(history());ps=[point('bowl','K1',[100,100]),point('bowl','K2',[100,100])];obs(m,0,ps,width=.03);m.select(stage())
  for t in range(3,30,3):self.assertIsNone(obs(m,t,ps,width=.03))
 def test_stable_return_and_single_event(self):
  m=ObservedCompletion(history());ps=[point('bowl','K1',[100,100]),point('bowl','K2',[100,100])];obs(m,0,ps);m.select(stage());events=[]
  for t in range(3,25,3):
   ev=obs(m,t,ps)
   if ev:events.append(ev)
  self.assertEqual(len(events),1);self.assertEqual(events[0]['confirmed_step'],9)
 def test_moving_object_does_not_return(self):
  m=ObservedCompletion(history());obs(m,0);m.select(stage())
  for t in range(3,25,3):self.assertIsNone(obs(m,t,[point('bowl','K1',[100,100]),point('bowl','K2',[100+(t%2)*12,100])]))
 def test_cached_current_rejected(self):
  m=ObservedCompletion()
  with self.assertRaises(ValueError):obs(m,3,[point('bowl','K2',[100,100],frame=0)])
 def test_noncausal_rejected(self):
  m=ObservedCompletion();obs(m,3)
  with self.assertRaises(ValueError):obs(m,2)
 def test_placement_requires_current_object(self):
  m=ObservedCompletion({('episode_start','stove_placement','K3'):point('stove_placement','K3',[100,100])});obs(m,0);m.select(stage('bowl_stove','target'))
  for t in range(3,25,3):self.assertIsNone(obs(m,t))
 def test_placement(self):
  m=ObservedCompletion();ps=[point('bowl','K1',[100,100]),point('bowl','K2',[100,100]),point('stove_placement','K3',[100,100])];obs(m,0,ps);m.select(stage('bowl_stove','target'));ev=None
  for t in (3,6,9):ev=obs(m,t,ps)
  self.assertEqual(ev['operation'],'bowl_stove')
 def test_takeover_distinct_from_initial(self):
  h=history();h[('instruction_takeover','bowl','K2')]=point('bowl','K2',[150,150]);m=ObservedCompletion(h)
  ps=[point('bowl','K1',[100,100]),point('bowl','K2',[100,100])];obs(m,0,ps);m.select(stage('release_bowl','release'))
  for t in (3,6,9,12):self.assertIsNone(obs(m,t,ps))
 def test_low_confidence_rejected(self):
  m=ObservedCompletion(history());obs(m,0);m.select(stage());p=point('bowl','K2',[100,100]);p['keypoint_confidence']=.1
  for t in (3,6,9,12):self.assertIsNone(obs(m,t,[p,point('bowl','K1',[100,100])]))
if __name__=='__main__':unittest.main()
