"""Per-simulator EGL ownership for nested live/reference LIBERO environments.

The installed robosuite binding selects its GL context during construction but
does not select it again in MjSim.render. A newly constructed reference simulator
can therefore steal the thread's active context from the running episode.
This local adapter binds the owning context before each complete render/read.
It neither modifies camera names nor edits pixels, physics state, or robosuite.
"""
from functools import wraps


GUARD_VERSION='per_sim_make_current_v1'
OBSERVATION_CAMERAS=('agentview','robot0_eye_in_hand')


def bind_render_context(env):
    """Bind only this environment's current simulator; safe to call repeatedly."""
    sim=env.sim
    if getattr(sim,'_revision_render_guard',None)!=GUARD_VERSION:
        original_render=sim.render

        @wraps(original_render)
        def guarded_render(*args,**kwargs):
            # Fetch each time: robosuite can replace a render context when its
            # buffers are rebuilt. Do not retain another simulator's context.
            context=sim._render_context_offscreen
            if context is None:
                raise RuntimeError('revision_render_context_missing')
            if context.sim is not sim:
                raise RuntimeError('revision_render_context_owner_mismatch')
            context.gl_ctx.make_current()
            sim._revision_render_bind_count+=1
            return original_render(*args,**kwargs)

        sim.render=guarded_render
        sim._revision_render_guard=GUARD_VERSION
        sim._revision_render_bind_count=0
    env._revision_render_guard=GUARD_VERSION
    env._revision_render_info=dict(
        version=GUARD_VERSION,
        capture_strategy='owning_sim_GL_context_bound_before_every_render_and_pixel_read',
        camera_names=list(OBSERVATION_CAMERAS),
        camera_ids={name:int(sim.model.camera_name2id(name)) for name in OBSERVATION_CAMERAS},
        all_model_camera_names=list(sim.model.camera_names),
        pixel_transform='unchanged; existing observation rotation is retained')
    return env
