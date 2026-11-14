import unittest,tempfile,copy
from pathlib import Path
from scene_memory import SceneMemory
from points import Points
from test_scene_memory import point,facts

def reusable(static=False,delta=0):
 f=facts(static,delta);f['bowl']['cache_reusable']=True;return f

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=SceneMemory(Path(self.tmp.name)/'events',episode_id='ep');self.s.evidence(0,reusable(),'cam')
 def tearDown(self):self.tmp.cleanup()
 def seed(self,pts=None,f=None,camera='cam',episode='ep',frame=-1):
  self.s.import_episode_objects(pts if pts is not None else [point(k='K1')],f if f is not None else reusable(),'cam' if camera is None else camera,episode,frame)
 def test_cold_start_has_history_without_faking_five_frames(self):
  self.seed();p,status=self.s.resolve('bowl','K1');self.assertEqual((p['frame'],p['time_source'],status),(-1,'episode_start','cached'));self.assertFalse(self.s.facts['bowl']['static'])
 def test_missing_current_reuses_initial_same_slot(self):
  self.seed();self.s.evidence(3,reusable(delta=.0005),'cam');self.s.ingest([],3);self.assertEqual(self.s.resolve('bowl','K1')[0]['frame'],-1);self.assertEqual(self.s.resolve('bowl','K3')[1],'missing')
 def test_moved_object_is_not_imported(self):
  self.s.evidence(0,reusable(delta=.02),'cam');self.seed();self.assertEqual(self.s.resolve('bowl','K1')[1],'missing')
 def test_current_grasp_or_support_loss_rejects(self):
  f=reusable();f['bowl']['cache_reusable']=False;self.s.evidence(0,f,'cam');self.seed();self.assertEqual(self.s.resolve('bowl','K1')[1],'missing')
 def test_initial_grasp_or_support_loss_rejects(self):
  f=reusable();f['bowl']['cache_reusable']=False;self.seed(f=f);self.assertEqual(self.s.resolve('bowl','K1')[1],'missing')
 def test_missing_pose_evidence_rejects(self):
  self.seed(f={});self.assertEqual(self.s.resolve('bowl','K1')[1],'missing')
 def test_wrong_episode_rejects(self):
  self.seed(episode='other');self.assertEqual(self.s.resolve('bowl','K1')[1],'missing')
 def test_wrong_camera_rejects(self):
  self.seed(camera='other');self.assertEqual(self.s.resolve('bowl','K1')[1],'missing')
 def test_low_confidence_rejects(self):
  p=point(k='K1');p['keypoint_confidence']=.49;self.seed([p]);self.assertEqual(self.s.resolve('bowl','K1')[1],'missing')
 def test_only_object_k1_k3_are_imported(self):
  self.seed([point(k='K2'),point('middle_handle','K1'),point('stove_button','K1')]);self.assertFalse(self.s.cache)
 def test_invalidated_history_cannot_be_repeatedly_reimported(self):
  self.seed();self.s.evidence(1,reusable(delta=.02),'cam');self.assertEqual(self.s.resolve('bowl','K1')[1],'missing');self.s.evidence(2,reusable(),'cam');self.seed();self.assertEqual(self.s.resolve('bowl','K1')[1],'missing')
 def test_disabled_history_import(self):
  self.s.transfer_enabled=False;self.seed();self.assertEqual(self.s.resolve('bowl','K1')[1],'missing')
 def test_future_history_rejected(self):
  with self.assertRaises(ValueError):self.seed(frame=1)
 def test_early_pixel_jump_checked_without_five_frame_window(self):
  self.seed();self.s.ingest([point(k='K1',xy=(130,100))],0);self.assertEqual(self.s.resolve('bowl','K1')[1],'cached')
 def test_instruction_switch_keeps_scene_and_initial_target(self):
  self.seed();p=object.__new__(Points);p.scene=self.s;p.episode_id='ep';p.instruction_version=0;p.memory={('episode_start','bowl','K2'):{'yx224':[10,20]},('instruction_takeover','bowl','K2'):{'yx224':[30,40]}};p.history_camera={'episode_start':'cam','instruction_takeover':'cam'}
  calls=[];p.observe=lambda im,frame,source:calls.append((frame,source));p.begin_instruction(None,0)
  self.assertIn(('episode_start','bowl','K2'),p.memory);self.assertNotIn(('instruction_takeover','bowl','K2'),p.memory);self.assertEqual(p.scene.resolve('bowl','K1')[1],'cached');self.assertEqual(calls,[(0,'instruction_takeover')]);self.assertEqual(p.instruction_version,1)
 def test_changed_camera_prevents_fixed_initial_anchor(self):
  self.s.seed_episode([point('stove_button','K1')],camera='other');self.assertFalse(self.s.anchors)
 def test_history_age_uses_episode_clock_not_switch_sentinel(self):
  self.seed();self.s.evidence(3,reusable(),'cam');self.s.ingest([],3)
  p=object.__new__(Points);p.scene=self.s;p.frame=3;p.camera_id='cam';p.episode_frame_at_takeover=89
  decision=dict(reference=dict(time_source='current',entity='bowl',keypoint='K1'),policy_prompt_template='grasp at {current.bowl.K1}',remaining_plan=[dict(kind='grasp')])
  _,marker=p.bind(decision,3);self.assertEqual(marker['age_steps'],92);self.assertEqual(marker['age_clock'],'episode');self.assertEqual(marker['source_episode_frame'],0)
 def test_live_initialization_preserves_initial_object_point(self):
  p=object.__new__(Points);p.scene=self.s;p.episode_id='ep';p.history_camera={};p.memory={};p.episode_frame_at_takeover=None
  def observe(image,frame,source,camera_id=None):
   p.history_camera[source]=camera_id;p.memory[(source,'bowl','K1')]=dict(point(k='K1'),frame=frame,time_source=source)
  p.observe=observe;p.initialize_episode(None,reusable(),'cam')
  self.assertEqual(p.episode_frame_at_takeover,0);self.assertEqual(p.scene.resolve('bowl','K1')[1],'cached')
  with self.assertRaises(ValueError):p.initialize_episode(None,reusable(),'cam')

if __name__=='__main__':unittest.main()
