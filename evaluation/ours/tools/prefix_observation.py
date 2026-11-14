"""Rebuild method memory from real RGB-D, YOLO and proprioception only.

No simulator object poses/holding labels, private predicates or completion
history are consumed. The benchmark preparer does not tell the Agent a stage.
"""
import json,os
import numpy as np

def observe(bridge):
 b=bridge;points=b.saved_points;frame=b.physics_steps
 mon=b.saved_mon
 if mon is not None and frame<=mon.last:return
 points.update_evidence(frame,{},b.cache_reader.memory_camera_id())
 points.observe(np.ascontiguousarray(b.obs['agentview_image'][::-1,::-1]),frame)
 if mon is None:
  mon=b.saved_mon=b.mon_class(history=dict(points.memory),settings=b.runner.Settings(confidence=float(os.environ.get('S1_POINT_CONF','0.35'))))
 eef=np.asarray(b.obs['robot0_eef_pos']);yx,valid=b.runner.project(b.env.sim,eef)
 depth,cal=b.runner.read_depth(b.env)
 geometry=b.runner.sensed_geometry(list(points.current.values()),depth,cal)
 mon.supply(frame,b.runner.resize(np.ascontiguousarray(b.obs['agentview_image'][::-1,::-1])),
            b.runner.resize(np.ascontiguousarray(b.obs['robot0_eye_in_hand_image'][::-1,::-1])),geometry)
 mon.rgb_rows[-1]['camera_calibration']=cal
 mon.rgb_rows[-1]['image_points']=list(points.current.values())
 # No stage is selected during the external preparer, so this cannot invent a
 # completed grasp/return/close event. Ownership is an observed sensor estimate.
 assert mon.active is None,'do_not_override_method_stage'
 event=mon.observe(frame,eef.tolist(),np.asarray(b.obs['robot0_gripper_qpos']).tolist(),yx.tolist()if valid else None,list(points.current.values()))
 assert event is None
 points.scene.observe_robot_state(mon.snapshot,mon.samples[-1],frame)
 with(b.root/'PREPARATION_OBSERVED_MEMORY.jsonl').open('a')as f:
  f.write(json.dumps(dict(frame=frame,source='actual_YOLO_RGBD_robot_proprio',held_estimate=mon.held,
       holding_evidence=mon.holding_evidence,creates_completion=False,private_simulator_labels_used=False))+'\n')
