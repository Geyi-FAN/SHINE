"""RGB-D sensor adapter. Camera calibration is allowed; object/joint state is not read."""
import numpy as np

def read_depth(env):
 sim=env.sim;rgb,buffer=sim.render(width=256,height=256,camera_name='agentview',depth=True)
 near=sim.model.vis.map.znear*sim.model.stat.extent;far=sim.model.vis.map.zfar*sim.model.stat.extent
 depth=near/(1.-np.asarray(buffer)*(1.-near/far))
 cid=sim.model.camera_name2id('agentview')
 calibration=dict(position=sim.data.cam_xpos[cid].tolist(),rotation=np.asarray(sim.data.cam_xmat[cid]).reshape(3,3).tolist(),focal=128./np.tan(np.deg2rad(sim.model.cam_fovy[cid])/2))
 return np.ascontiguousarray(depth[::-1,::-1]),calibration

def xyz_from_point(yx,depth,cal):
 y,x=(np.asarray(yx)+.5)/.875-.5;iy,ix=np.rint([y,x]).astype(int)
 if not (0<=iy<256 and 0<=ix<256):return None
 patch=depth[max(0,iy-1):min(256,iy+2),max(0,ix-1):min(256,ix+2)];good=patch[np.isfinite(patch)&(patch>.05)&(patch<5)]
 if len(good)<5 or np.percentile(good,90)-np.percentile(good,10)>.04:return None
 z=float(np.median(good));raw_y,raw_x=255-y,255-x
 local=np.array([(raw_x-127.5)*z/cal['focal'],(raw_y-127.5)*z/cal['focal'],-z])
 return (np.asarray(cal['position'])+np.asarray(cal['rotation'])@local).tolist()

def sensed_geometry(points,depth,cal,threshold=.35):
 out={}
 for p in points:
  if min(p.get('det_confidence',0),p.get('keypoint_confidence',0))<threshold:continue
  xyz=xyz_from_point(p['yx224'],depth,cal)
  if xyz is not None:out[p['entity']+'.'+p['keypoint']]=xyz
 return out
