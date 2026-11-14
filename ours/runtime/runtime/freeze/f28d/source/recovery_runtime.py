"""Observation recovery bookkeeping. No hidden next stage or GT point fallback."""
import copy
from recovery_observer import RecoveryObserver

class RecoveryRuntime:
    def __init__(self, folder, user_message):
        self.observer=RecoveryObserver(folder);self.user_message=user_message
        self.events=[];self.inspection_limit=8;self.replans=0;self.inspections=0;self.last_check=-1000;self.visual_facts=None
        self.pending=None;self.grip_release_until=None;self.release_requested_at=None
        self.missing_since=None;self.missing_attempts=0;self.missing_inspections=0
        self.empty_hand_proof=None
    def point_recovered(self, frame, reference, marker):
        if self.missing_since is None:return
        self.events.append(dict(frame=frame,event='missing_point_recovered',reference=reference,
            interruption_start=self.missing_since,interruption_steps=frame-self.missing_since,
            resolution=marker.get('resolution'),source_frame=marker.get('source_frame'),
            note='Successful reacquisition ends this consecutive recovery episode; not stage completion'))
        self.missing_since=None;self.missing_attempts=0;self.missing_inspections=0
    def inspect(self, mon):
        # A new control observation is required for a corroborating call.
        if self.inspections>=getattr(self,'inspection_limit',4) or mon.last-self.last_check<8:return None
        result=self.observer.check(self.user_message,list(mon.rgb_rows),mon.diagnostics)
        self.inspections+=1;self.last_check=mon.last
        if not result['accepted']:return None
        pred=result['response'];previous=self.visual_facts;self.visual_facts=dict(pred,frame=mon.last)
        self.events.append(dict(frame=mon.last,event='image_inspection',result=pred))
        from empty_hand_evidence import certify
        self.empty_hand_proof=certify(list(mon.rgb_rows),mon.last,pred,previous)
        if self.empty_hand_proof:
            self.events.append(dict(frame=mon.last,event='observed_empty_hand_certified',proof=self.empty_hand_proof))
        if pred['held_object']!='unknown' and not (pred['held_object']=='none' and .002<=mon.samples[-1]['width']<.060 and self.empty_hand_proof is None):
            # This is an estimated current holding label, not a completion event.
            mon.held=pred['held_object'];mon.last_held_frame=mon.last
            mon.held_width=mon.samples[-1]['width'] if mon.held!='none' else None
            mon.snapshot['held_object']=mon.held
            if self.empty_hand_proof:mon.snapshot['ownership_observation_memory']=dict(self.empty_hand_proof)
        if pred.get('bowl_location') not in (None,'unknown'):
            mon.snapshot['observed_scene_context']=dict(bowl_location=pred['bowl_location'],observation_frame=mon.last,source='image_observation_agent; not simulator truth')
        for relation,value in pred.get('relations',{}).items():
            if value is True or value is False:mon.snapshot['native_goal_relations'][relation]=value
        held=pred.get('release_object') or pred.get('held_object');width=mon.samples[-1]['width']
        # Release only after independent NEW-FRAME corroboration, near-hand target,
        # measured non-empty closed fingers and visible existing support in both calls.
        release=(previous is not None and mon.last-previous['frame']>=8 and
            held in ('bowl','cheese','wine_bottle','plate') and (previous.get('release_object') or previous.get('held_object'))==held and
            pred.get('recovery_request')=='release_supported_in_place' and
            previous.get('recovery_request')=='release_supported_in_place' and
            pred.get('support_visible',{}).get(held) is True and previous.get('support_visible',{}).get(held) is True and
            .002<=width<.060 and (mon.diagnostics.get('holding',{}).get('near_px',{}).get(held) or 1000)<=26)
        if release:
            self.grip_release_until=mon.last+16;self.release_requested_at=mon.last
            self.events.append(dict(frame=mon.last,event='agent_requested_supported_release',object=held,
                evidence_frames=[previous['frame'],mon.last],controller='pose hold + fingers open; no Cartesian relocation'))
        return pred
    def apply_visual_facts(self, mon):
        if not self.visual_facts:return
        # Short-lived observation memory, never an indefinitely authoritative label.
        p=self.visual_facts
        if mon.last-p['frame']>24:return
        from empty_hand_evidence import measured_clearance
        fresh_clear=measured_clearance(list(mon.rgb_rows),mon.last)if self.empty_hand_proof is not None else None
        if mon.held=='unknown' and p.get('held_object')!='unknown' and not (p.get('held_object')=='none' and .002<=mon.samples[-1]['width']<.060 and fresh_clear is None):
            mon.held=p['held_object'];mon.last_held_frame=mon.last;mon.snapshot['held_object']=mon.held
            if fresh_clear:mon.snapshot['ownership_observation_memory']=dict(self.empty_hand_proof,revalidated_frame=mon.last)
        if p.get('bowl_location') not in (None,'unknown'):
            mon.snapshot['observed_scene_context']=dict(bowl_location=p['bowl_location'],observation_frame=p['frame'],source='image_observation_agent; not simulator truth')
        for relation,value in p.get('relations',{}).items():
            if value is True and mon.snapshot['native_goal_relations'].get(relation) is None:
                mon.snapshot['native_goal_relations'][relation]=value
