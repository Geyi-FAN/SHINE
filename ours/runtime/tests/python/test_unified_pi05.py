"""Actual composition and HTTP protocol, without a model or simulator."""
import copy
import io
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from unified.actor import build_inputs, configuration, validate_policy_metadata, Pi05HTTPClient


def metadata():
    c = configuration()
    return dict(model='pi05', variant='E3', checkpoint=c['checkpoint'],
                checkpoint_step=30000, trajectories=744, image_size=224,
                state_dimension=8, action_horizon=10, execute_steps=3,
                flow_steps=10, discrete_state_input=True, visual_marker=False,
                drawer_handle_coordinates=False,complete_task_input_supported=True,
                normalization_sha256=c['normalization_sha256'])


class ActorIdentityTests(unittest.TestCase):
    def test_pi05_ordinary_task_uses_complete_task_admission(self):
        from speech_routing import native_candidate
        state=SimpleNamespace(policy_metadata={'executor':'pi05_e3_v4'},instruction='put the bowl on the stove',task_record={'user_utterance':'put the bowl on the stove'},deferred_task=None)
        skill,reason=native_candidate(state,True,'none')
        self.assertEqual(skill['skill_id'],'bowl_stove')
        self.assertEqual(reason,'complete_trained_task_in_standard_episode')
        self.assertIsNone(native_candidate(state,False,'none')[0])
        self.assertIsNone(native_candidate(state,True,'bowl')[0])

    def test_qa_frame_assets_are_included(self):
        from PIL import Image
        import io
        import qa_image
        image=io.BytesIO();Image.new('RGB',(256,256)).save(image,format='JPEG')
        root=Path(__file__).resolve().parents[2]/'runtime/freeze/voice/data/visual_atlas_v2'
        result=qa_image.qa_image(image.getvalue(),image.getvalue(),root)
        self.assertEqual(Image.open(io.BytesIO(result)).size,(1024,768))

    def test_shared_main_ports_are_rejected(self):
        from launch import free_port
        for port in [8787,8801,0,65536]:
            with self.subTest(port=port), self.assertRaises(ValueError):free_port(port)

    def test_native_executes_three_of_ten_predictions(self):
        from native_execution import NativeExecution
        native=NativeExecution.__new__(NativeExecution)
        native.skill={'canonical_task':'put the bowl on the stove'}
        native.log=lambda *_args,**_kw:None
        native.client=SimpleNamespace(infer=lambda request:dict(actions=np.zeros((10,7))))
        image=np.zeros((256,256,3),np.uint8)
        obs=dict(agentview_image=image,robot0_eye_in_hand_image=image,
                 robot0_eef_pos=[0,0,0],robot0_eef_quat=[0,0,0,1],robot0_gripper_qpos=[0,0])
        self.assertEqual(native._infer(obs,'opaque',0,0)['actions'].shape,(3,7))

    def test_actual_selected_profile(self):
        import policy_backend, execution_profile, os
        self.assertIs(policy_backend.SmolHTTPClient, Pi05HTTPClient)
        self.assertEqual(os.environ['HYBRID_EXECUTOR'], 'pi05_e3_v4')
        self.assertEqual(len(execution_profile.load_catalog()), 22)
        self.assertEqual(validate_policy_metadata(metadata())['executor'], 'pi05_e3_v4')

    def test_legacy_and_wrong_weights_rejected(self):
        for key, value in [('model','smolvla'),('image_size',256),('execute_steps',4),
                           ('checkpoint_step',7240),('trajectories',880),
                           ('normalization_sha256','wrong'),('checkpoint','/tmp/wrong'),
                           ('visual_marker',True),('complete_task_input_supported',False)]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                validate_policy_metadata(dict(metadata(), **{key:value}))

    def test_images_and_original_state_encoding(self):
        rgb = np.zeros((256,256,3), np.uint8)
        rgb[:128,:128,0] = 255
        obs = dict(agentview_image=rgb, robot0_eye_in_hand_image=rgb,
                   robot0_eef_pos=[.1,.2,.3],robot0_eef_quat=[0,0,0,1],
                   robot0_gripper_qpos=[.04,-.04])
        result = build_inputs(obs, 'put the bowl on the stove')
        self.assertEqual(result['observation/image'].shape, (224,224,3))
        self.assertEqual(int(result['observation/image'][-1,-1,0]),255)
        self.assertEqual(int(result['observation/image'][0,0,0]),0)
        np.testing.assert_allclose(result['observation/state'], [.1,.2,.3,0,0,0,.04,-.04])
        self.assertNotIn('Current subgoal:', result['prompt'])
        prompt = 'Task: Return the bowl.\nCurrent subgoal: Return the bowl at <146,72>.\nCoordinates: MAIN, 224x224, <y,x> pixels.\n'
        self.assertEqual(build_inputs(obs,prompt)['prompt'],prompt)
        with self.assertRaises(ValueError):
            build_inputs(obs,'Task: Test. Coordinates: WRIST, 256x256, <x,y>.')

    def test_real_npz_http_protocol_and_no_post_retry(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_GET(self):
                payload=json.dumps(metadata()).encode();self.send_response(200)
                self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
            def do_POST(self):
                with np.load(io.BytesIO(self.rfile.read(int(self.headers['Content-Length']))),allow_pickle=False) as data:
                    requests.append(json.loads(str(data['metadata'])))
                    assert data['image'].shape == (224,224,3) and data['state'].shape == (8,)
                self.send_response(503);self.end_headers();self.wfile.write(b'uncertain')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            client=Pi05HTTPClient(port=server.server_port)
            client.get_server_metadata()
            with self.assertRaises(Exception):
                client.infer({'observation/image':np.zeros((224,224,3),np.uint8),
                              'observation/wrist_image':np.zeros((224,224,3),np.uint8),
                              'observation/state':np.zeros(8),'prompt':'test',
                              'evaluation_case_id':'opaque','evaluation_call_index':0,'evaluation_seed':7})
            self.assertEqual(len(requests),1)
        finally:server.shutdown();server.server_close();thread.join()

    def test_full_c3r_and_shared_kernel_compiles(self):
        import sys
        from bridge import SingleOwnerBridge
        from c3r.integration import install as c3r
        from unified.hooks import install_bridge
        c3r(SingleOwnerBridge);install_bridge(SingleOwnerBridge)
        runner=sys.modules['frozen_g2_runner']
        with tempfile.TemporaryDirectory() as directory:
            bridge=SingleOwnerBridge.__new__(SingleOwnerBridge)
            bridge.runner=runner;bridge.root=Path(directory);bridge.engine_start_step=0
            bridge.log=lambda *_args,**_kwargs:None
            bridge.bootstrap_gate=lambda *_args:True
            bridge.build_run_function()
            source=(bridge.root/'generated_kernel.py').read_text()
            self.assertTrue(callable(bridge.run_function))
            self.assertIn('T7_BOOTSTRAP_GATE(',source)
            self.assertIn('GATEWAY_BRIDGE.engine_start_step',source)
        self.assertTrue(SingleOwnerBridge._c3r_integrated)
        self.assertTrue(SingleOwnerBridge._unified_bridge_installed)

