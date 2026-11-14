"""Planning-only relation evidence. Never a completion or benchmark signal."""
import copy
import json
import math
from pathlib import Path


def trusted_relation_geometry(geometry,points,frame,confidence=.35):
    """Current image predictions only; use the unchanged S1 confidence level."""
    allowed=set()
    for point in points:
        if point.get('source')!='yolo_image_only'or point.get('frame',frame)!=frame:continue
        if min(point.get('det_confidence',0),point.get('keypoint_confidence',0))<confidence:continue
        yx=point.get('yx224')
        if yx is None or len(yx)!=2 or not all(math.isfinite(x)and 0<=x<=223 for x in yx):continue
        allowed.add(point['entity']+'.'+point['keypoint'])
    return{key:value for key,value in geometry.items()if key in allowed and value is not None
           and len(value)==3 and all(math.isfinite(x)for x in value)}


class PlanningRelationMemory:
    def __init__(self, log=None):
        self.log=None if log is None else Path(log)
        self.scope=None;self.last_frame=-1;self.scope_start=0;self.entry=None
        self.seen_visual=set();self.seen_completed=set();self.positive_frames=[];self.negative_frames=[]
        self.current_assessable=False;self.contradiction=None

    def record(self,event,frame,**data):
        if self.log:
            with self.log.open('a')as handle:
                handle.write(json.dumps(dict(event=event,frame=frame,**data))+'\n')

    def invalidate(self,frame,reason):
        if self.entry:
            self.record('invalidated',frame,reason=reason,previous=copy.deepcopy(self.entry))
        self.entry=None;self.positive_frames=[];self.negative_frames=[];self.contradiction=reason

    def establish(self,frame,source,evidence_frames):
        self.entry=dict(relation='bowl_drawer',last_observed_value=True,source_frame=frame,
                        evidence_frames=list(evidence_frames),source=source,
                        episode_id=self.scope[0],camera_id=self.scope[1],valid_for_planning=True,
                        planning_only=True,current_physical_completion_confirmed=False)
        self.contradiction=None
        self.record('established',frame,entry=copy.deepcopy(self.entry))

    def observe(self,episode_id,frame,camera,snapshot,geometry=None,active_stage=None,
                completed_events=(),visual_events=(),diagnostics=None):
        geometry=geometry or{};diagnostics=diagnostics or{}
        scope=(episode_id,camera)
        if scope!=self.scope or frame<self.last_frame:
            self.entry=None;self.seen_visual=set();self.seen_completed=set();self.positive_frames=[];self.negative_frames=[]
            self.scope=scope;self.scope_start=frame;self.last_frame=-1;self.contradiction=None
            self.record('scope_reset',frame,episode_id=episode_id,camera_id=camera)
        new_frame=frame>self.last_frame;self.last_frame=frame
        held=snapshot.get('held_object');op=(active_stage or{}).get('operation','')
        intervenes=held=='bowl' or op.startswith(('grasp_bowl','return_bowl','release_bowl')) or op in(
            'bowl_drawer','bowl_stove','bowl_cabinet','bowl_plate','open_top')
        near=(diagnostics.get('holding')or{}).get('near_px',{}).get('bowl')
        width=snapshot.get('robot',{}).get('gripper_width_m')
        if width is None:width=(diagnostics.get('holding')or{}).get('width_m')
        uncertain_bowl_contact=(held=='unknown'and near is not None and near<=26 and
                                width is not None and .002<=width<.060)
        if intervenes or uncertain_bowl_contact:
            self.invalidate(frame,'object_or_top_drawer_intervention'if intervenes else'uncertain_bowl_contact')
        top=snapshot.get('drawers',{}).get('top',{})
        a=geometry.get('bowl.K2');b=geometry.get('top_drawer_interior.K3')
        self.current_assessable=bool(top.get('open')is True and a is not None and b is not None)
        outside=False
        if self.current_assessable:
            delta=[float(x)-float(y)for x,y in zip(a,b)]
            outside=math.hypot(*delta[:2])>.045 or not(-.02<=delta[2]<=.065)
        if new_frame:
            self.negative_frames=(self.negative_frames+[frame])[-3:]if outside else[]
            if len(self.negative_frames)==3 and frame-self.negative_frames[0]>=8:
                self.invalidate(frame,'fresh_geometry_places_bowl_outside_open_drawer')
            elif outside:
                self.record('geometry_disagreement_pending_confirmation',frame,evidence_frames=list(self.negative_frames))
        # A raw False from the old proxy when the drawer is closed is not
        # outside-object evidence: that proxy also requires an OPEN drawer.
        if new_frame:
            positive=(not intervenes and not uncertain_bowl_contact and self.current_assessable and
                      snapshot.get('native_goal_relations',{}).get('bowl_drawer')is True)
            self.positive_frames=(self.positive_frames+[frame])[-3:]if positive else[]
            if len(self.positive_frames)==3 and frame-self.positive_frames[0]>=8:
                self.establish(frame,'s1_fresh_rgbd_relation_window',self.positive_frames)
        for event in visual_events:
            if event.get('event')!='image_inspection':continue
            source_frame=event.get('frame',-1)
            if source_frame<self.scope_start or source_frame>frame or source_frame in self.seen_visual:continue
            self.seen_visual.add(source_frame)
            pred=event.get('result')or{};location=pred.get('bowl_location')
            supported=pred.get('support_visible',{}).get('bowl')is True
            outside_visual=location in('table','stove','plate','cabinet_top','held')and(supported or pred.get('held_object')=='bowl')
            if outside_visual:
                self.invalidate(frame,'accepted_current_visual_observation_places_bowl_elsewhere')
            elif (source_frame==frame and not intervenes and not uncertain_bowl_contact and
                  top.get('open')is True and pred.get('relations',{}).get('bowl_drawer')is True and
                  location=='top_drawer'and supported and pred.get('held_object')in('none','cheese','wine_bottle','plate')):
                self.establish(source_frame,'accepted_image_observation_agent_relation',[source_frame])
        for event in completed_events:
            key=(event.get('operation'),event.get('confirmed_step'))
            if key in self.seen_completed:continue
            self.seen_completed.add(key)
            if event.get('confirmed_step',-1)<self.scope_start:continue
            operation=event.get('operation','')
            if event.get('outcome')!='completed':continue
            source=event.get('source','')
            if 'oracle'in source.lower()or'simulator'in source.lower():continue
            if operation=='bowl_drawer'and not intervenes:
                self.establish(event['confirmed_step'],'accepted_observed_container_completion',[event['confirmed_step']])
            elif operation.startswith(('grasp_bowl','return_bowl','release_bowl'))or operation in('bowl_stove','bowl_cabinet','bowl_plate','open_top'):
                self.invalidate(frame,'completed_observed_object_or_top_drawer_intervention')

    def planning_snapshot(self,current):
        result=copy.deepcopy(current)
        raw=current.get('native_goal_relations',{}).get('bowl_drawer')
        result['latest_relation_observations']=dict(bowl_drawer=raw,
            current_rgbd_assessable=self.current_assessable,contradiction=self.contradiction)
        hard_negative=self.contradiction in('fresh_geometry_places_bowl_outside_open_drawer',
            'accepted_current_visual_observation_places_bowl_elsewhere')
        if not self.current_assessable and raw is False and not hard_negative:
            result.setdefault('native_goal_relations',{})['bowl_drawer']=None
        if self.entry:
            result['relation_state_memory']=dict(bowl_drawer=copy.deepcopy(self.entry))
            result['relation_state_memory']['bowl_drawer'].update(current_frame=self.last_frame,
                age_control_steps=self.last_frame-self.entry['source_frame'],current_measurement=raw,
                invalidation_policy='new bowl manipulation, held bowl, top drawer reopening, fresh outside evidence, camera/episode change')
        return result


