"""Candidate completion observation gate. Robot sensors + fresh YOLO only."""
import numpy as np
from scipy.spatial.transform import Rotation
from observed_completion import distance,DESTINATIONS
class PoseHold:
 def __init__(self,obs,controller):
  if not controller.use_delta:raise ValueError('Hold adapter requires delta OSC')
  self.xyz=np.array(obs['robot0_eef_pos']);self.rot=Rotation.from_quat(obs['robot0_eef_quat']).as_matrix()
  self.scale=(np.array(controller.output_max)-np.array(controller.output_min))/2
  if len(self.scale)!=6 or np.any(self.scale<=0):raise ValueError('Unexpected controller scaling')
 def action(self,obs):
  cur=Rotation.from_quat(obs['robot0_eef_quat']).as_matrix();delta=np.r_[self.xyz-np.array(obs['robot0_eef_pos']),Rotation.from_matrix(self.rot@cur.T).as_rotvec()]
  return np.r_[np.clip(delta/self.scale,-1,1),0.].tolist() # Panda gripper 0 retains existing actuator target.
 def drift(self,obs):return float(np.linalg.norm(np.array(obs['robot0_eef_pos'])-self.xyz))
class CandidateGate:
 def __init__(self,event,stage,frame,obs,controller):
  self.event=dict(event);self.stage=dict(stage);self.start=frame;self.pose=PoseHold(obs,controller);self.rows=[];self.max_drift=0.
 def check(self,mon,frame,obs):
  s=mon.samples[-1];c=mon.settings;obj=self.stage['object'];kind=self.stage['kind'];checks={};self.max_drift=max(self.max_drift,self.pose.drift(obs))
  if kind=='grasp':
   p=mon.point(s,obj,'K1');checks={'visible':None if p is None else True,'closed':c.min_width_m<=s['width']<c.closed_width_m,'ownership':mon.held==obj,'near_hand':None if p is None or s['eef_yx'] is None else distance(p,s['eef_yx'])<=c.near_hand_px}
  else:
   p=mon.point(s,obj);ref=mon._history_point('episode_start' if kind=='return' else 'instruction_takeover',obj) if kind in ('return','release') else None
   if self.stage['operation'] in DESTINATIONS:
    target=DESTINATIONS[self.stage['operation']][1];ref=mon.point(s,target,'K3')
    if ref is None and target.endswith('placement'):ref=mon._history_point('episode_start',target,'K3')
   k1=mon.point(s,obj,'K1');checks={'open':s['width']>=c.open_width_m,'location':None if p is None or ref is None else distance(p,ref)<=(c.return_radius_px if kind in ('return','release') else c.place_radius_px),'stable':None if p is None else mon.stable(obj),'separation':None if k1 is None or s['eef_yx'] is None else distance(k1,s['eef_yx'])>=c.clear_px}
  ok=all(v is True for v in checks.values());self.rows.append({'frame':frame,'checks':checks,'ok':ok});recent=self.rows[-4:]
  accepted=len(recent)==4 and recent[-1]['frame']-recent[0]['frame']>=9 and all(x['ok'] for x in recent)
  if accepted:return 'accept'
  if frame-self.start>=18:return 'resume'
  return 'observe'
