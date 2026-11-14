"""F08: preserve validated source audio across a NEW confirmation, never guess nouns."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime/freeze/voice/robot_gateway'))
from core import RobotState,TaskError
from grounding import ENTITIES,inventory_from_names
from native_execution import native_candidate

class ConfirmationAcousticSourceTests(unittest.TestCase):
    raw='Open the top drawer and put the ball inside, but wait for my confirmation.'
    alternative='Open the top drawer and put the bowl inside, but wait for my confirmation.'
    task='open the top drawer and put the bowl inside'
    yes='Yes. Go ahead.'
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=RobotState(self.tmp.name);self.s.ready=True;self.s.mode='idle';self.seq=0
        self.s.policy_metadata=dict(executor='pi05_e3_v4');self.s.scene_inventory=inventory_from_names(v[0]for v in ENTITIES.values())
    def tearDown(self):self.s.db.close();self.tmp.cleanup()
    def evidence(self,**kw):return dict(kind='audio_only_relisten.v1',primary=self.raw,transcript=self.alternative,reference_sent=False,scene_sent=False,audio_bytes=200960,**kw)
    def record(self,uid,text,evidence=None):return self.s.record_interaction(dict(episode_id=self.s.episode,input_id=uid,text=text,task_version=self.s.version,asr_evidence=evidence))
    def cmd(self,name,text,uid,**kw):return self.s.command(name,dict(episode_id=self.s.episode,expected_task_version=self.s.version,user_utterance=text,voice_input_id=uid,source='qwen_realtime_current_user',**kw),uid+':'+name)
    def propose(self,evidence=None):
        self.record('source',self.raw,self.evidence()if evidence is None else evidence)
        return self.cmd('robot_propose_task',self.raw,'source',instruction=self.task)['pending_proposal']
    def confirm(self,p,uid='yes'):
        self.record(uid,self.yes);return self.cmd('robot_resolve_proposal',self.yes,uid,proposal_id=p['proposal_id'],decision='confirm')
    def test_proposal_with_validated_audio_never_moves(self):
        p=self.propose();self.assertTrue(p['semantic_check']['audio_relisten_grounding_used']);self.assertIsNone(self.s.task_id);self.assertEqual(self.s.action_steps,0)
    def test_confirm_revalidates_original_audio(self):
        p=self.propose();r=self.confirm(p);self.assertEqual(r['status'],'accepted');self.assertEqual(r['confirmed_proposal_id'],p['proposal_id'])
    def test_original_and_confirmation_ids_are_distinct(self):
        self.confirm(self.propose());r=self.s.task_record;self.assertEqual(r['voice_input_id'],'yes');self.assertEqual(r['speech_correction_evidence']['source_input_id'],'source');self.assertEqual(r['user_utterance'],self.raw)
    def test_actual_acoustic_provenance_retained_for_routing(self):
        self.confirm(self.propose());e=self.s.task_record['speech_correction_evidence'];self.assertEqual(e['kind'],'validated_acoustic_source.v1');self.assertEqual(e['audio_only_alternative'],self.alternative);self.assertFalse(e['scene_sent']);self.assertFalse(e['reference_sent']);self.assertEqual(native_candidate(self.s,True,'none')[0]['task_id'],3)
    def test_new_input_same_confirmation_never_restarts(self):
        self.confirm(self.propose());key=(self.s.task_id,self.s.version,self.s.action_steps,self.s.running_since)
        r=self.record('duplicate',self.yes);self.assertNotIn('confirmation',r);self.assertEqual((self.s.task_id,self.s.version,self.s.action_steps,self.s.running_since),key)
    def test_duplicate_fresh_start_rejected(self):
        self.confirm(self.propose());task=self.s.task_id;self.record('duplicate',self.yes)
        with self.assertRaisesRegex(TaskError,'speech_does_not_authorize'):self.cmd('robot_start_task',self.yes,'duplicate',instruction=self.task)
        self.assertEqual(self.s.task_id,task)
    def test_consumed_proposal_cannot_be_replayed(self):
        p=self.propose();self.confirm(p);task=self.s.task_id
        with self.assertRaises(TaskError):self.confirm(p,'duplicate')
        self.assertEqual(self.s.task_id,task)
    def test_same_tool_request_is_idempotent(self):
        p=self.propose();r=self.confirm(p);version=self.s.version
        same=dict(episode_id=self.s.episode,expected_task_version=0,user_utterance=self.yes,voice_input_id='yes',source='qwen_realtime_current_user',proposal_id=p['proposal_id'],decision='confirm')
        self.assertEqual(self.s.command('robot_resolve_proposal',same,'yes:robot_resolve_proposal'),r);self.assertEqual(self.s.version,version)
    def test_no_acoustic_evidence_not_guessed(self):
        self.record('source',self.raw)
        with self.assertRaises(TaskError):self.cmd('robot_propose_task',self.raw,'source',instruction=self.task)
    def test_scene_informed_alternative_rejected(self):
        e=self.evidence();e['scene_sent']=True
        with self.assertRaises(TaskError):self.propose(e)
    def test_reference_informed_alternative_rejected(self):
        e=self.evidence();e['reference_sent']=True
        with self.assertRaises(TaskError):self.propose(e)
    def test_changed_action_not_acoustic_noun_repair(self):
        e=self.evidence();e['transcript']=self.alternative.replace('Open','Close')
        with self.assertRaises(TaskError):self.propose(e)
    def test_changed_destination_not_acoustic_noun_repair(self):
        e=self.evidence();e['transcript']=self.alternative.replace('top','middle')
        with self.assertRaises(TaskError):self.propose(e)
    def test_mismatching_primary_rejected(self):
        e=self.evidence();e['primary']='another utterance'
        with self.assertRaises(TaskError):self.propose(e)
    def test_input_key_cannot_spoof_confirmed_source(self):
        self.record('good',self.raw,self.evidence());self.record('bad',self.raw)
        with self.assertRaises(TaskError):self.cmd('robot_propose_task',self.raw,'bad',instruction=self.task,_confirmation_source_input_id='good')
    def test_original_source_must_still_match_proposal_raw(self):
        p=self.propose();self.s.pending_proposal['user_utterance']=self.raw.replace('ball','bull')
        with self.assertRaises(TaskError):self.confirm(p)
        self.assertIsNone(self.s.task_id)
    def test_other_source_id_cannot_supply_evidence(self):
        self.record('other','Put the cheese in the bowl.');p=self.propose();self.s.pending_proposal['voice_input_id']='other'
        with self.assertRaises(TaskError):self.confirm(p)
        self.assertIsNone(self.s.task_id)
    def test_source_evidence_revalidated_not_blindly_copied(self):
        p=self.propose();row=self.s.db.execute("select event_id from utterances where id='source'").fetchone();data=json.loads(self.s.db.execute('select payload from events where id=?',row).fetchone()[0]);data['asr_evidence']['scene_sent']=True;self.s.db.execute('update events set payload=? where id=?',(json.dumps(data),row[0]));self.s.db.commit()
        with self.assertRaises(TaskError):self.confirm(p)
        self.assertIsNone(self.s.task_id)
    def test_missing_original_source_rejected(self):
        p=self.propose();self.s.db.execute("delete from utterances where id='source'");self.s.db.commit()
        with self.assertRaises(TaskError):self.confirm(p)
        self.assertIsNone(self.s.task_id)
    def test_expired_proposal_rejected(self):
        p=self.propose();self.s.pending_proposal['expires_at']=0
        with self.assertRaises(TaskError):self.confirm(p)
        self.assertIsNone(self.s.task_id)
    def test_reject_does_not_authorize_action(self):
        p=self.propose();self.record('no','No.');r=self.cmd('robot_resolve_proposal','No.','no',proposal_id=p['proposal_id'],decision='reject');self.assertEqual(r['status'],'proposal_rejected');self.assertIsNone(self.s.task_id)
    def test_physical_keep_constraint_not_dropped(self):
        raw=self.raw+' Keep the wine bottle at its current position.';alt=self.alternative+' Keep the wine bottle at its current position.';e=self.evidence();e.update(primary=raw,transcript=alt);self.record('source',raw,e)
        with self.assertRaises(TaskError):self.cmd('robot_propose_task',raw,'source',instruction=self.task)

if __name__=='__main__':unittest.main()
