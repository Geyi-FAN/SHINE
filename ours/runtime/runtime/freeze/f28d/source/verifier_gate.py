"""Resource admission only. Existing S1 decisions and acceptance guards stay intact."""
import math


class VerifierGate:
    def __init__(self,periodic_limit=2):
        if periodic_limit not in(1,2):raise ValueError('Research periodic limit must be1or2; total stage cap stays6')
        self.states={};self.events=[];self.periodic_limit=periodic_limit
    def permit(self,stage,entered,frame,rows,trigger,is_candidate,post_guard,recovery_epoch=-1):
        key=(stage['operation'],entered);s=self.states.setdefault(key,dict(calls=0,periodic_calls=0,last=-10000,fingerprint=None,previous_guard=None,recovery_epoch=-1))
        new_positive=post_guard is True and s['previous_guard']is not True
        new_view=recovery_epoch>max(entered,s['recovery_epoch'])and frame>=recovery_epoch
        reason='admit';strong=trigger in ('confirm_visual_candidate','confirm_observation_candidate')or is_candidate or new_positive or new_view
        s['previous_guard']=post_guard
        if s['calls']>=6:reason='stage_call_limit6'
        elif post_guard is False:reason='unchanged_independent_guard_would_reject'
        current=rows[-1]if rows else{};sensor=current.get('sensor',{})
        entity=('top_handle'if stage['operation'].endswith('top')else'middle_handle')if stage['operation'].startswith(('open_','close_'))else stage['object']
        point=next((p for p in current.get('image_points',[])if p.get('entity')==entity and p.get('keypoint')=='K1'),None)
        position=point.get('yx224')if point else None
        fingerprint=(sensor.get('width',0)>=.065,point is not None,
            None if position is None else tuple(int(round(float(v)/6))for v in position),
            tuple(int(round(float(v)/.015))for v in sensor.get('eef_xyz',[])),post_guard)
        elapsed=frame-s['last']
        if reason=='admit'and not strong:
            if s['periodic_calls']>=self.periodic_limit:reason='reserve_four_calls_for_candidates_or_new_views'if self.periodic_limit==2 else'reserve_five_calls_for_candidates_or_new_views'
            elif elapsed<48:reason='minimum_interval48'
            elif s['calls']and fingerprint==s['fingerprint']and elapsed<180:reason='no_material_new_evidence'
            elif frame-entered<96 and post_guard is not True:reason='wait_for_candidate_or_bounded_dwell'
        permit=reason=='admit'
        # Log a state change or actual admission, not thousands of identical skips.
        if permit or s.get('last_reason')!=reason:self.events.append(dict(operation=key[0],entered=entered,frame=frame,trigger=trigger,allowed=permit,reason=reason,calls_before=s['calls']))
        s['last_reason']=reason
        if permit:
            s.update(calls=s['calls']+1,last=frame,fingerprint=fingerprint,recovery_epoch=max(s['recovery_epoch'],recovery_epoch))
            if not strong:s['periodic_calls']+=1
        return permit
