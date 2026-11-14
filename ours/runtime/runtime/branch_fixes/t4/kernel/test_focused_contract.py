import copy,json,tempfile,unittest,sys
from pathlib import Path
B=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102')
sys.path[:0]=[str(B),str(B/'freeze/f28d/source')]
from t06l_inspection import prepare,contract,install_schema
import output_contract

class FocusedContract(unittest.TestCase):
    def fixture(self,scope='initial_contact'):
        payload={'schema':'recovery_observation_v1','scoped_inspection':scope,
            'current_image_frames_shown':[8],'sensor_frames':[{'frame':f}for f in [0,4,8]]}
        return dict(model='unit',messages=[dict(role='system',content='unit'),dict(role='user',content=[dict(type='text',text=json.dumps(payload)),dict(type='text',text='frame=8: MAIN left, WRIST right')])])
    def original(self):
        fn=output_contract.constrain
        return getattr(fn,'_t06l_original',fn)
    def test_schema_has_only_needed_six_fields(self):
        body=contract(self.fixture(),'recovery',self.original());schema=body['response_format']['json_schema']['schema']
        self.assertEqual(set(schema['required']),{'held_object','support_visible','evidence_frames','rationale','recovery_request','release_object'})
        self.assertFalse(schema['additionalProperties']);self.assertLessEqual(schema['properties']['rationale']['maxLength'],120)
    def test_initial_tools_cannot_clear_before_release(self):
        schema=contract(self.fixture(),'recovery',self.original())['response_format']['json_schema']['schema']
        self.assertEqual(schema['properties']['recovery_request']['enum'],['release_supported_in_place','observe_only','none'])
    def test_clearance_tools_cannot_release_again(self):
        schema=contract(self.fixture('post_release_clearance'),'recovery',self.original())['response_format']['json_schema']['schema']
        self.assertEqual(schema['properties']['recovery_request']['enum'],['clear_supported_object','observe_only','none'])
    def test_only_shown_current_rgb_can_be_cited(self):
        schema=contract(self.fixture(),'recovery',self.original())['response_format']['json_schema']['schema']
        self.assertEqual(schema['properties']['evidence_frames']['items']['enum'],[8])
    def test_stalled_packet_contract_byte_equivalent(self):
        body=self.fixture();payload=json.loads(body['messages'][1]['content'][0]['text']);payload.pop('scoped_inspection');body['messages'][1]['content'][0]['text']=json.dumps(payload)
        old=self.original()(body,'recovery');new=contract(body,'recovery',self.original());self.assertEqual(old,new)
    def test_verifier_contract_is_unchanged(self):
        body=self.fixture();self.assertEqual(self.original()(body,'verifier'),contract(body,'verifier',self.original()))
    def test_exact_k1_and_robot_values_kept_other_points_omitted(self):
        width=.0599999991234
        raw={'sensor_frames':[dict(frame=f,sensor={'width':width},fresh_yolo_points=[dict(entity='bowl',keypoint='K1',yx224=[112.123456789,140.987654321]),dict(entity='bowl',keypoint='K3',yx224=[110.,140.]),dict(entity='stove_placement',keypoint='K3',yx224=[20.,30.])],depth_xyz_m={'bowl.K1':[.123456789,.987654321,.999999999],'bowl.K3':[1.,2.,3.]})for f in [0,4,8]]}
        before=copy.deepcopy(raw);rows=[dict(frame=f,sensor={'width':width})for f in [0,4,8]]
        with tempfile.TemporaryDirectory(dir='/mnt/disk_4/geyi/t4_T06_latency_placement_20261104')as d:
            prepare(raw,rows,{},Path(d),0)
            self.assertEqual(json.loads((Path(d)/'0_input_full_sensors.json').read_text()),before)
        for old,new in zip(before['sensor_frames'],raw['sensor_frames']):
            self.assertEqual(new['frame'],old['frame']);self.assertEqual(new['sensor'],old['sensor'])
            self.assertEqual(new['fresh_yolo_points'],old['fresh_yolo_points'][:1]);self.assertEqual(new['depth_xyz_m'],{'bowl.K1':old['depth_xyz_m']['bowl.K1']})
    def test_minimal_reply_validates_real_json_schema(self):
        import jsonschema
        schema=contract(self.fixture(),'recovery',self.original())['response_format']['json_schema']['schema']
        pred=dict(held_object='unknown',support_visible={o:(True if o=='bowl'else None)for o in ['bowl','cheese','wine_bottle','plate']},evidence_frames=[8],rationale='Closed fingers near a visibly supported rim.',recovery_request='release_supported_in_place',release_object='bowl')
        jsonschema.validate(pred,schema)
        bad=dict(pred,relations={})
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(bad,schema)
    def test_unshown_evidence_fails_real_schema(self):
        import jsonschema
        schema=contract(self.fixture(),'recovery',self.original())['response_format']['json_schema']['schema']
        pred=dict(held_object='none',support_visible={o:None for o in ['bowl','cheese','wine_bottle','plate']},evidence_frames=[0],rationale='Unknown support.',recovery_request='observe_only',release_object=None)
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(pred,schema)
