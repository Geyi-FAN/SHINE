"""Measurement-only revision events. Never changes a command or simulator state."""
import numpy as np


class RevisionEvents:
    def __init__(self, contract, initial, at_switch, target, instruction):
        self.ct=contract;self.initial=initial;self.at=at_switch;self.target=target
        self.restore_end=None;self.close_end=None;self.close_start=None;self.restore_streak=0
        self.errors=set();self.log=[];self.instruction=instruction.lower()

    def update(self, step, source_measure, target_measure, predicate):
        m=source_measure;ct=self.ct
        if ct.get('restore') and self.restore_end is None:
            ref=ct['source_reference']['position'];name=ct['source_object']
            ok=(not m['target_contact'] and m['support_contact'] and m['gripper_gap']>=.065
                and m['object_speed']<=.012 and m['object_angular_speed']<=.20
                and np.linalg.norm(np.asarray(m['all_object_poses'][name]['position'])-ref)<=.025)
            self.restore_streak=self.restore_streak+1 if ok else 0
            if self.restore_streak>=5:
                self.restore_end=step;self.log.append(dict(event='restored_supported_released',step=step))
        key=ct.get('close')
        if key:
            # Drawer coordinates are negative when opening, zero when closed.
            old=self.at['articulation'][key];now=m['articulation'][key]
            closing=(abs(now)<abs(old)-(.01 if key=='stove' else .002))
            if closing and self.close_start is None:
                self.close_start=step
                if ct.get('restore') and self.restore_end is None:self.errors.add('drawer_close_started_before_restore')
            p=['turnoff','flat_stove_1'] if key=='stove' else ['close','wooden_cabinet_1_'+key+'_region']
            closed=bool(predicate(p))
            if closed and self.close_end is None:
                self.close_end=step;self.log.append(dict(event='required_close',step=step))
                if ct.get('restore') and self.restore_end is None:self.errors.add('close_before_restore')
            if self.close_end is not None and not closed:self.errors.add('required_closed_state_lost')
        required_done=(not ct.get('restore') or self.restore_end is not None) and (not key or self.close_end is not None)
        if not required_done:
            from .tasks import TASKS
            target_name=TASKS[self.target][1];same=target_name==ct.get('source_object')
            if self.target in (0,7):
                joint='middle' if self.target==0 else 'stove'
                begun=abs(m['articulation'][joint]-self.at['articulation'][joint])>(.04 if joint=='stove' else .012)
            else:
                # A same-object restore necessarily touches/moves that object;
                # detect its re-grasp only after the restore event, not before.
                begun=bool(target_measure['target_contact']) and (not same or not ct.get('restore') or self.restore_end is not None)
            if begun:self.errors.add('new_object_or_fixture_manipulated_before_required_events')
            if m['goals'][str(self.target)]:self.errors.add('new_goal_reached_before_required_events')
        if ct.get('payload') and not predicate(ct['payload']):self.errors.add('required_payload_relation_lost')
        if ct.get('continue_completed_source') is not None and not m['goals'][str(ct['continue_completed_source'])]:
            self.errors.add('completed_continue_goal_was_undone')
        if 'keep' in self.instruction or 'leave' in self.instruction:
            for joint,ref in ct.get('preserve_joints',{}).items():
                if abs(m['articulation'][joint]-ref)>(.08 if joint=='stove' else .012):self.errors.add('explicit_preserved_joint_changed:'+joint)

    def result(self):
        errors=set(self.errors)
        if self.ct.get('restore') and self.restore_end is None:errors.add('restore_event_missing')
        if self.ct.get('close') and self.close_end is None:errors.add('close_event_missing')
        return dict(passed=not errors,reasons=sorted(errors),events=self.log,
            restore_end=self.restore_end,close_start=self.close_start,close_end=self.close_end)


def eligible_phase(history, source, allowed, source_stable_streak):
    """Use the collector's fine-stage definitions, plus its held-state safeguards."""
    from .runtime import phase_candidates
    t=len(history)-1
    phases=phase_candidates(history,source)
    phase=next((p for p,indices in phases.items() if indices and indices[-1]==t),None)
    if phase not in allowed:return None
    m=history[-1]['before']
    if phase in ('M2','C4'):
        last=history[-5:]
        if len(last)<5 or not all(r['before']['state']=='grasped_airborne' and r['before']['bilateral_finger_contact']
                and not r['before']['support_contact'] and r['before']['object_height_change']>=.03 for r in last):return None
    if phase=='D1' and abs(m['articulation']['middle'])<=.012:return None
    if phase in ('M4','C6','D2','P2','K2') and source_stable_streak<5:return None
    return phase
