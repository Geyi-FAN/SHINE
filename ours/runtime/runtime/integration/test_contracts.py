import copy,dataclasses,sys,unittest
from adapter import *

class Contracts(unittest.TestCase):
 def setUp(self):
  self.i=Identity('e1','t1',1,0,'return_bowl',4);self.obs=Observation(12,100);self.g=StageTickets(self.i);self.body={'model':MODEL};self.t=self.g.issue('verifier',self.body,self.obs)
  self.adapter=F28dExecutionAdapter();self.inp=dict(user_message='Return the bowl, then open the middle drawer',physical_state=dict(source='s1_rgb_proprio_estimates',held_object='unknown'),completed_events=[],reference_availability=[],episode_id='e1',task_version=1,frame=12,mode='test')
 def test_eight_fields_unchanged(self):self.assertEqual(self.adapter.planner_input(self.inp,self.i),self.inp)
 def test_ninth_field_rejected(self):
  with self.assertRaises(ValueError):self.adapter.planner_input(dict(self.inp,original_user_message='old'),self.i)
 def test_qa_preserves_ticket(self):
  self.g.qa();self.assertTrue(self.g.accepts(self.t,115,current_evidence_frame=18)[0])
 def test_pause_drops_late_verifier(self):
  self.g.pause();self.assertFalse(self.g.accepts(self.t,115,current_evidence_frame=18)[0]);self.assertEqual(self.g.identity.semantic_revision,1)
 def test_resume_cannot_reuse_pre_pause_result(self):
  self.g.pause();self.g.resume();self.assertFalse(self.g.accepts(self.t,115,current_evidence_frame=18)[0])
 def test_resume_new_ticket(self):
  self.g.pause();self.g.resume();t=self.g.issue('planning',{},Observation(20,115));self.assertTrue(self.g.accepts(t,116,current_evidence_frame=20)[0])
 def test_new_task_drops_old(self):
  self.g.new_task('t2');self.assertFalse(self.g.accepts(self.t,115,current_evidence_frame=18)[0]);self.assertEqual(self.g.identity.semantic_revision,2)
 def test_reset_drops_previous_episode(self):
  self.g.reset('e2');self.assertFalse(self.g.accepts(self.t,115,current_evidence_frame=18)[0])
 def test_stage_advance_drops_previous_verifier(self):
  self.g.advance('open_middle',16);self.assertFalse(self.g.accepts(self.t,115,current_evidence_frame=18)[0])
 def test_duplicate_commit_blocked(self):
  self.assertTrue(self.g.commit(self.t,115,current_evidence_frame=18)[0]);self.assertFalse(self.g.commit(self.t,116,current_evidence_frame=19)[0])
 def test_old_action_capture_not_receipt(self):self.assertEqual(self.g.accepts(self.t,115,action=True)[1],'stale_action_observation')
 def test_fresh_action(self):self.assertTrue(self.g.accepts(self.t,102,action=True)[0])
 def test_future_capture(self):self.assertFalse(self.g.accepts(self.t,99,action=True)[0])
 def test_verifier_not_blindly_expired_at_3s(self):self.assertTrue(self.g.accepts(self.t,115,current_evidence_frame=18)[0])
 def test_old_verifier_requires_current_corrob(self):self.assertFalse(self.g.accepts(self.t,115)[0])
 def test_contrary_current_evidence_blocks(self):self.assertFalse(self.g.accepts(self.t,115,current_evidence_frame=18,contradicted=True)[0])
 def test_action_capability_absent(self):
  with self.assertRaises(RuntimeError):self.adapter.dispatch_action([1]*7)
 def test_private_nested_fields(self):
  for field in sorted(PRIVATE_KEYS):
   with self.subTest(field=field),self.assertRaises(ValueError):deny_private({'physical_state':{'nested':[{field:True}]}})
 def test_semantic_version_not_control_version(self):
  self.g.pause();self.assertEqual(self.adapter.planner_input(self.inp,self.g.identity)['task_version'],1)
 def test_mismatched_semantic_version_rejected(self):
  with self.assertRaises(ValueError):self.adapter.planner_input(dict(self.inp,task_version=2),self.i)
 def test_unknown_ownership_kept_unknown(self):self.assertEqual(self.adapter.planner_input(self.inp,self.i)['physical_state']['held_object'],'unknown')
 def test_no_unknown_fields(self):
  x=copy.deepcopy(self.inp);x['physical_state']['sneaky_answer']='open_middle'
  with self.assertRaises(ValueError):self.adapter.planner_input(x,self.i)
 def test_cached_not_fresh_completion_evidence(self):
  with self.assertRaises(ValueError):ObservedSceneStateStore().publish(self.inp['physical_state'],self.obs,fresh_detector_points=[dict(frame=8,time_source='current')],resolved_action_references=[])
 def test_cached_action_reference_preserved(self):
  p=ObservedSceneStateStore().publish(self.inp['physical_state'],self.obs,fresh_detector_points=[],resolved_action_references=[dict(frame=8,time_source='current',source='cached')]);self.assertEqual(p['resolved_action_references'][0]['frame'],8)
 def test_sim_truth_state_rejected(self):
  with self.assertRaises(ValueError):ObservedSceneStateStore().publish(dict(source='simulator_physical_facts_v2.5'),self.obs,fresh_detector_points=[],resolved_action_references=[])
 def test_unknown_role_rejected(self):
  with self.assertRaises(ValueError):self.g.issue('oracle',{},self.obs)
 def test_pause_prevents_issue(self):
  self.g.pause()
  with self.assertRaises(ValueError):self.g.issue('planning',{},self.obs)

