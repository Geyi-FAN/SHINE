import copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np

B=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102')
sys.path[:0]=[str(B),str(B/'freeze/f28d/source')]
import recovery_observer
from recovery_runtime import RecoveryRuntime
from t06l_inspection import scope,prepare,system,extra_errors,install

class ScopeTests(unittest.TestCase):
    def rows(self,width=.058):
        return [dict(frame=f,sensor={'width':width,'eef_xyz':[0.,0.,1.],'eef_yx':[50.,50.]},
            image_points=[],geometry={},main=np.zeros((24,24,3),np.uint8),wrist=np.zeros((24,24,3),np.uint8))for f in [0,4,8]]
    def test_initial_scope(self):self.assertEqual(scope(self.rows(),{'operation':None,'status':'waiting'}),'initial_contact')
    def test_selected_grasp_keeps_full_inspection(self):self.assertIsNone(scope(self.rows(),{'operation':'grasp_cheese'}))
    def test_stalled_placement_keeps_full_inspection(self):self.assertIsNone(scope(self.rows(),{'operation':'cheese_bowl'}))
    def test_missing_point_context_keeps_full_inspection(self):self.assertIsNone(scope(self.rows(),{'observation_request_context':{'reason':'current_target_reference_missing'}}))
    def test_clear_scope_needs_executed_context_and_measured_open(self):
        d={'observation_request_context':dict(reason='supported_in_place_release_executed_but_hand_may_still_intersect_old_object',released_object='bowl',gripper_open=True)}
        self.assertEqual(scope(self.rows(.078),d),'post_release_clearance')
        self.assertIsNone(scope(self.rows(.059),d))
    def test_unknown_width_does_not_shorten_inspection(self):
        for value in [None,float('nan'),'open']:
            rows=self.rows();rows[-1]['sensor']['width']=value;self.assertIsNone(scope(rows,{}))
    def test_selected_stage_in_context_does_not_shorten(self):self.assertIsNone(scope(self.rows(),{'observation_request_context':{'selected_stage':{'operation':'grasp_cheese'}}}))
    def test_all_sensor_history_kept_and_current_only_shown(self):
        rows=self.rows();payload={'sensor_frames':[{'frame':r['frame']}for r in rows]};before=copy.deepcopy(payload)
        kind,shown=prepare(payload,rows,{})
        self.assertEqual(kind,'initial_contact');self.assertEqual([r['frame']for r in shown],[8]);self.assertEqual([r['frame']for r in payload['sensor_frames']],[r['frame']for r in before['sensor_frames']])
    def test_active_scope_original_system_unchanged(self):self.assertEqual(system('ORIGINAL',None),'ORIGINAL')
    def test_early_clearance_is_rejected(self):
        payload={'scoped_inspection':'initial_contact','current_image_frames_shown':[8]}
        self.assertTrue(extra_errors({'recovery_request':'clear_supported_object','evidence_frames':[8]},payload))
    def test_unshown_rgb_citation_rejected(self):
        payload={'scoped_inspection':'initial_contact','current_image_frames_shown':[8]}
        self.assertTrue(extra_errors({'recovery_request':'observe_only','evidence_frames':[0]},payload))
    def test_unknown_object_still_fails_original_release_validator(self):
        from observation_validation import errors
        self.assertTrue(errors({'recovery_request':'release_supported_in_place','release_object':'unknown','support_visible':{}},{}))
    def call(self,short,diagnostics,pred=None):
        pred=pred or dict(held_object='none',support_visible={o:True for o in ['bowl','cheese','plate','wine_bottle']},
            relations={'bowl_drawer':False,'cheese_bowl':False},bowl_location='plate',evidence_frames=[8],
            rationale='The current hand touches the rim of a supported bowl.',recovery_request='release_supported_in_place',release_object='bowl')
        bodies=[];old=recovery_observer.request_json
        recovery_observer.request_json=lambda req,**kw:(bodies.append(json.loads(req.data))or{'choices':[{'message':{'content':json.dumps(pred)}}]})
        class Local(recovery_observer.RecoveryObserver):pass
        try:
            if short:install(Local)
            with tempfile.TemporaryDirectory(dir='/mnt/disk_4/geyi/t4_T06_latency_placement_20261104')as d:
                observer=object.__new__(Local);observer.folder=Path(d);observer.calls=[];observer.cfg={'model':'unit','chat_url':'http://127.0.0.1:1'};observer.key='not-a-key';observer.episode_reference=Path(d)/'missing.png'
                result=observer.check('Put the cream cheese in that bowl and leave the bowl there.',self.rows(),diagnostics)
                return result,bodies
        finally:recovery_observer.request_json=old
    def test_actual_observer_uses_latest_pair_and_same_sensor_history(self):
        result,bodies=self.call(True,{})
        self.assertTrue(result['accepted']);body=bodies[0];contents=body['messages'][1]['content'];payload=json.loads(contents[0]['text'])
        self.assertEqual(len([x for x in contents if x['type']=='image_url']),1)
        self.assertEqual(len(payload['sensor_frames']),3);self.assertEqual(payload['current_image_frames_shown'],[8])
        self.assertIn('two accepted NEW-FRAME',body['messages'][0]['content'])
    def test_stalled_execution_request_bytes_unchanged(self):
        pred=dict(held_object='none',support_visible={'cheese':True},relations={'cheese_bowl':False},evidence_frames=[8],recovery_request='observe_only')
        _,old=self.call(False,{'operation':'grasp_cheese'},pred)
        _,new=self.call(True,{'operation':'grasp_cheese'},pred)
        self.assertEqual(old,new)
    def test_two_model_confirmations_still_required_before_actual_release(self):
        # Exercise the actual unchanged runtime, not an imitation of its guard.
        r=object.__new__(RecoveryRuntime);r.inspections=0;r.inspection_limit=8;r.last_check=-1000;r.visual_facts=None;r.events=[];r.empty_hand_proof=None;r.grip_release_until=None;r.release_requested_at=None
        current={'frame':0};response=dict(held_object='none',support_visible={'bowl':True},relations={},recovery_request='release_supported_in_place',release_object='bowl')
        r.observer=SimpleNamespace(check=lambda *a:dict(accepted=True,response=copy.deepcopy(response)))
        mon=SimpleNamespace(last=0,rgb_rows=self.rows(),diagnostics={'holding':{'near_px':{'bowl':10.}}},samples=[{'width':.03}],held='unknown',held_width=None,last_held_frame=-1000,snapshot={})
        r.user_message='put cheese in bowl'
        r.inspect(mon);self.assertIsNone(r.grip_release_until)
        mon.last=4;r.inspect(mon);self.assertIsNone(r.grip_release_until);self.assertEqual(r.inspections,1)
        mon.last=8;r.inspect(mon);self.assertEqual(r.grip_release_until,24);self.assertEqual(r.inspections,2)
    def test_no_release_when_visual_support_unknown(self):
        from observation_validation import errors
        self.assertTrue(errors({'recovery_request':'release_supported_in_place','release_object':'bowl','support_visible':{'bowl':None}},{}))

if __name__=='__main__':unittest.main()
