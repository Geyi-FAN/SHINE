"""Read-only Oracle adapter and separately versioned full-contract diagnostics."""
import json
import numpy as np
from sym_paths import DATA
from sym_contract import Oracle,prompt,ROLES
from sym_geometry import Grounder
from restore_metrics import gates


class StrictMonitor:
    VERSION='declared_contract_v3_symbolic_20261015'
    def __init__(self,plan,at):
        self.plan=plan;self.at=at;self.errors=set();self.s25=0;self.s35=0;self.sw=0;self.release_streak=0
        self.restored=False;self.restored35=False;self.withdrawn=False;self.released=False;self.closed=False

    def update(self,sm,tm,goal,predicate):
        p=self.plan;ct=p['contract'];obj=p['restore_object']
        if obj:
            ref=p['initial_xyz'][obj];g25=gates(sm,ref,.025);g35=gates(sm,ref,.035)
            self.s25=self.s25+1 if all(g25.values()) else 0
            self.s35=self.s35+1 if all(g35.values()) else 0
            clear=all(g35.values()) and np.linalg.norm(np.asarray(sm['eef_position'])-sm['object_position'])>=.08
            self.sw=self.sw+1 if clear else 0
            if p['new'] and self.restored35 and not g35['position']:self.errors.add('restored_object_moved_again')
            self.restored |= self.s25>=5;self.restored35 |= self.s35>=5;self.withdrawn |= self.sw>=5
        needs_release=any(s['kind']=='release' for s in p['stages'])
        if needs_release:
            ok=all(v for k,v in gates(sm,sm['object_position'],1).items() if k!='position')
            self.release_streak=self.release_streak+1 if ok else 0;self.released |= self.release_streak>=5
        key=p['close']
        if key:
            pred=['turnoff','flat_stove_1'] if key=='stove' else ['close','wooden_cabinet_1_'+key+'_region']
            closed=bool(predicate(pred))
            if self.closed and not closed:self.errors.add('required_closed_state_lost')
            self.closed |= closed
        required=(not obj or self.restored and (not p['new'] or self.withdrawn)) and (not needs_release or self.released) and (not key or self.closed)
        if not required:
            target=p['target'];same=p['source_object']==__import__('sym_contract').TASK_OBJECT.get(target)
            if target in (0,7):
                joint='middle' if target==0 else 'stove';begun=abs(sm['articulation'][joint]-self.at['articulation'][joint])>(.012 if target==0 else .04)
            else:begun=bool(tm['target_contact']) and (not same or not obj or self.restored)
            if begun:self.errors.add('new_target_manipulated_before_required_events')
            if goal['goal']:self.errors.add('new_goal_reached_before_required_events')
        for inv in p['acceptance'].get('invariants',[]):
            kind=inv['predicate']
            if kind in ('source_object_unchanged','restored_source_pose_preserved'):
                if kind=='restored_source_pose_preserved' and not self.restored:continue
                name=inv['object'];ref=p['initial_xyz'][name] if kind=='restored_source_pose_preserved' else self.at['all_object_poses'][name]['position']
                if np.linalg.norm(np.asarray(sm['all_object_poses'][name]['position'])-ref)>inv['tolerance_m']:
                    self.errors.add(kind+':'+name)
            elif kind=='source_articulation_unchanged':
                key2=inv['joint']
                if abs(sm['articulation'][key2]-self.at['articulation'][key2])>inv['tolerance']:self.errors.add(kind+':'+key2)
            elif kind=='payload_relation_preserved':
                if not predicate(inv['relation']):self.errors.add(kind)
            elif kind=='required_closed_state_preserved':pass  # continuous predicate checked above
            elif kind=='no_repeat_operation':
                if not goal['goal']:self.errors.add('completed_goal_undone')
            else:raise ValueError(('Unimplemented invariant',kind))
        # Preserve explicit snapshot contracts even when the mini record has no
        # full acceptance catalog, using the original checker tolerance.
        if ct.get('preserve_object') and not p['acceptance'].get('invariants'):
            name=ct['source_object'];ref=ct['preserve_reference']['position']
            if np.linalg.norm(np.asarray(sm['all_object_poses'][name]['position'])-ref)>.015:self.errors.add('preserved_object_moved')
        if not p['acceptance'].get('invariants') and any(w in p['original_instruction'].lower() for w in ('keep','leave')):
            for joint,ref in ct.get('preserve_joints',{}).items():
                if abs(sm['articulation'][joint]-ref)>(.08 if joint=='stove' else .012):self.errors.add('preserved_joint_changed:'+joint)
        for field in ('preserve_relation','payload'):
            if ct.get(field) and not predicate(ct[field]):self.errors.add(field+'_broken')

    def result(self):
        errors=set(self.errors);p=self.plan
        if p['restore_object'] and not self.restored:errors.add('restore_event_missing')
        if p['new'] and not self.withdrawn:errors.add('withdraw_event_missing')
        if p['close'] and not self.closed:errors.add('close_event_missing')
        if any(s['kind']=='release' for s in p['stages']) and not self.released:errors.add('release_event_missing')
        return dict(version=self.VERSION,passed=not errors,reasons=sorted(errors))


class OnlineAdapter:
    def __init__(self,env,case,arm):
        self.plan=json.loads((DATA/'mini_plans.json').read_text())[case['case_id']]
        self.env=env;self.arm=arm;self.grounder=Grounder(env,self.plan);self.oracle=Oracle(self.plan)
        guards,sm,tm,goal=self.grounder.measure();self.oracle.observe(guards,0)
        self.strict=StrictMonitor(self.plan,sm)
        self.history=[];self.calls=[]

    def update(self,step):
        guards,sm,tm,goal=self.grounder.measure();stage=self.oracle.observe(guards,step)
        self.strict.update(sm,tm,goal,self.env.env._eval_predicate)
        self.history.append(dict(step=int(step),stage=int(stage),guards=guards.tolist()))

    def make_prompt(self,step):
        points,valid,counts,world=self.grounder.points()
        text=prompt(self.plan,self.arm,self.oracle.index,points,valid)
        from v3_markers import marker_info
        self.last_marker=marker_info(self.plan,self.oracle.index,points,valid)
        self.calls.append(dict(step=int(step),stage=int(self.oracle.index),prompt=text,
            points=points.tolist(),valid=valid.tolist(),roles=list(ROLES),marker=self.last_marker))
        return text

    def make_observation(self,request,step):
        from v3_markers import render_numpy
        import hashlib
        request=dict(request);request['prompt']=self.make_prompt(step)
        image=request['observation/image']
        self.calls[-1]['raw_main_sha256']=hashlib.sha256(image.tobytes()).hexdigest()
        request['observation/image']=render_numpy(image,self.last_marker)
        self.calls[-1]['marked_main_sha256']=hashlib.sha256(request['observation/image'].tobytes()).hexdigest()
        return request
