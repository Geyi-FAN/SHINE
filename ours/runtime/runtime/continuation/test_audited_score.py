import unittest
from continuation.audited_score import early_control_replies,pause_evidence

class EvidenceAudit(unittest.TestCase):
 def setUp(self):
  self.turn=dict(audio_started_wall=10,audio_ended_wall=13)
  self.receipt=dict(status='accepted',executed=True,state='paused',episode_id='ep',task_id='t',task_version=2)
  self.event=dict(ts=12500,type='realtime.protocol',payload=dict(type='robot.fast_stop',phase='receipt',inputId='input:fast-stop:1',receipt=self.receipt,asr=dict(receivedAt=12490)))
  self.play=dict(direction='sent',type='host.playback_started',time=12.6,receiptKey='["input:fast-stop:1","ep","t",2,"robot_pause"]')
 def test_matching_accepted_early_receipt(self):self.assertEqual(len(early_control_replies(dict(episode_id='ep'),[self.event],[self.play],self.turn,20)),1)
 def test_wrong_episode_cannot_count(self):self.assertFalse(early_control_replies(dict(episode_id='other'),[self.event],[self.play],self.turn,20))
 def test_previous_asr_cannot_count(self):
  self.event['payload']['asr']['receivedAt']=9000
  self.assertFalse(early_control_replies(dict(episode_id='ep'),[self.event],[self.play],self.turn,20))
 def test_rejected_pause_cannot_count(self):
  self.receipt['executed']=False
  self.assertFalse(early_control_replies(dict(episode_id='ep'),[self.event],[self.play],self.turn,20))
 def test_unbound_audio_cannot_count(self):
  self.play['receiptKey']='["previous","ep","t",1,"robot_pause"]'
  self.assertFalse(early_control_replies(dict(episode_id='ep'),[self.event],[self.play],self.turn,20))
 def test_world_advance_while_pose_held_is_failure(self):
  ticks=[dict(mode='paused',time=0,step=1,simulation_time=0,state_hash='a'),dict(mode='paused',time=2,step=2,simulation_time=.05,state_hash='a')]
  self.assertFalse(pause_evidence({},ticks)['passed'])
 def test_fully_frozen_world_passes(self):
  ticks=[dict(mode='paused',time=t,step=1,simulation_time=0,state_hash='a')for t in [0,1,2]]
  self.assertTrue(pause_evidence({},ticks)['passed'])

if __name__=='__main__':unittest.main()
