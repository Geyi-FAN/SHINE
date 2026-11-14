"""Causal static cache. Pixels are always YOLO predictions, never simulator projections."""
import json, os
import numpy as np

OBJECTS={'bowl','plate','cheese','wine_bottle'}
FIXED={'stove_placement','cabinet_top_placement','wine_rack_placement','table_front_placement'}
ANCHORS={(e,'K3') for e in FIXED} | {('stove_button','K1')}
DRAWER=('top_drawer_interior','K3')

def pose_deltas(a,b):
    """Object pose error in metres/degrees; q and -q denote the same rotation."""
    if a is None or b is None:return float('inf'),float('inf')
    a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
    if a.shape!=(7,) or b.shape!=(7,) or not np.isfinite(a).all() or not np.isfinite(b).all():return float('inf'),float('inf')
    na,nb=np.linalg.norm(a[3:]),np.linalg.norm(b[3:])
    if na<1e-12 or nb<1e-12:return float('inf'),float('inf')
    cosine=np.clip(abs(np.dot(a[3:]/na,b[3:]/nb)),0.,1.)
    return float(np.linalg.norm(a[:3]-b[:3])),float(np.degrees(2*np.arccos(cosine)))

def stationary_window(rows,translation_m,rotation_deg):
    if len(rows)<5:return False
    pose=rows[-1]['object_position']+rows[-1]['object_quaternion_wxyz']
    return all(r['support_contact'] and not r['target_contact'] and
               pose_deltas(r['object_position']+r['object_quaternion_wxyz'],pose)[0]<=translation_m and
               pose_deltas(r['object_position']+r['object_quaternion_wxyz'],pose)[1]<=rotation_deg for r in rows)

