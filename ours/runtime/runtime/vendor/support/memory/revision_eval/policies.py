"""Policy boundary: observations only; simulator state is never sent to the actor."""
import numpy as np
from .env import rotate_libero_image


class DummyPolicy:
    """Environment/packaging smoke only. Never report this as a model baseline."""
    last_span_info={'policy':'dummy_smoke_only'}
    def begin_normal(self): pass
    def begin_revision(self,previous_instruction,episode_initial_rgb): pass
    def predict_env_action_chunk_from_obs(self,obs,instruction,execute_steps=12):
        return np.tile([0.,0.,0.,0.,0.,0.,-1.],(execute_steps,1))


class Pi05Policy:
    """OpenPI LIBERO websocket interface, checked against local OpenPI source.

    Server must load a LIBERO pi0.5 policy, including its own action unnormalizer.
    The standard LiberoInputs transform has no historical-reference slot.
    """
    def __init__(self,host,port,previous_context=False):
        from openpi_client.websocket_client_policy import WebsocketClientPolicy
        self.client=WebsocketClientPolicy(host,port)
        self.previous_context=previous_context;self.previous='';self.last_span_info=None

    def begin_normal(self):
        self.previous='';self.client.reset()

    def begin_revision(self,previous_instruction,episode_initial_rgb):
        self.previous=previous_instruction

    def predict_env_action_chunk_from_obs(self,obs,instruction,execute_steps=12):
        from openpi_client import image_tools
        def image(key):
            return image_tools.convert_to_uint8(image_tools.resize_with_pad(rotate_libero_image(obs[key]),224,224))
        # Same xyzw -> axis-angle conversion as OpenPI's LIBERO example.
        quat=np.asarray(obs['robot0_eef_quat'],dtype=np.float64).copy()
        quat[3]=np.clip(quat[3],-1.,1.)
        den=np.sqrt(1.-quat[3]*quat[3])
        aa=np.zeros(3) if np.isclose(den,0.) else quat[:3]*2.*np.arccos(quat[3])/den
        state=np.concatenate([obs['robot0_eef_pos'],aa,obs['robot0_gripper_qpos']]).astype(np.float32)
        prompt=instruction
        if self.previous_context and self.previous:
            prompt='Previous instruction: '+self.previous+'\nFollow the current instruction: '+instruction
        request={'observation/image':image('agentview_image'),
                 'observation/wrist_image':image('robot0_eye_in_hand_image'),
                 'observation/state':state,'prompt':prompt}
        actions=np.asarray(self.client.infer(request)['actions'],dtype=np.float32)
        # pi05_libero action_horizon is 10. Revision execute_steps=3 still requires H>=3;
        # normal protocol asks 12, so accept native H>=10 and execute min(H, execute_steps).
        min_h=min(execute_steps,10)
        if actions.ndim!=2 or actions.shape[1]!=7 or len(actions)<min_h or not np.isfinite(actions).all():
            raise ValueError('pi05_server_must_return_finite_unnormalized_LIBERO_actions_[H,7]')
        self.last_span_info=dict(policy='pi05_openpi',prompt=prompt,uses_historical_reference_image=False,
            previous_context=self.previous_context,state_shape=list(state.shape),returned_chunk=len(actions))
        return actions[:min(execute_steps,len(actions))]
