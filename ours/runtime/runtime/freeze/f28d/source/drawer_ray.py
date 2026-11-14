"""Known drawer-axis calibration + fresh 2D point, without live object/joint truth."""
import numpy as np

def closed_consensus(estimates,frame):
 recent=[x for x in estimates if 0<=frame-x['frame']<=8]
 enough=len(recent)>=2 and recent[-1]['frame']-recent[0]['frame']>=4
 closed=enough and all(abs(x['gap_m'])<=.010 for x in recent)
 return dict(passed=bool(closed),estimates=recent,closed_tolerance_m=.010,
  reason='measured_closed_geometry' if closed else 'geometry_contradicts_closed' if recent and any(abs(x['gap_m'])>.010 for x in recent) else 'insufficient_fresh_geometry')

def estimate(point,cal,axis_reference):
 if point is None or cal is None or axis_reference is None:return None
 confidence=min(point.get('det_confidence',0),point.get('keypoint_confidence',0))
 if confidence<.35:return None
 y,x=(np.asarray(point['yx224'])+.5)/.875-.5;raw_y,raw_x=255-y,255-x
 ray=np.asarray(cal['rotation'])@np.array([(raw_x-127.5)/cal['focal'],(raw_y-127.5)/cal['focal'],-1.]);ray=ray/np.linalg.norm(ray)
 axis=np.asarray(axis_reference['opening_axis']);axis=axis/np.linalg.norm(axis);origin=np.asarray(axis_reference['xyz']);camera=np.asarray(cal['position'])
 A=np.stack([axis,-ray],axis=1)
 if np.linalg.cond(A)>20:return None
 q,depth=np.linalg.lstsq(A,camera-origin,rcond=None)[0];residual=float(np.linalg.norm(origin+q*axis-camera-depth*ray))
 if depth<=0 or residual>.012 or not -.035<=q<=.30:return None
 return dict(gap_m=float(q),ray_axis_residual_m=residual,point_confidence=float(confidence),source='fresh_YOLO_MAIN224_plus_fixed_camera_and_development_drawer_axis_calibration',assumptions='same calibrated cabinet and camera; point is the same handle reference; no live articulation/object pose',closed_tolerance_m=.010)
