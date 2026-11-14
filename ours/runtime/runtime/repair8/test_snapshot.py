import hashlib,os,tempfile,unittest
from pathlib import Path
from repair8.qa_snapshot import score
class SnapshotQueries(unittest.TestCase):
 def check(self,question,episode='ep'):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'qa_frames';p.mkdir();f=p/'image.jpg';f.write_bytes(b'actual-captured-image');os.utime(f,(10,10));h=hashlib.sha256(f.read_bytes()).hexdigest()
   voice=[dict(type='visual.analysis',ts=11000,payload=dict(event='visual.evidence',question=question,episodeId=episode,taskId='visual:1',observationTime=10)),dict(type='visual.analysis',ts=10500,payload=dict(event='robot_visual.request',taskId='visual:1',image_sha256=h))]
   tick=dict(time=10,physical=dict(held_object='bowl',native_goal_relations=dict(bowl_stove=False),objects=dict(bowl=dict(robot_contact=True))))
   return score(d,dict(episode_id='ep'),voice,[tick],dict(text='Where is the bowl right now?',audio_started_wall=9),'画面中碗仍在夹爪中，悬于炉灶上方。',12)
 def test_equivalent_enriched_query(self):self.assertEqual(self.check('Where is the bowl right now? Is it on the stove, plate, or elsewhere?')[0],'pass')
 def test_other_object_not_substituted(self):self.assertEqual(self.check('Where is the cheese?')[0],'unknown')
 def test_other_episode_not_substituted(self):self.assertEqual(self.check('Where is the bowl?',episode='old')[0],'unknown')
if __name__=='__main__':unittest.main()
