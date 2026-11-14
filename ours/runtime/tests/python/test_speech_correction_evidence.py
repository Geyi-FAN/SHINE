import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime/freeze/voice/robot_gateway'))
from core import RobotState, TaskError
from grounding import ENTITIES, inventory_from_names


class SpeechCorrectionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=RobotState(self.tmp.name)
        self.s.ready=True;self.s.mode='idle';self.seq=0
        self.s.scene_inventory=inventory_from_names(v[0] for v in ENTITIES.values())

    def tearDown(self):
        self.s.db.close();self.tmp.cleanup()

    def say(self,text,identifier):
        return self.s.record_interaction(dict(episode_id=self.s.episode,task_version=self.s.version,text=text,input_id=identifier))

    def cmd(self,name,**args):
        self.seq+=1
        return self.s.command(name,dict(episode_id=self.s.episode,expected_task_version=self.s.version,**args),'req'+str(self.seq))

    def context(self):
        return self.cmd('robot_get_status')['dialogue_evidence']['correction_context']

    def pair(self):
        self.say('请你帮我打开泸州。','u1');self.say('炉灶。','u2')
        self.assertEqual(self.context()['correction_input_ids'],['u1','u2'])

    def test_current_correction_binds_user_action_and_has_no_automatic_motion(self):
        self.pair();self.assertIsNone(self.s.task_id)
        result=self.cmd('robot_start_task',instruction='turn on the stove',
            correction_input_ids=['u1','u2'],source='qwen_realtime_current_user',voice_input_id='u2',user_utterance='炉灶。')
        self.assertEqual(result['status'],'accepted');self.assertEqual(self.s.instruction,'turn on the stove')
        self.assertIn('打开泸州',self.s.task_record['user_utterance'])
        self.assertEqual(self.s.task_record['speech_correction_evidence']['correction_input_ids'],['u1','u2'])
        self.assertIsNone(self.context())  # consumed, not reusable

    def test_clarification_preserves_original_verb_across_reconnect(self):
        self.pair()
        p=self.cmd('robot_begin_clarification',user_utterance='炉灶。',voice_input_id='u2',
                   source='qwen_realtime_current_user',question='是要打开炉灶吗？',missing_slot='reference')['pending_clarification']
        self.assertEqual([x['text'] for x in p['source_utterances']],['请你帮我打开泸州。','炉灶。'])
        self.assertIsNone(self.s.task_id)

    def test_expired_changed_episode_and_consumed_context_cannot_dispatch(self):
        self.pair()
        self.s.db.execute('UPDATE events SET time=? WHERE kind="speech_classified"',(time.time()-100,))
        self.assertIsNone(self.context())
        with self.assertRaisesRegex(TaskError,'correction_context_stale_or_unbound'):
            self.cmd('robot_start_task',instruction='turn on the stove',correction_input_ids=['u1','u2'],source='qwen_realtime_current_user',voice_input_id='u2',user_utterance='炉灶。')
        self.assertIsNone(self.s.task_id)

    def test_control_invalidates_correction_lease(self):
        self.cmd('robot_start_task',instruction='put the bowl on the plate')
        self.say('请你帮我打开泸州。','u1');self.cmd('robot_pause')
        self.say('炉灶。','u2');self.assertIsNone(self.context())

    def test_wrong_input_pair_and_invented_object_rejected(self):
        self.pair()
        for ids,goal in [(['old','u2'],'turn on the stove'),(['u1','u2'],'put the cream cheese in the bowl')]:
            with self.assertRaises(TaskError):
                self.cmd('robot_start_task',instruction=goal,correction_input_ids=ids,source='qwen_realtime_current_user',voice_input_id='u2',user_utterance='炉灶。')
        self.assertIsNone(self.s.task_id)

    def test_correction_cannot_flip_the_action_verb(self):
        self.pair()
        with self.assertRaisesRegex(TaskError,'correction_action_mismatch'):
            self.cmd('robot_start_task',instruction='turn off the stove',correction_input_ids=['u1','u2'],source='qwen_realtime_current_user',voice_input_id='u2',user_utterance='炉灶。')
        self.assertIsNone(self.s.task_id)

    def test_bare_entity_after_complete_command_question_or_assent_is_not_correction(self):
        for first,last in [('把碗放到盘子上。','炉灶。'),('炉灶在哪里？','炉灶。'),('打开泸州。','嗯。'),('如果打开泸州呢？','炉灶。')]:
            self.say(first,'a'+str(self.seq));self.seq+=1;self.say(last,'b'+str(self.seq));self.seq+=1
            self.assertIsNone(self.context(),(first,last))


if __name__=='__main__':unittest.main()
