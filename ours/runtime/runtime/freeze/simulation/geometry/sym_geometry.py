"""Shared offline/online read-only physical guards and MAIN grounding.

Mask centroids follow RoboMME's visible-object semantics. Floating centroids are
kept until the final text rounding. Semantic destinations are projected world
points, explicitly distinct from localization centroids.
"""
import numpy as np
import sym_paths
from sym_contract import OBJECTS, OBJ_ROLES, ROLES
from sim_runtime import GeometryRuntime
from restore_metrics import gates
import mujoco


def project(sim, xyz):
    cid=sim.model.camera_name2id('agentview')
    pos=np.asarray(sim.data.cam_xpos[cid]);rot=np.asarray(sim.data.cam_xmat[cid]).reshape(3,3)
    focal=128/np.tan(np.deg2rad(sim.model.cam_fovy[cid])/2)
    local=(np.asarray(xyz)-pos)@rot;depth=-local[2]
    if depth<=0:return np.zeros(2),False
    raw=127.5+focal*local[[1,0]]/depth
    yx=((255-raw)+.5)*.875-.5
    return yx,bool(np.isfinite(yx).all() and np.all(yx>=0) and np.all(yx<=223))


class Grounder:
    def __init__(self,env,plan):
        self.env=env;self.plan=plan;self.sim=env.sim;self.rt=GeometryRuntime()
        self.source=self.rt.monitor(env,plan['source']);self.target=self.rt.monitor(env,plan['target'])
        self.release_reference=None
        self.mask_ids={}
        for obj in OBJECTS:
            self.mask_ids[OBJ_ROLES[obj]]=[i for i,n in enumerate(self.sim.model.geom_names) if n and n.startswith(obj+'_')]
        for level in ('middle','top'):
            ids=[]
            for g in range(self.sim.model.ngeom):
                mid=int(self.sim.model.geom_dataid[g])
                if int(self.sim.model.geom_type[g])==int(mujoco.mjtGeom.mjGEOM_MESH) and mid>=0:
                    if level+'_handle' in self.sim.model.mesh_id2name(mid) and self.sim.model.geom_group[g]==1:ids.append(g)
            if len(ids)!=1:raise ValueError(('handle geom ambiguity',level,ids))
            self.mask_ids[level+'_handle']=ids
        # Stove button is an articulation body landmark, not the whole stove mask.
        jid=self.sim.model.joint_name2id('flat_stove_1_button')
        self.button_body=int(self.sim.model.jnt_bodyid[jid])
        self.mask_ids['stove_button']=[i for i in range(self.sim.model.ngeom)
            if int(self.sim.model.geom_bodyid[i])==self.button_body]
        if not self.mask_ids['stove_button']:raise ValueError('No stove-button geoms')

    def measure(self):
        sm=self.source.measure();tm=self.target.measure()
        if self.release_reference is None and self.plan['source_object']:
            self.release_reference=np.asarray(sm['all_object_poses'][self.plan['source_object']]['position']).copy()
        final=self.rt.frame(self.target,self.plan['target'])
        guards=[];restore25=False;clearance=False
        for stage in self.plan['stages']:
            kind=stage['kind']
            if kind in ('return','release'):
                obj=stage['object'];p=np.asarray(sm['all_object_poses'][obj]['position'])
                if not np.allclose(sm['object_position'],p,atol=1e-7,rtol=0):
                    raise ValueError(('Source monitor does not measure the required object',obj))
                if kind=='return':
                    ref=np.asarray(self.plan['initial_xyz'][obj]);restore25=all(gates(sm,ref,.025).values())
                    clearance=all(gates(sm,ref,.035).values()) and np.linalg.norm(np.asarray(sm['eef_position'])-p)>=.08
                    ok=restore25
                else:
                    ok=all(v for k,v in gates(sm,p,1).items() if k!='position')
            elif kind=='close':
                key=stage['joint'];pred=['turnoff','flat_stove_1'] if key=='stove' else ['close','wooden_cabinet_1_'+key+'_region']
                ok=self.env.env._eval_predicate(pred)
            elif kind=='open_top':ok=self.env.env._eval_predicate(['open','wooden_cabinet_1_top_region'])
            elif kind=='grasp':
                # A carried payload can contact the inside/bottom of its bowl.
                # Such internal assembly contact is not external support.
                payloads=[]
                for inv in self.plan['acceptance'].get('invariants',[]):
                    relation=inv.get('relation',[])
                    if inv['predicate']=='payload_relation_preserved' and len(relation)==3 and relation[2]==stage['object']:
                        payloads.append(relation[1])
                external_support=any(not any(any(g.startswith(obj+'_') for g in contact['pair']) for obj in payloads)
                                     for contact in tm['support_contacts'])
                ok=bool(tm['bilateral_finger_contact'] and not external_support and tm['target_contact'])
            elif kind in ('target','maintain'):ok=final['stable']
            else:raise ValueError(kind)
            guards.append(bool(ok))
        guards.extend([bool(final['goal']),bool(restore25),bool(clearance)])
        return np.asarray(guards,bool),sm,tm,final

    def destination(self):
        t=self.plan['target'];sim=self.sim
        sites={1:'flat_stove_1_cook_region',2:'wooden_cabinet_1_top_side',3:'wooden_cabinet_1_top_region',
               4:'wooden_cabinet_1_top_side',5:'main_table_stove_front_region',9:'wine_rack_1_top_region'}
        if t in sites:
            sid=sim.model.site_name2id(sites[t]);return np.asarray(sim.data.site_xpos[sid]).copy()
        if t in (6,8):
            obj=OBJECTS[0] if t==6 else OBJECTS[3]
            model=self.env.env.objects_dict[obj];bid=sim.model.body_name2id(model.root_body)
            # Named semantic center in the object's local frame. Bowl z=3cm is
            # inside the visible bowl mouth (top_site z=4cm in the source XML).
            local=np.array([0.,0.,.03 if t==6 else .005])
            return sim.data.body_xpos[bid]+sim.data.body_xmat[bid].reshape(3,3)@local
        return None

    def points(self):
        sim=self.sim
        seg=sim.render(width=256,height=256,camera_name='agentview',segmentation=True)[::-1,::-1]
        yx=np.zeros((len(ROLES),2),np.float32);valid=np.zeros(len(ROLES),bool)
        counts=np.zeros(len(ROLES),np.int32);world=np.full((len(ROLES),3),np.nan,np.float64)
        for role,ids in self.mask_ids.items():
            i=ROLES.index(role);mask=np.isin(seg[:,:,1],ids)&(seg[:,:,0]==int(mujoco.mjtObj.mjOBJ_GEOM))
            pixels=np.argwhere(mask);counts[i]=len(pixels)
            if len(pixels)>=10:
                yx[i]=(pixels.mean(0)+.5)*.875-.5
                valid[i]=bool(np.all(yx[i]>=0) and np.all(yx[i]<=223))
        refs={}
        if self.plan['restore_object']:refs['return_target']=self.plan['initial_xyz'][self.plan['restore_object']]
        if self.release_reference is not None:refs['release_target']=self.release_reference
        goal=self.destination()
        if goal is not None:refs['destination']=goal
        for role,p in refs.items():
            i=ROLES.index(role);world[i]=p;yx[i],valid[i]=project(sim,p)
        return yx,valid,counts,world


def apply_scene_metadata(env,metadata):
    """Only for disposable OFFLINE labeling environments, before any rollout."""
    fixtures=metadata.get('scene',{}).get('fixture_model_poses',{})
    for pose in fixtures.values():
        bid=env.sim.model.body_name2id(pose['root_body'])
        env.sim.model.body_pos[bid]=pose['body_pos'];env.sim.model.body_quat[bid]=pose['body_quat_wxyz']
    env.sim.forward()
