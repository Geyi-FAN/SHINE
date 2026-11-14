"""Recovery admission and outcome evidence from fresh images/depth and proprioception.

No simulator, benchmark, object pose truth, or case-specific rules. These estimates
never declare task completion. Missing evidence stays unknown.
"""
import hashlib
import json
from dataclasses import dataclass
import numpy as np

PLACEMENTS={'cheese_bowl','bowl_drawer','bowl_stove','bowl_plate','bowl_cabinet','bottle_cabinet','bottle_rack'}

@dataclass(frozen=True)
class ProgressSettings:
    minimum_dwell: int = 120
    window_steps: int = 48
    minimum_span: int = 32
    minimum_rows: int = 7
    confirmation_steps: int = 8
    improvement_m: float = .008
    improvement_px: float = 5.
    local_horizontal_m: float = .065
    local_distance_m: float = .16
    followup_steps: int = 40


def entity_for(stage):
    op=stage['operation']
    return ('top_handle'if op.endswith('top')else'middle_handle')if op.startswith(('open_','close_'))else stage['object']


def camera_token(row):
    if row.get('camera_transform_id'):return row['camera_transform_id']
    cal=row.get('camera_calibration')
    return None if cal is None else hashlib.sha256(json.dumps(cal,sort_keys=True).encode()).hexdigest()[:16]


def point_in(row,entity,key='K1'):
    for p in row.get('image_points',[]):
        if p.get('entity')==entity and p.get('keypoint')==key and p.get('source')=='yolo_image_only' and p.get('frame',row['frame'])==row['frame'] and min(p.get('det_confidence',0),p.get('keypoint_confidence',0))>=.35:
            v=np.asarray(p.get('yx224',[]),float)
            if v.shape==(2,)and np.all(np.isfinite(v)):return v
    return None


def vector(value,n=3):
    if value is None:return None
    v=np.asarray(value,float)
    return v if v.shape==(n,)and np.all(np.isfinite(v))else None


def features(rows,stage):
    entity=entity_for(stage);out=[]
    for r in rows:
        sensor=r.get('sensor',{});pixel=point_in(r,entity);eef=vector(sensor.get('eef_xyz'));handpix=vector(sensor.get('eef_yx'),2)
        xyz=vector(r.get('geometry',{}).get(entity+'.K1'))if pixel is not None else None
        out.append(dict(frame=r['frame'],eef=eef,pixel=pixel,xyz=xyz,width=sensor.get('width'),
          distance_m=None if xyz is None or eef is None else float(np.linalg.norm(xyz-eef)),
          distance_px=None if pixel is None or handpix is None else float(np.linalg.norm(pixel-handpix))))
    return out


def median_ends(values,count=3):
    good=[x for x in values if x is not None and np.isfinite(x)]
    return (None,None)if len(good)<2*count else(float(np.median(good[:count])),float(np.median(good[-count:])))


