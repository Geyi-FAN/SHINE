"""Both routes use the same imported pi05 E3 params and normalization.

Historical build_smol_inputs/SmolHTTPClient names are compatibility aliases,
not a fallback. They resolve to these pi05-only implementations.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import urllib.request

import numpy as np
from PIL import Image

W = Path(__file__).resolve().parents[2]
CONFIG = W/'config/model.json'
COORDINATES = 'Coordinates: MAIN, 224x224, <y,x> pixels.'


def configuration():
    return json.loads(CONFIG.read_text())


def validate_policy_metadata(metadata, expected=None, model=None):
    c = configuration()
    required = dict(model='pi05', variant='E3', checkpoint_step=30000,
                    trajectories=744, image_size=224, state_dimension=8,
                    action_horizon=10, execute_steps=3, flow_steps=10,
                    discrete_state_input=True, visual_marker=False,
                    drawer_handle_coordinates=False)
    errors = [f'{k}: {metadata.get(k)!r} != {v!r}' for k, v in required.items()
              if metadata.get(k) != v]
    if Path(metadata.get('checkpoint', '')).resolve() != Path(c['checkpoint']).resolve():
        errors.append('checkpoint identity mismatch')
    if expected and Path(expected).resolve() != Path(c['checkpoint']).resolve():
        errors.append('caller selected a different checkpoint')
    if metadata.get('normalization_sha256') != c['normalization_sha256']:
        errors.append('normalization fingerprint mismatch')
    if c.get('complete_task_input_enabled') and metadata.get('complete_task_input_supported') is not True:
        errors.append('policy service does not support explicit complete-task input')
    if errors:
        raise RuntimeError('pi05 E3 admission failed: ' + '; '.join(errors))
    return dict(metadata, executor='pi05_e3_v4', runtime_actor='pi05_744_E3_30k')


def validate_conditioning_prompt(prompt, mode):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError('Nonempty task text is required')
    if mode == 'complete_task':
        if any(label in prompt for label in ('Task:', 'Current subgoal:', 'Current Subgoal:', 'Coordinates:')):
            raise ValueError('Complete-task text must not contain manual conditioning headers')
    elif mode == 'symbolic':
        if COORDINATES.rstrip('.') not in prompt:
            raise ValueError('Wrong view, image transform or coordinate convention')
    else:
        raise ValueError('Unknown conditioning mode')
    return prompt


def build_inputs(observation, prompt, conditioning_mode='symbolic'):
    q = np.asarray(observation['robot0_eef_quat'], np.float64).copy()
    q[3] = np.clip(q[3], -1., 1.)
    den = np.sqrt(1. - q[3]*q[3])
    aa = np.zeros(3) if np.isclose(den, 0.) else q[:3]*2.*np.arccos(q[3])/den
    state = np.r_[observation['robot0_eef_pos'], aa,
                  observation['robot0_gripper_qpos']].astype(np.float32)
    if state.shape != (8,) or not np.isfinite(state).all():
        raise ValueError('Expected finite EEF/axis-angle/two-finger 8D state')
    def image(key):
        rgb = np.ascontiguousarray(observation[key][::-1, ::-1])
        return np.asarray(Image.fromarray(rgb).resize((224, 224), Image.Resampling.BILINEAR))
    # Native is a complete ordinary task, not a script-created Oracle subgoal.
    # Symbolic prompts already include their Agent-selected stage and reference.
    if conditioning_mode == 'symbolic' and 'Coordinates:' not in prompt:
        prompt = 'Task: ' + str(prompt).strip().rstrip('.') + '.\n' + COORDINATES + '\n'
    prompt = validate_conditioning_prompt(prompt, conditioning_mode)
    request = {'observation/image': image('agentview_image'),
               'observation/wrist_image': image('robot0_eye_in_hand_image'),
               'observation/state': state, 'prompt': prompt}
    if conditioning_mode == 'complete_task':
        request['conditioning_mode'] = conditioning_mode
    return request


class Pi05HTTPClient:
    def __init__(self, host='127.0.0.1', port=None):
        if port is None:
            raise ValueError('An isolated pi05 policy port is required')
        self.url = f'http://{host}:{int(port)}'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get_server_metadata(self):
        with self.opener.open(self.url+'/metadata', timeout=10) as response:
            data = json.load(response)
        return validate_policy_metadata(data)

    def infer(self, request):
        main = np.asarray(request['observation/image'])
        wrist = np.asarray(request['observation/wrist_image'])
        state = np.asarray(request['observation/state'])
        if main.shape != (224,224,3) or wrist.shape != (224,224,3) or state.shape != (8,):
            raise ValueError('Wrong pi05 image/state shapes; no implicit legacy fallback')
        metadata = {k:request[k] for k in ('prompt','evaluation_case_id','evaluation_call_index')}
        if 'conditioning_mode' in request:
            metadata['conditioning_mode'] = request['conditioning_mode']
        if 'evaluation_seed' in request:
            metadata['evaluation_seed'] = request['evaluation_seed']
        payload = io.BytesIO()
        np.savez(payload, image=main, wrist=wrist, state=state, metadata=json.dumps(metadata))
        req = urllib.request.Request(self.url+'/infer', data=payload.getvalue(),
                                     headers={'Content-Type':'application/octet-stream'})
        # A transport error never repeats POST; the controller must stop and log
        # uncertain execution. No cached answer, different checkpoint or retry.
        with self.opener.open(req, timeout=120) as response:
            answer = json.load(response)
        if request.get('conditioning_mode') == 'complete_task':
            if answer.get('conditioning_mode') != 'complete_task' or answer.get('effective_prompt_sha256') != hashlib.sha256(request['prompt'].encode()).hexdigest():
                raise ValueError('Policy service did not confirm unchanged complete-task text')
        actions = np.asarray(answer.get('actions'), float)
        if actions.shape != (10,7) or not np.isfinite(actions).all():
            raise ValueError('Expected ten finite seven-dimensional pi05 actions')
        return answer


SmolHTTPClient = Pi05HTTPClient
build_smol_inputs = build_inputs
build_replay_smol_inputs = lambda observation, prompt, *_: build_inputs(observation, prompt)