class References(unittest.TestCase):
 def setUp(self):
  self.ref=dict(time_source='episode_start',entity='bowl',keypoint='K2');self.p=dict(self.ref,yx224=[100.25,99.5],frame=-1,episode_id='e1',camera_transform_id='cam1');self.d=dict(status='plan_ready',reference=self.ref,policy_prompt_template='Return at {episode_start.bowl.K2}')
 def bind(self,p=None,d=None):return bind_policy_reference(self.d if d is None else d,self.p if p is None else p,camera_transform_id='cam1',expected_episode_id='e1')
 def test_historical_point_float_until_final(self):
  text,meta=self.bind();self.assertEqual(meta['yx'],[115,114]);self.assertEqual(meta['source_frame'],-1)
 def test_missing_no_zero_fallback(self):
  with self.assertRaises(ValueError):bind_policy_reference(self.d,None,camera_transform_id='cam1',expected_episode_id='e1')
 def test_no_k_swap(self):
  with self.assertRaises(ValueError):self.bind(dict(self.p,keypoint='K3'))
 def test_no_time_swap(self):
  with self.assertRaises(ValueError):self.bind(dict(self.p,time_source='instruction_takeover'))
 def test_no_object_swap(self):
  with self.assertRaises(ValueError):self.bind(dict(self.p,entity='cheese'))
 def test_no_camera_swap(self):
  with self.assertRaises(ValueError):self.bind(dict(self.p,camera_transform_id='cam2'))
 def test_no_episode_swap(self):
  with self.assertRaises(ValueError):self.bind(dict(self.p,episode_id='e2'))
 def test_nan_not_point(self):
  with self.assertRaises(ValueError):self.bind(dict(self.p,yx224=[float('nan'),0]))
 def test_out_of_image(self):
  with self.assertRaises(ValueError):self.bind(dict(self.p,yx224=[224,0]))
 def test_blocked_cannot_bind(self):
  with self.assertRaises(ValueError):self.bind(d=dict(self.d,status='need_observation'))
 def test_no_point_drawer_unchanged(self):
  text,meta=self.bind(d=dict(status='plan_ready',reference=None,policy_prompt_template='open the middle drawer'));self.assertEqual(text,'open the middle drawer');self.assertIsNone(meta)
 def test_current_valid_static_cache_retains_history_source(self):
  d=dict(self.d,reference=dict(self.ref,time_source='current'),policy_prompt_template='destination {current.bowl.K2}')
  p=dict(self.p,resolution='cached',cache_validated=True,reference_time_source='current')
  _,meta=self.bind(d=d,p=p);self.assertEqual(meta['source_time_source'],'episode_start');self.assertEqual(meta['source_frame'],-1)
 def test_history_without_cache_certificate_not_current(self):
  d=dict(self.d,reference=dict(self.ref,time_source='current'),policy_prompt_template='destination {current.bowl.K2}')
  with self.assertRaises(ValueError):self.bind(d=d)

if __name__=='__main__':unittest.main(verbosity=2)
