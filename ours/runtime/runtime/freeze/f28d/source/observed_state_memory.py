"""Planning-only drawer state memory grounded in accepted events and fresh depth.

No simulator imports. Missing detections do not prove a state change. This class
never emits a completion event and never supplies cached completion geometry.
"""
import copy,json
from collections import deque
from pathlib import Path
from close_observation import current_candidate


class ObservedStateMemory:
    def __init__(self, calibration, log=None):
        self.references=calibration.get('closed_handles',{})
        self.camera=None;self.entries={};self.processed=set();self.pending_cameras={}
        self.windows={level:deque(maxlen=8) for level in ('top','middle')}
        self.log=None if log is None else Path(log)
    def record(self,event,**fields):
        if self.log:
            with self.log.open('a') as f:f.write(json.dumps(dict(event=event,**fields))+'\n')
    def update(self, frame, geometry, camera, active_stage, accepted_events):
        if self.camera is not None and camera!=self.camera:
            self.record('camera_changed',frame=frame);self.entries={}
            self.processed.update(self.pending_cameras);self.pending_cameras={}
            for window in self.windows.values():window.clear()
        self.camera=camera
        for level in self.windows:
            reference=self.references.get(level)
            gap=None if reference is None else current_candidate(geometry,level,reference)
            self.windows[level].append(dict(frame=frame,gap_m=gap))
        for event in accepted_events:
            operation=event.get('operation','')
            if event.get('outcome')!='completed' or not operation.startswith(('open_','close_')):continue
            if not operation.endswith(('top','middle')):continue
            key=(operation,event['confirmed_step'])
            if key in self.processed:continue
            level='top' if operation.endswith('top') else 'middle'
            state='open' if operation.startswith('open_') else 'closed'
            if key not in self.pending_cameras:self.pending_cameras[key]=camera
            opposite='close_'+level if state=='open' else 'open_'+level
            if self.pending_cameras[key]!=camera or (active_stage or {}).get('operation')==opposite:
                self.processed.add(key);self.pending_cameras.pop(key,None)
                self.record('pending_event_invalidated',frame=frame,operation=operation)
                continue
            from completion_proof import valid_drawer_proof
            if valid_drawer_proof(event):
                # Archive the SAME evidence already accepted by the completion
                # detector. Do not demand a second, different observation window
                # after switching the robot to another task.
                self.processed.add(key);self.pending_cameras.pop(key,None)
                self.entries[level]=dict(state=state,source_frame=event['confirmed_step'],completion_frame=event['confirmed_step'],
                    evidence_frames=list(event['completion_proof']['evidence_frames']),camera=camera,
                    evidence_source='accepted_completion_proof',completion_proof=copy.deepcopy(event['completion_proof']))
                self.record('established_from_accepted_completion_proof',frame=frame,level=level,**self.entries[level])
                continue
            window=list(self.windows[level])[-4:]
            enough=len(window)==4 and window[-1]['frame']-window[0]['frame']>=9
            enough=enough and all(x['gap_m'] is not None and (x['gap_m']>=.145 if state=='open' else abs(x['gap_m'])<=.010) for x in window)
            if not enough:
                self.record('event_not_archived_without_sustained_fresh_geometry',frame=frame,operation=operation,completion_frame=event['confirmed_step'])
                continue
            self.processed.add(key);self.pending_cameras.pop(key,None)
            self.entries[level]=dict(state=state,source_frame=frame,completion_frame=event['confirmed_step'],
                evidence_frames=[x['frame'] for x in window],camera=camera)
            self.record('established',frame=frame,level=level,**self.entries[level])
        for level,entry in list(self.entries.items()):
            op=(active_stage or {}).get('operation','')
            opposite='close_'+level if entry['state']=='open' else 'open_'+level
            if op==opposite:
                self.record('invalidated_new_intervention',frame=frame,level=level,operation=op)
                del self.entries[level];continue
            recent=list(self.windows[level])[-3:]
            changed=len(recent)==3 and recent[-1]['frame']-recent[0]['frame']>=8 and all(x['gap_m'] is not None and (x['gap_m']<.145 if entry['state']=='open' else abs(x['gap_m'])>.010) for x in recent)
            if changed:
                self.record('invalidated_sustained_measured_change',frame=frame,level=level,measurements=recent)
                del self.entries[level]
    def planning_snapshot(self, current):
        result=copy.deepcopy(current);details={}
        result['latest_drawer_observations']=copy.deepcopy(current.get('drawers',{}))
        for level,entry in self.entries.items():
            raw=current.get('drawers',{}).get(level,{})
            field='open' if entry['state']=='open' else 'closed_confirmed'
            if raw.get(field) is True:continue
            result.setdefault('drawers',{})[level]=dict(open=entry['state']=='open',closed_current=entry['state']=='closed',closed_confirmed=entry['state']=='closed')
            details[level]=dict(entry,evidence_source='cached_observed_state',planning_only=True,current_measurement=raw)
        if details:result['drawer_state_memory']=details
        return result