def effective_bowl_drawer(facts):
    raw=facts.get('native_goal_relations',{}).get('bowl_drawer')
    if raw is True or raw is False:return raw
    memory=facts.get('relation_state_memory',{}).get('bowl_drawer',{})
    if(memory.get('valid_for_planning')is True and memory.get('planning_only')is True and
       memory.get('last_observed_value')is True):return True
    return None


def handoff_context(inp,operation=None):
    facts=inp['physical_state'];robot=facts.get('robot')or{}
    event=(inp.get('completed_events')or[{}])[-1];previous=event.get('operation')
    level='top'if previous=='close_top'else'middle'if previous=='close_middle'else None
    distance=robot.get('hand_to_'+level+'_handle_m')if level else None
    width=robot.get('gripper_width_m')
    fresh=facts.get('observed_step')==inp['frame']
    already=event.get('confirmed_step')is not None and robot.get('handoff_for_close_step')==event.get('confirmed_step')
    ready=bool(level and fresh and event.get('outcome')=='completed'and facts.get('held_object')=='none'
               and width is not None and(width>=.065 or width<.002)
               and distance is not None and math.isfinite(distance)and 0<=distance<.12 and not already)
    if operation==previous:ready=False
    return dict(pending_existing_observation_handoff=ready,preceding_operation=previous,
                preceding_close_step=event.get('confirmed_step'),handle_distance_m=distance,
                gripper_width_m=width,measurements_fresh=fresh,already_performed=already,
                source='existing proprioception and fresh RGB-D; no new task goal',
                tool='observe_clear_cabinet',offset_m=.04)
