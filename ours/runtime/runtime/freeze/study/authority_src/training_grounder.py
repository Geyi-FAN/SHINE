"""Exact training point projection, with no drawer-handle GT or image arrows."""
import numpy as np
from benchmark_execution.legacy_boundary_plan import OBJECTS,ROLES

def project(sim,xyz):
 cid=sim.model.camera_name2id('agentview');pos=sim.data.cam_xpos[cid];rot=sim.data.cam_xmat[cid].reshape(3,3);local=(np.asarray(xyz)-pos)@rot;depth=-local[2]
 if depth<=0:return np.zeros(2),False
 focal=128/np.tan(np.deg2rad(sim.model.cam_fovy[cid])/2);p=((255-(127.5+focal*local[[1,0]]/depth))+.5)*.875-.5
 return p,bool(np.isfinite(p).all() and (p>=0).all() and (p<=223).all())

class TrainingGrounder:
 def __init__(self,env,plan):
  self.env=env;self.sim=env.sim;self.plan=plan;self.core=env.env
  self.ids={ROLES[i]:[g for g,n in enumerate(self.sim.model.geom_names) if n and n.startswith(obj+'_')] for i,obj in enumerate(OBJECTS)}
  jid=self.sim.model.joint_name2id('flat_stove_1_button');body=self.sim.model.jnt_bodyid[jid];self.ids['stove_button']=np.flatnonzero(self.sim.model.geom_bodyid==body).tolist()

 def points(self):
  sim=self.sim;seg=sim.render(width=256,height=256,camera_name='agentview',segmentation=True)[::-1,::-1]
  p=np.zeros((10,2),np.float32);v=np.zeros(10,bool)
  for role,ids in self.ids.items():
   pixels=np.argwhere(np.isin(seg[:,:,1],ids)&(seg[:,:,0]==5))
   if len(pixels)>=10:
    i=ROLES.index(role);p[i]=(pixels.mean(0)+.5)*.875-.5;v[i]=bool((p[i]>=0).all() and (p[i]<=223).all())
  refs={};restore=next((c for c in self.plan['contract']['clauses'] if c['kind']=='restore_episode_start'),None)
  if restore:refs['return_target']=restore['reference_position']
  t=self.plan['target'];sites={1:'flat_stove_1_cook_region',2:'wooden_cabinet_1_top_side',3:'wooden_cabinet_1_top_region',4:'wooden_cabinet_1_top_side',5:'main_table_stove_front_region',9:'wine_rack_1_top_region'}
  if t in sites:refs['destination']=sim.data.get_site_xpos(sites[t]).copy()
  elif t in [6,8]:
   obj=OBJECTS[0] if t==6 else OBJECTS[3];model=self.core.objects_dict[obj];bid=sim.model.body_name2id(model.root_body);refs['destination']=sim.data.body_xpos[bid]+sim.data.body_xmat[bid].reshape(3,3)@np.array([0.,0.,.03 if t==6 else .005])
  for role,xyz in refs.items():i=ROLES.index(role);p[i],v[i]=project(sim,xyz)
  return p,v