class ProgressTracker:
    def __init__(self,settings=None,allow_vertical_approach=False):self.settings=settings or ProgressSettings();self.states={};self.allow_vertical_approach=allow_vertical_approach
    def evaluate(self,stage,entered,frame,rows,context,held='unknown',calibration=None):
        c=self.settings;rows=[r for r in rows if max(entered,frame-c.window_steps)<=r['frame']<=frame]
        rows=sorted({r['frame']:r for r in rows}.values(),key=lambda r:r['frame'])
        result=dict(frame=frame,operation=stage['operation'],entered_step=entered,status='insufficient_evidence',eligible=False,allowed_intents=[],creates_completion=False,
                    evidence_frames=[r['frame']for r in rows],reason='insufficient_causal_window')
        key=(stage['operation'],entered);state=self.states.setdefault(key,dict(stalled_since=None,camera=None))
        def stop(reason,status='insufficient_evidence'):
            state['stalled_since']=None;result.update(reason=reason,status=status);return result
        if frame-entered<c.minimum_dwell:return stop('minimum_execution_before_stall_review','warmup')
        if len(rows)<c.minimum_rows or rows[-1]['frame']!=frame or rows[-1]['frame']-rows[0]['frame']<c.minimum_span:return stop('insufficient_causal_window')
        if any(b['frame']-a['frame']>8 for a,b in zip(rows,rows[1:])):return stop('observation_gap')
        cameras={camera_token(r)for r in rows if camera_token(r)is not None}
        if len(cameras)>1:return stop('camera_changed_within_window')
        token=next(iter(cameras),None)
        if state['camera']is not None and token!=state['camera']:return stop('camera_identity_changed')
        state['camera']=token;result['camera_token']=token
        f=features(rows,stage);last=f[-1]
        if last['pixel']is None or sum(x['pixel']is not None for x in f)<.7*len(f):return stop('target_not_fresh_or_insufficient_coverage')
        positions=[x['pixel']for x in f if x['pixel']is not None]
        if any(np.linalg.norm(b-a)>30 for a,b in zip(positions,positions[1:])):return stop('target_identity_or_detection_jump')
        a,b=median_ends([x['distance_m']for x in f]);pa,pb=median_ends([x['distance_px']for x in f])
        delta_m=None if a is None else a-b;delta_px=None if pa is None else pa-pb
        target_pixel_motion=float(np.linalg.norm(np.median(positions[-3:],axis=0)-np.median(positions[:3],axis=0)))
        result.update(distance_gain_m=delta_m,distance_gain_px=delta_px,target_pixel_motion=target_pixel_motion)
        width=last['width'];op=stage['operation'];obj=stage['object']
        if stage['kind']=='target'and op not in PLACEMENTS:return stop('non_grasp_action_is_not_lost_ownership','out_of_local_scope')
        if held==obj and width is not None and .002<=width<.060:return stop('carried_object_requires_existing_completion_path','completion_pending'if stage['kind']=='grasp'else'normal_execution')
        if delta_m is not None and delta_m>=c.improvement_m:return stop('approach_distance_is_improving','progressing')
        if delta_px is not None and delta_px>=c.improvement_px:return stop('image_approach_is_improving','progressing')
        # Handle motion in a fixed MAIN view is evidence of ongoing interaction;
        # without complete 3D evidence do not interrupt it as if it were stuck.
        if op.startswith(('open_','close_')):
            level='top'if op.endswith('top')else'middle';ref=(calibration or{}).get('closed_handles',{}).get(level)
            if ref:
                from close_observation import current_candidate
                gaps=[current_candidate(r.get('geometry',{}),level,ref)for r in rows];ga,gb=median_ends(gaps)
                if ga is not None:
                    gain=(gb-ga)if op.startswith('open_')else(abs(ga)-abs(gb));result['drawer_gap_gain_m']=gain
                    if gain>=.006:return stop('drawer_motion_is_progressing','progressing')
            if target_pixel_motion>=3:return stop('visible_handle_is_moving','progressing')
        elif stage['kind']=='grasp':
            eef=[x['eef']for x in f if x['eef']is not None]
            if len(eef)>=6:
                zchange=float(np.median(np.array(eef[-3:])[:,2])-np.median(np.array(eef[:3])[:,2]));result['eef_z_change_m']=zchange
                if zchange<=-.008 and(delta_px is None or delta_px>=-2):return stop('ongoing_vertical_approach','progressing')
                xyz=[x['xyz']for x in f if x['xyz']is not None]
                if len(xyz)>=6 and np.median(np.array(xyz[-3:])[:,2])-np.median(np.array(xyz[:3])[:,2])>=.008:return stop('target_is_lifting','progressing')
        if last['xyz']is None:return stop('current_depth_not_available')
        xy=float(np.hypot(context['target_dx_m'],context['target_dy_m']));dist=float(np.linalg.norm([context['target_dx_m'],context['target_dy_m'],context['target_dz_m']]))
        closed=[x['width']is not None and x['width']<.002 for x in f]
        attempts=sum(not a and b for a,b in zip(closed,closed[1:]));result.update(target_xy_m=xy,target_distance_m=dist,observed_empty_closure_attempts=attempts)
        if stage['kind']=='target'and context.get('hand_empty')and context.get('target_supported')and context.get('outside_destination'):
            mode='lost_ownership';allowed=['reacquire']
        elif xy>c.local_horizontal_m or dist>c.local_distance_m:
            return stop('target_too_far_for_bounded_local_correction','out_of_local_scope')
        elif self.allow_vertical_approach and stage['kind']=='grasp'and xy<=.015 and context['target_dz_m']<=-.080 and width is not None and width>=.065 and context.get('hand_empty')and context.get('target_supported'):
            mode='vertical_standoff';allowed=['lower_approach']
        elif xy>.008:mode='position_offset';allowed=['align','clear_and_reapproach']
        elif attempts>=2 and context['target_dz_m']<=-.040:mode='repeated_close_without_lift';allowed=['orientation_test','clear_and_reapproach']
        else:return stop('no_supported_local_failure_diagnosis','insufficient_evidence')
        if state.get('failure_mode')!=mode:state['stalled_since']=None
        state['failure_mode']=mode
        if state['stalled_since']is None:state['stalled_since']=frame
        result.update(status='stalled',reason='sustained_no_progress',failure_mode=mode,allowed_intents=allowed,stalled_since=state['stalled_since'],
            orientation_test_allowed=mode=='repeated_close_without_lift',eligible=frame-state['stalled_since']>=c.confirmation_steps)
        return result


