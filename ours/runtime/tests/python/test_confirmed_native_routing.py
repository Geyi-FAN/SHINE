"""Post-confirmation routing ignores only a consumed terminal consent clause."""
import copy,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime/freeze/voice/robot_gateway'))
from native_execution import native_candidate

class ConfirmedNativeRoutingTests(unittest.TestCase):
    task='open the middle drawer of the cabinet'
    raw='Open the middle drawer of the cabinet, but ask for my confirmation before starting.'
    def state(self,raw=None,confirmed=True):
        record=dict(user_utterance=raw or self.raw,confirmed_proposal_id='p1'if confirmed else None)
        return SimpleNamespace(policy_metadata=dict(executor='pi05_e3_v4'),instruction=self.task,
            task_record=record,deferred_task=None)
    def test_consumed_confirmation_retains_native_route(self):self.assertEqual(native_candidate(self.state(),True,'none')[0]['task_id'],0)
    def test_unconfirmed_raw_still_not_native(self):self.assertIsNone(native_candidate(self.state(confirmed=False),True,'none')[0])
    def test_original_evidence_not_modified(self):
        s=self.state();old=copy.deepcopy(s.task_record);native_candidate(s,True,'none');self.assertEqual(s.task_record,old)
    def test_ask_me_variant(self):self.assertEqual(native_candidate(self.state('Open the middle drawer, but ask me to confirm before you start.'),True,'none')[0]['task_id'],0)
    def test_negative_physical_clause_retained(self):self.assertIsNone(native_candidate(self.state('Do not open the middle drawer, but ask for my confirmation before starting.'),True,'none')[0])
    def test_keep_constraint_retained(self):self.assertIsNone(native_candidate(self.state('Open the middle drawer and keep the bowl in place, but ask for my confirmation before starting.'),True,'none')[0])
    def test_before_physical_sequence_retained(self):self.assertIsNone(native_candidate(self.state('Open the middle drawer before putting the bowl away, but ask for my confirmation before starting.'),True,'none')[0])
    def test_trailing_constraint_not_stripped(self):self.assertIsNone(native_candidate(self.state(self.raw+' Keep the bowl in place.'),True,'none')[0])
    def test_extra_then_goal_retained(self):self.assertIsNone(native_candidate(self.state('Open the middle drawer then put the bowl on the stove, but ask for my confirmation before starting.'),True,'none')[0])
    def test_declared_precondition_not_dropped(self):
        s=self.state();s.task_record['preconditions']=['close the top drawer'];self.assertIsNone(native_candidate(s,True,'none')[0])
    def test_takeover_stays_symbolic(self):self.assertIsNone(native_candidate(self.state(),False,'none')[0])
    def test_held_object_stays_symbolic(self):self.assertIsNone(native_candidate(self.state(),True,'bowl')[0])
    def test_unknown_holding_stays_symbolic(self):self.assertIsNone(native_candidate(self.state(),True,'unknown')[0])
    def test_other_model_stays_symbolic(self):
        s=self.state();s.policy_metadata['executor']='pi05_v3r';self.assertIsNone(native_candidate(s,True,'none')[0])
    def test_real_confirmed_task_record_retains_native_route(self):
        from core import RobotState
        from grounding import ENTITIES,inventory_from_names
        with tempfile.TemporaryDirectory()as tmp:
            s=RobotState(tmp);s.ready=True;s.mode='idle';s.policy_metadata=dict(executor='pi05_e3_v4')
            s.scene_inventory=inventory_from_names(v[0]for v in ENTITIES.values())
            def cmd(name,text,uid,**kw):
                s.record_interaction(dict(episode_id=s.episode,input_id=uid,text=text,task_version=s.version))
                return s.command(name,dict(episode_id=s.episode,expected_task_version=s.version,
                    user_utterance=text,voice_input_id=uid,source='qwen_realtime_current_user',**kw),uid)
            try:
                p=cmd('robot_propose_task',self.raw,'u1',instruction=self.task)['pending_proposal']
                cmd('robot_resolve_proposal','Yes, open the middle drawer.','u2',proposal_id=p['proposal_id'],decision='confirm')
                self.assertEqual(s.task_record['confirmed_proposal_id'],p['proposal_id'])
                self.assertEqual(s.task_record['user_utterance'],self.raw)
                self.assertEqual(native_candidate(s,True,'none')[0]['task_id'],0)
            finally:s.db.close()

if __name__=='__main__':unittest.main()
