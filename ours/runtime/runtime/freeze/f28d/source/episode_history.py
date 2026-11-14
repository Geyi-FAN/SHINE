"""Private hybrid-evaluation adapter for episode-start validity evidence.

Pixels are supplied by YOLO on the original initial image. A disposable simulator
only checks the matching camera/initial object state; it never projects pixels
or mutates the live episode. Real deployments must provide observed history.
"""
import hashlib,json,time
import numpy as np
from sim_runtime import new_env,restore
from completion import Completion

def load_initial_object_history(case,bddl,initial_image,relocate,rgbd_file=None):
    started=time.monotonic();env=None
    try:
        env=new_env(bddl)
        if case['kind']=='new_revision':
            import h5py
            from sym_geometry import apply_scene_metadata
            source=relocate(case['source_hdf'])
            with h5py.File(source,'r') as f:
                metadata=json.loads(f.attrs['metadata_json'])
                state=np.asarray(f['states'][0])
            apply_scene_metadata(env,metadata)
            env.regenerate_obs_from_state(state)
        else:
            source=relocate(case['initial_state_file'])
            restore(env,dict(np.load(source)))
        rendered=np.ascontiguousarray(env.sim.render(width=256,height=256,camera_name='agentview')[::-1,::-1])
        supplied=np.asarray(initial_image)
        if supplied.shape!=(256,256,3):raise ValueError('Historical image must be native MAIN256')
        mae=float(np.abs(rendered.astype(float)-supplied.astype(float)).mean())
        if mae>3.:raise ValueError('Initial image/state mismatch: mean absolute RGB error '+str(mae))
        observed={}
        if rgbd_file is not None:
            from depth_sensor import read_depth
            depth,camera=read_depth(env)
            np.savez_compressed(rgbd_file,depth=depth,calibration=json.dumps(camera))
            observed=dict(initial_observed_rgbd_file=str(rgbd_file),depth_source='rendered sensor plus calibrated camera; no object/joint GT projection')
        mon=Completion(env,{},case['source_task'],case.get('previous_instruction',''));mon.observe(0)
        return dict(schema='episode_object_evidence.v1',episode_id=case['case_id'],source_episode_frame=0,
                    source='simulator_initial_state_for_validity_only',source_path=str(source),
                    camera_transform_id=mon.memory_camera_id(),facts=mon.memory_evidence(),
                    image_sha256=hashlib.sha256(supplied.tobytes()).hexdigest(),render_image_mae=mae,
                    seconds=time.monotonic()-started,**observed)
    finally:
        if env:env.close()