class ProgressReview:
    """Watch the resumed VLA; no extra hold, model calls, motion or completion."""
    def __init__(self,stage,entered,start,finish,before,intent,expected,camera=None,followup_steps=40):
        self.stage=dict(stage);self.entered=entered;self.start=start;self.finish=finish;self.before=dict(before);self.intent=intent;self.expected=expected;self.camera=camera;self.followup_steps=followup_steps
    def evaluate(self,frame,rows,events,current_stage=None,current_entered=None):
        if rows and self.camera is not None and camera_token(rows[-1])!=self.camera:return self._result(frame,'interrupted','camera_changed')
        valid=[e for e in events if e.get('outcome')=='completed'and e.get('confirmed_step',-1)>self.finish and 'oracle'not in e.get('source','').lower()and 'simulator'not in e.get('source','').lower()]
        same=[e for e in valid if e.get('operation')==self.stage['operation']and e.get('entered_step')==self.entered]
        reacquired=[e for e in valid if self.intent=='reacquire'and e.get('operation','').startswith('grasp_')and e.get('object')==self.stage['object']]
        if same or reacquired:return self._result(frame,'observed_stage_progress','existing_observation_detector_event')
        if current_stage is not None and self.intent!='reacquire'and(current_stage.get('operation')!=self.stage['operation']or current_entered!=self.entered):return self._result(frame,'interrupted','stage_changed_without_matching_observed_event')
        if frame-self.finish<self.followup_steps:return None
        recent=[r for r in rows if self.finish<=r['frame']<=frame][-3:]
        if len(recent)<3 or recent[-1]['frame']!=frame or recent[-1]['frame']-recent[0]['frame']<8:return self._result(frame,'insufficient_evidence','no_sustained_fresh_followup')
        f=features(recent,self.stage)
        if any(x['xyz']is None or x['eef']is None for x in f):return self._result(frame,'insufficient_evidence','target_depth_missing_after_correction')
        xy=float(np.median([np.linalg.norm((x['xyz']-x['eef'])[:2])for x in f]));before=float(np.hypot(self.before['target_dx_m'],self.before['target_dy_m']));gain=before-xy
        if self.intent in ('align','clear_and_reapproach')and gain>=.003:
            return dict(self._result(frame,'local_alignment_improved','sustained_image_depth_xy_error_reduction'),xy_gain_m=gain,task_recovered=False)
        if self.intent=='lower_approach':
            previous_height=-float(self.before['target_dz_m'])
            current_height=float(np.median([x['eef'][2]-x['xyz'][2]for x in f]))
            height_gain=previous_height-current_height
            return dict(self._result(frame,'local_approach_improved'if height_gain>=.003 else'no_confirmed_progress',
                'sustained_measured_vertical_standoff_reduction'if height_gain>=.003 else'no_sustained_vertical_approach_progress'),
                height_gain_m=height_gain,task_recovered=False)
        return dict(self._result(frame,'no_confirmed_progress','motion_executed_without_sustained_task_progress'),xy_gain_m=gain)
    def _result(self,frame,status,reason):return dict(frame=frame,event='code_progress_review',operation=self.stage['operation'],entered_step=self.entered,start=self.start,finish=self.finish,intent=self.intent,expected_progress=self.expected,status=status,reason=reason,creates_completion=False,task_recovered=False)
