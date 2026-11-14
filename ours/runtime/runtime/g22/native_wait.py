"""Bind async Native waiting to the current request pose, never episode start."""
def tick(bridge,native,state,observation,pose_factory=None):
    previous=native.future
    native.tick(state,observation)
    if native.future is not None and native.future is not previous:
        if pose_factory is None:
            from hold_gate import PoseHold
            pose_factory=PoseHold
        bridge.pose=pose_factory(bridge.obs,bridge.env.env.robots[0].controller)
        bridge.log('native_async_hold_bound_to_request_pose',eef_xyz=bridge.obs['robot0_eef_pos'].tolist())
