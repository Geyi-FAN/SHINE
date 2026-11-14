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
    def __init__(self,log_path,enabled=True,episode_id=None):
        self.episode_id=episode_id
        self.imported_history=set()
        self.transfer_enabled=os.environ.get('HYBRID_EPISODE_OBJECT_MEMORY','1')=='1'
        self.anchor_threshold=float(os.environ.get('HYBRID_ANCHOR_CONF','0.5'))
        if not .1<=self.anchor_threshold<=1:raise ValueError('anchor confidence must be in [0.1,1]')
        self.object_translation=float(os.environ.get('HYBRID_OBJECT_CACHE_TRANSLATION_M','0.005'))
        self.object_rotation=float(os.environ.get('HYBRID_OBJECT_CACHE_ROTATION_DEG','5'))
        if not 0<self.object_translation<=.05 or not 0<self.object_rotation<=45:raise ValueError('invalid object cache pose tolerances')
        self.anchors={}
        self.counts={};self.enabled=enabled;self.path=log_path;self.cache={};self.current={};self.facts={};self.camera=None;self.frame=-1;self.pending={}
        self.configuration=dict(version='episode_object_transfer_v1',episode_object_transfer=self.transfer_enabled,persistent_confidence=self.anchor_threshold,
                                object_translation_m=self.object_translation,object_rotation_deg=self.object_rotation,
                                selection='highest_min_detection_keypoint_confidence_in_static_epoch')
        self.log('configuration',**self.configuration)
    def log(self,event,**kw):
        name=event+(':'+kw['resolution'] if event=='resolve' else '')
        self.counts[name]=self.counts.get(name,0)+1
        with open(self.path,'a') as f:f.write(json.dumps(dict(event=event,frame=self.frame,**kw))+'\n')
    def evidence(self,frame,facts,camera):
        if frame<self.frame:raise ValueError('noncausal scene evidence')
        if frame!=self.frame:self.current={}
        self.frame=frame
        if self.camera is not None and camera!=self.camera:
            for key in list(self.cache):self.drop(key,'camera_changed')
            for key in list(self.anchors):self.drop_anchor(key,'camera_changed')
            self.current={};self.pending={}
        self.camera=camera;self.facts=facts
        if DRAWER in self.anchors:
            f=facts.get(DRAWER[0],{})
            if not f.get('static') or not self.same_pose(self.anchors[DRAWER]['pose'],f.get('pose')):self.drop_anchor(DRAWER,'drawer_moved_closed_or_evidence_missing')
        for key,entry in list(self.cache.items()):
            f=facts.get(key[0],{})
            translation,rotation=pose_deltas(entry['pose'],f.get('pose'))
            reason=None
            if not f.get('cache_reusable',f.get('static',False)):reason='grasp_support_loss_or_missing_evidence'
            elif translation>self.object_translation or rotation>self.object_rotation:reason='object_moved_from_static_epoch_origin'
            if reason:
                self.log('object_cache_invalidity',entity=key[0],keypoint=key[1],reason=reason,
                         translation_m=translation if np.isfinite(translation) else None,
                         rotation_deg=rotation if np.isfinite(rotation) else None,
                         translation_limit_m=self.object_translation,rotation_limit_deg=self.object_rotation)
                self.drop(key,reason)
    def drop_anchor(self,key,reason):
        self.anchors.pop(key,None)
        self.log('anchor_invalidate',entity=key[0],keypoint=key[1],reason=reason)
    def acquire_anchor(self,p,frame,time_source):
        key=(p['entity'],p['keypoint'])
        if not self.enabled or key in self.anchors:return
        if key not in ANCHORS and key!=DRAWER:return
        xy=np.asarray(p['yx224'],float)
        if xy.shape!=(2,) or not np.isfinite(xy).all() or np.any(xy<0) or np.any(xy>223):return
        if not np.isfinite([p['det_confidence'],p['keypoint_confidence']]).all() or min(p['det_confidence'],p['keypoint_confidence'])<self.anchor_threshold:return
        pose=None
        if key==DRAWER:
            # Historical image alone cannot establish the current drawer configuration.
            f=self.facts.get(key[0],{})
            if time_source!='current' or not f.get('static'):return
            pose=list(f['pose'])
        value=dict(p,frame=frame,time_source=time_source,camera_transform_id=self.camera,
                   cache_kind='stage_anchor' if key==DRAWER else 'episode_anchor')
        self.anchors[key]=dict(point=value,pose=pose)
        self.log('anchor_acquire',entity=key[0],keypoint=key[1],source_frame=frame,
                 source_time_source=time_source,yx224=xy.tolist(),cache_kind=value['cache_kind'],
                 det_confidence=p['det_confidence'],keypoint_confidence=p['keypoint_confidence'])
    def seed_episode(self,points,frame=-1,camera=None):
        if camera is not None and camera!=self.camera:
            self.log('history_reject',reason='camera_mismatch',source_frame=frame)
            return
        for p in points:self.acquire_anchor(p,frame,'episode_start')
    def import_episode_objects(self,points,initial_facts,camera,episode_id,frame=-1):
        """Import image-only K1/K3 with private initial/current validity evidence.

        A one-time snapshot warm start, NOT a recurring GT fallback. A live
        episode normally retains this same SceneMemory across instructions.
        """
        if not self.enabled or not self.transfer_enabled:return
        if self.episode_id is None or episode_id!=self.episode_id:
            self.log('history_reject',reason='episode_mismatch',source_frame=frame);return
        if camera!=self.camera:
            self.log('history_reject',reason='camera_mismatch',source_frame=frame);return
        if frame>self.frame:raise ValueError('future episode history')
        for p in points:
            key=(p['entity'],p['keypoint']);history_key=(frame,)+key
            if key[0] not in OBJECTS or key[1] not in ('K1','K3'):continue
            if history_key in self.imported_history:
                self.log('history_reject',entity=key[0],keypoint=key[1],reason='history_already_considered');continue
            self.imported_history.add(history_key)
            initial=initial_facts.get(key[0],{});current=self.facts.get(key[0],{})
            delta,angle=pose_deltas(initial.get('pose'),current.get('pose'))
            xy=np.asarray(p['yx224'],float);confidence=min(p['det_confidence'],p['keypoint_confidence'])
            reason=None
            if xy.shape!=(2,) or not np.isfinite(xy).all() or np.any(xy<0) or np.any(xy>223):reason='invalid_pixels'
            elif not np.isfinite([p['det_confidence'],p['keypoint_confidence']]).all() or confidence<self.anchor_threshold:reason='low_history_confidence'
            elif not initial.get('cache_reusable') or not current.get('cache_reusable'):reason='grasp_support_loss_or_missing_history_evidence'
            elif delta>self.object_translation or angle>self.object_rotation:reason='object_pose_changed_since_episode_start'
            if reason:
                self.log('history_reject',entity=key[0],keypoint=key[1],reason=reason,source_frame=frame,
                         translation_m=delta if np.isfinite(delta) else None,rotation_deg=angle if np.isfinite(angle) else None)
                continue
            old=self.cache.get(key)
            if old and min(old['point']['det_confidence'],old['point']['keypoint_confidence'])>=confidence:continue
            value=dict(p,frame=frame,time_source='episode_start',camera_transform_id=camera,
                       cache_kind='episode_object',source_episode_frame=0)
            self.cache[key]=dict(point=value,pose=list(initial['pose']))
            self.log('history_import',entity=key[0],keypoint=key[1],source_frame=frame,source_time_source='episode_start',
                     confidence=confidence,yx224=xy.tolist(),translation_m=delta,rotation_deg=angle,cache_kind='episode_object')
    @staticmethod
    def same_pose(a,b):
        if a is None or b is None:return False
        a=np.asarray(a);b=np.asarray(b)
        return a.shape==b.shape and bool(np.max(np.abs(a-b))<=1e-5)
    def drop(self,key,reason):
        self.cache.pop(key,None);self.pending.pop(key,None);self.log('invalidate',entity=key[0],keypoint=key[1],reason=reason)
    def ingest(self,points,frame):
        if frame!=self.frame:raise ValueError('evidence/image frame mismatch')
        self.current={}
        for p in points:
            e,k=p['entity'],p['keypoint'];key=(e,k);yx=np.asarray(p['yx224'],float)
            applicable=(e in OBJECTS and k in ('K1','K2','K3')) or (e in FIXED and k=='K3') or (e in ('top_handle','middle_handle','stove_button') and k=='K1') or (e=='top_drawer_interior' and k=='K3')
            if not applicable or yx.shape!=(2,) or not np.isfinite(yx).all() or np.any(yx<0) or np.any(yx>223) or not np.isfinite([p['det_confidence'],p['keypoint_confidence']]).all() or p['det_confidence']<.1 or p['keypoint_confidence']<.1:
                self.log('reject',entity=e,keypoint=k,reason='invalid_slot_bounds_or_confidence');continue
            self.acquire_anchor(p,frame,'current')
            f=self.facts.get(e,{})
            eligible=self.enabled and (e in OBJECTS and k in ('K1','K3')) and f.get('static',False)
            old=self.cache.get(key)
            if self.enabled and old and f.get('cache_reusable',f.get('static',False)) and np.linalg.norm(yx-np.asarray(old['point']['yx224']))>10:
                previous=self.pending.get(key)
                self.pending[key]=(frame,yx.tolist())
                if previous is None or previous[0]>=frame or np.linalg.norm(yx-np.asarray(previous[1]))>3:
                    self.log('reject',entity=e,keypoint=k,reason='static_pixel_jump',candidate=yx.tolist());continue
            self.pending.pop(key,None)
            value=dict(p,frame=frame,time_source='current',camera_transform_id=self.camera)
            self.current[key]=value
            confidence=min(p['det_confidence'],p['keypoint_confidence'])
            if eligible and confidence>=self.anchor_threshold:
                # Keep the static epoch origin: refreshing a pixel must not allow
                # arbitrarily large cumulative motion to evade invalidation.
                previous_confidence=-1 if old is None else min(old['point']['det_confidence'],old['point']['keypoint_confidence'])
                if confidence>previous_confidence:
                    self.cache[key]=dict(point=dict(value,cache_kind='stationary_object'),pose=list(f['pose']) if old is None else old['pose'])
                    self.log('update',entity=e,keypoint=k,source_frame=frame,yx224=yx.tolist(),confidence=confidence,cache_kind='stationary_object')
                else:self.log('retain_best',entity=e,keypoint=k,source_frame=old['point']['frame'],candidate_frame=frame,confidence=previous_confidence,candidate_confidence=confidence)
    def resolve(self,entity,keypoint):
        key=(entity,keypoint)
        if self.enabled and key in self.anchors:
            p=self.anchors[key]['point']
            return p,'fresh' if p['frame']==self.frame and p['time_source']=='current' else 'cached'
        if key in self.current:return self.current[key],'fresh'
        if self.enabled and key in self.cache:return self.cache[key]['point'],'cached'
        return None,'missing'