class SceneMemory:
    """Image-point history; validity is an estimate, never a simulator pose test."""
    def __init__(self,log_path,enabled=True,episode_id=None):
        from collections import deque
        self.path=log_path;self.enabled=enabled;self.episode_id=episode_id
        self.transfer_enabled=True;self.anchor_threshold=.5
        self.current={};self.cache={};self.anchors={};self.consensus={};self.pending={}
        self.facts={};self.counts={};self.imported_history=set();self.frame=-1;self.camera=None
        self.invalidated_entities=set();self.held='unknown';self.epoch=0
        self.configuration=dict(version='observable_static_cache_v1',validity_source='YOLO_temporal_consensus_and_robot_proprioception',
            oracle_validity_assisted=False,consensus_frames=3,consensus_span_steps=6,
            consensus_radius_px=3,minimum_confidence=.1,persistent_confidence=.5,
            missing_point_policy='same_camera_static_visual_estimate_until_contradiction',
            fixed_anchors='episode',dynamic_handles_cached=False)
        self.log('configuration',**self.configuration)
    def log(self,event,**kw):
        import json
        self.counts[event]=self.counts.get(event,0)+1
        with open(self.path,'a')as f:f.write(json.dumps(dict(event=event,frame=self.frame,**kw))+'\n')
    def evidence(self,frame,facts,camera):
        # facts is deliberately NOT inspected, serialized, or used for decisions.
        if frame<self.frame:raise ValueError('noncausal scene evidence')
        if self.camera is not None and self.camera!=camera:
            self.current.clear();self.cache.clear();self.anchors.clear();self.consensus.clear();self.pending.clear()
            self.log('invalidate_all',reason='camera_changed')
        if frame!=self.frame:self.current={}
        self.frame=frame;self.camera=camera
        self.facts={'source':'observable_memory_only'}
    def drop(self,key,reason):
        self.cache.pop(key,None);self.consensus.pop(key,None);self.pending.pop(key,None)
        self.invalidated_entities.add(key[0]);self.log('invalidate',entity=key[0],keypoint=key[1],reason=reason)
    def drop_anchor(self,key,reason):
        self.anchors.pop(key,None);self.log('anchor_invalidate',entity=key[0],keypoint=key[1],reason=reason)
    def observe_robot_state(self,snapshot,sample,physics_frame):
        import numpy as np
        self.held=snapshot.get('held_object','unknown')
        hand=sample.get('eef_yx');width=sample.get('width',1.)
        for key,entry in list(self.cache.items()):
            near=hand is not None and width<.065 and np.linalg.norm(np.asarray(hand)-np.asarray(entry['point']['yx224']))<12
            if key[0]==self.held or near:self.drop(key,'observed_grasp_or_closed_hand_near_object')
        top=snapshot.get('drawers',{}).get('top',{})
        if (top.get('closed_current') is True or top.get('open') is False) and DRAWER in self.anchors:
            self.drop_anchor(DRAWER,'visually_observed_drawer_closed')
    def _point(self,p,frame,time_source):
        import numpy as np
        try:
            e,k=p['entity'],p['keypoint'];xy=np.asarray(p['yx224'],float)
            confidence=min(float(p['det_confidence']),float(p['keypoint_confidence']))
            applicable=(e in OBJECTS and k in ('K1','K2','K3'))or(e in FIXED and k=='K3')or(e in ('top_handle','middle_handle','stove_button')and k=='K1')or((e,k)==DRAWER)
            if not applicable or xy.shape!=(2,)or not np.isfinite(xy).all()or np.any(xy<0)or np.any(xy>223)or not np.isfinite(confidence)or confidence<.1:return None
        except (KeyError,TypeError,ValueError):return None
        return dict(p,frame=frame,time_source=time_source,camera_transform_id=self.camera,validity_source='observable_visual_estimate')
    def _entry(self,p,kind):
        self.epoch+=1
        return dict(point=dict(p,cache_kind=kind),epoch_id=self.epoch)
    def acquire_anchor(self,p,frame,time_source):
        q=self._point(p,frame,time_source)
        if not q or not self.enabled:return
        key=(q['entity'],q['keypoint'])
        # Drawer interior is only acquired from repeated CURRENT detections below.
        if key not in ANCHORS or min(q['det_confidence'],q['keypoint_confidence'])<.5:return
        if key not in self.anchors:
            self.anchors[key]=self._entry(q,'episode_visual_anchor')
            self.log('anchor_acquire',entity=key[0],keypoint=key[1],source_frame=frame,oracle_validity_assisted=False)
    def seed_episode(self,points,frame=-1,camera=None):
        if camera is not None and camera!=self.camera:return
        for p in points:
            self.acquire_anchor(p,frame,'episode_start')
            q=self._point(p,frame,'episode_start')
            if not q:continue
            key=(q['entity'],q['keypoint'])
            if self.enabled and key[0]in OBJECTS and key[1]in ('K1','K3')and min(q['det_confidence'],q['keypoint_confidence'])>=.5:
                self.cache[key]=self._entry(q,'episode_visual_estimate')
                self.log('episode_object_seed',entity=key[0],keypoint=key[1],source_frame=frame,oracle_validity_assisted=False)
    def import_episode_objects(self,points,initial_facts,camera,episode_id,frame=-1):
        # No access to initial_facts: the live episode already retains its journal.
        if not self.enabled or episode_id!=self.episode_id or camera!=self.camera:return
        for p in points:
            key=(p['entity'],p['keypoint']);mark=(frame,)+key
            if mark in self.imported_history or key[0]in self.invalidated_entities:continue
            self.imported_history.add(mark)
            if key not in self.cache:self.seed_episode([p],frame,camera)
    def ingest(self,points,frame):
        import numpy as np
        if frame!=self.frame:raise ValueError('evidence/image frame mismatch')
        self.current={}
        for p in points:
            q=self._point(p,frame,'current')
            if not q:continue
            key=(q['entity'],q['keypoint']);xy=np.asarray(q['yx224'],float)
            previous=self.pending.get(key)
            if previous is not None:
                if frame<=previous[0]or np.linalg.norm(xy-np.asarray(previous[1]))>3:
                    self.pending[key]=(frame,xy.tolist());continue
                self.pending.pop(key,None)
            old=(self.anchors if key==DRAWER else self.cache).get(key)
            if old and np.linalg.norm(xy-np.asarray(old['point']['yx224']))>10:
                (self.drop_anchor(key,'visible_object_point_jump') if key==DRAWER else self.drop(key,'visible_object_point_jump'));self.pending[key]=(frame,xy.tolist());continue
            self.current[key]=q;self.acquire_anchor(q,frame,'current')
            cacheable=(key[0]in OBJECTS and key[1]in ('K1','K3')and key[0]!=self.held)or key==DRAWER
            if not self.enabled or not cacheable:continue
            rows=self.consensus.get(key,[])
            if rows and(frame<=rows[-1]['frame']or frame-rows[-1]['frame']>6 or np.linalg.norm(xy-np.asarray(rows[0]['yx224']))>3):
                if old:
                    if key==DRAWER:self.drop_anchor(key,'observed_interior_motion')
                    else:self.drop(key,'observed_motion_breaks_static_consensus')
                rows=[]
            rows=(rows+[q])[-3:];self.consensus[key]=rows
            if len(rows)==3 and frame-rows[0]['frame']>=6:
                best=max(rows,key=lambda z:min(z['det_confidence'],z['keypoint_confidence']))
                store=self.anchors if key==DRAWER else self.cache
                if key not in store:store[key]=self._entry(best,'visual_static_consensus')
                else:
                    old_point=store[key]['point']
                    if min(best['det_confidence'],best['keypoint_confidence'])>min(old_point['det_confidence'],old_point['keypoint_confidence']):
                        store[key]['point']=dict(best,cache_kind='visual_static_consensus')
                self.log('consensus_acquire',entity=key[0],keypoint=key[1],source_frame=store[key]['point']['frame'],evidence_frames=[z['frame']for z in rows],oracle_validity_assisted=False)
    def resolve(self,entity,keypoint):
        key=(entity,keypoint)
        if key in self.current:return self.current[key],'fresh'
        if self.enabled:
            entry=self.anchors.get(key)or self.cache.get(key)
            if entry:return dict(entry['point'],validity_status='cached_visual_estimate'),'cached'
        return None,'missing'
