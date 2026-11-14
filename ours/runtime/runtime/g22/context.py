"""Complete pre-trial restoration; no mutation is permitted after trial start."""
def restore_complete(env,context,authority):
    obs=authority.state.restore(env,context)
    # Frozen restore writes warm-start before controller.update(force=True).
    # That update can call forward dynamics and overwrite the solver cache.
    # Reapply it AFTER all initialization; body state/images remain untouched.
    env.sim.data.qacc_warmstart[:]=context['data_qacc_warmstart']
    return obs
