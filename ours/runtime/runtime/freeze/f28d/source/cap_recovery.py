"""Agent-generated local recovery, observed preconditions and one existing action exit."""
import base64,copy,io,json,math,os,time,urllib.request
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from PIL import Image
from cap_program import Program,MotionBudget,InvalidProgram,preflight
from hold_gate import PoseHold
from local_transport import connection,recovery_request_json
from agent_transport import ProviderUnavailable


class ProgramPose:
    def __init__(self,code,obs,controller,context,identity,remaining,intent=None,diagnosis=None,finish_at_boundary=False):
        self.intent=intent;self.diagnosis=diagnosis or{}
        self.program=Program(code);self.budget=MotionBudget();self.pose=PoseHold(obs,controller);self.controller=controller
        self.context=dict(context);self.initial_context=copy.deepcopy(context);self.identity=identity;self.current_identity=identity
        self.remaining=min(64,remaining);self.ticks=0;self.command=None;self.command_ticks=0
        self.done=False;self.reason=None;self.events=[];self.opening=False;self.request_replan=False
        self.finish_at_boundary=finish_at_boundary
    def refresh(self,context,identity):self.context=dict(context);self.current_identity=identity
    def action(self,obs):
        try:
            if self.done:return self.pose.action(obs)
            if self.identity!=self.current_identity:raise InvalidProgram('Stage/episode identity changed')
            if self.ticks>=self.remaining:
                if self.finish_at_boundary and self.command is None and self.context['hand_empty']:
                    following=self.program.next(self.context)
                    if following is None:
                        self.done=True;self.request_replan=self.program.replan;self.reason='program_finished'
                        self.pose=PoseHold(obs,self.controller);return self.pose.action(obs)
                raise InvalidProgram('Recovery control-step budget exhausted')
            if not self.context['hand_empty']:raise InvalidProgram('Current empty-hand evidence lost')
            if self.command is not None and self.command['tool']in('move_relative','rotate_relative')and not self.context['target_visible']:
                raise InvalidProgram('Fresh target observation lost during correction')
            if self.command is None:
                command=self.program.next(self.context)
                if command is None:
                    self.done=True;self.request_replan=self.program.replan;self.reason='program_finished'
                    self.pose=PoseHold(obs,self.controller);return self.pose.action(obs)
                self.budget.authorize(command,self.context)
                if self.intent is not None:
                    from recovery_motion_contract import validate_live
                    validate_live(command,self.context,self.intent,self.diagnosis)
                self.command=command;self.command_ticks=0
                self.events.append(dict(tick=self.ticks,event='tool_started',**command))
                name,a=command['tool'],command['arguments'];self.opening=name=='open_gripper'
                if name=='move_relative':self.pose.xyz+=np.array([a.get(k,0.)for k in ['dx_m','dy_m','dz_m']])
                if name=='rotate_relative':self.pose.rot=Rotation.from_euler('xyz',[a.get(k,0.)for k in ['roll_deg','pitch_deg','yaw_deg']],degrees=True).as_matrix()@self.pose.rot
            result=self.pose.action(obs)
            if self.opening:result[6]=-1.
            self.ticks+=1;self.command_ticks+=1;name=self.command['tool']
            duration=self.command['arguments'].get('steps',8)if name=='observe'else 12 if name=='open_gripper'else 16
            if self.command_ticks>=duration:
                if name in ('move_relative','rotate_relative'):
                    poserr=float(np.linalg.norm(self.pose.xyz-np.asarray(obs['robot0_eef_pos'])))
                    angle=float(np.linalg.norm(Rotation.from_matrix(self.pose.rot@Rotation.from_quat(obs['robot0_eef_quat']).as_matrix().T).as_rotvec()))
                    if poserr>.012 or angle>math.radians(6):raise InvalidProgram('Bounded motion did not converge; stop correction')
                self.events.append(dict(tick=self.ticks,event='tool_finished',tool=name));self.command=None;self.opening=False
            return result
        except (InvalidProgram,ValueError,TypeError,ZeroDivisionError,KeyError)as exc:
            self.done=True;self.reason=str(exc);self.pose=PoseHold(obs,self.controller)
            self.events.append(dict(tick=self.ticks,event='program_aborted',reason=str(exc)))
            return self.pose.action(obs)


class CodeRecovery:
    def __init__(self,folder,user_message,episode_id):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True);self.user_message=user_message;self.episode_id=episode_id
        self.cfg,self.key=connection('recovery');self.calls=[];self.events=[];self.stage_attempts={};self.probes={};self.active=None;self.pose_stage=None;self.generated=0
        self.progress_v2=os.environ.get('CAP_PROGRESS_V2','0')=='1'
        self.condition_v3=os.environ.get('CAP_CONDITION_V3','0')=='1'
        if self.condition_v3 and not self.progress_v2:raise ValueError('CAP_CONDITION_V3 requires CAP_PROGRESS_V2; do not silently change the legacy recovery interface')
        self.policy_v4=os.environ.get('CAP_RECOVERY_POLICY_V4','0')=='1'
        if self.policy_v4 and not self.condition_v3:raise ValueError('CAP_RECOVERY_POLICY_V4 requires CAP_CONDITION_V3')
        self.reentry_enabled=os.environ.get('CAP_RECOVERY_REENTRY','0')=='1'
        if self.reentry_enabled and not self.policy_v4:raise ValueError('CAP_RECOVERY_REENTRY requires CAP_RECOVERY_POLICY_V4')
        self.reentry_evidence={};self.reentry_log={}
        self.vertical_approach=os.environ.get('CAP_VERTICAL_APPROACH','0')=='1'
        if self.vertical_approach and not self.policy_v4:raise ValueError('CAP_VERTICAL_APPROACH requires CAP_RECOVERY_POLICY_V4')
        self.vector_geometry=os.environ.get('CAP_VECTOR_GEOMETRY','0')=='1'
        if self.vector_geometry and not self.condition_v3:raise ValueError('CAP_VECTOR_GEOMETRY requires CAP_CONDITION_V3')
        from recovery_progress import ProgressTracker
        self.progress_tracker=ProgressTracker(allow_vertical_approach=self.vertical_approach);self.progress_reviews=[];self.progress_gate_log={}
    def identity(self,mon,stage):return(self.episode_id,stage['operation'],mon.entered)
    def context(self,mon,recovery,stage,reference,free_upward=False):
        row=mon.rgb_rows[-1];sensor=row['sensor'];width=sensor['width'];pred=recovery.visual_facts or{}
        fresh=0<=mon.last-pred.get('frame',-1000)<=8
        proof=recovery.empty_hand_proof
        initial_empty=bool(fresh and pred.get('held_object')=='none'and(width>=.065 or(proof is not None and 0<=mon.last-proof.get('frame',-1000)<=12)))
        # An active program has no closing primitive. Retain its certified empty
        # state only while fresh measured fingers remain OPEN and S1 has no
        # contrary ownership. It expires at this bounded program's end.
        maintained_empty=bool(self.active is not None and self.active.context.get('hand_empty')and width>=.065 and mon.held=='none')
        empty=initial_empty or maintained_empty
        entity=('top_handle'if stage['operation'].endswith('top')else'middle_handle')if stage['operation'].startswith(('open_','close_'))else stage['object']
        key=entity+'.K1';point=row.get('geometry',{}).get(key)
        visible=point is not None and any(p['entity']==entity and p['keypoint']=='K1'for p in row.get('image_points',[]))
        delta=np.asarray(point)-np.asarray(sensor['eef_xyz'])if visible else np.zeros(3)
        current_pixel=next((p['yx224']for p in row.get('image_points',[])if p['entity']==entity and p['keypoint']=='K1'),None)
        prior_pixel=None if self.active is None else self.active.initial_context.get('target_yx_px')
        maintained_support=bool(self.active is not None and self.active.initial_context['target_supported']and visible and current_pixel is not None and prior_pixel is not None and np.linalg.norm(np.asarray(current_pixel)-np.asarray(prior_pixel))<=6 and empty)
        supported=bool(fresh and(pred.get('support_visible',{}).get(stage['object'])is True or stage['operation'].startswith(('open_','close_'))))or maintained_support
        outside=False
        if stage['kind']=='target'and reference:
            obj=next((p['yx224']for p in row.get('image_points',[])if p['entity']==stage['object']and p['keypoint']=='K2'),None)
            dest=next((p['yx224']for p in row.get('image_points',[])if p['entity']==reference['entity']and p['keypoint']==reference['keypoint']),None)
            if dest is None:dest=next((p['yx224']for(t,e,k),p in mon.history.items()if e==reference['entity']and k==reference['keypoint']),None)
            outside=bool(obj is not None and dest is not None and np.linalg.norm(np.asarray(obj)-np.asarray(dest))>2*mon.settings.place_radius_px)
        result=dict(hand_empty=empty,target_visible=bool(visible),target_supported=supported,outside_destination=outside,
            clear_upward=bool(free_upward),target_dx_m=float(delta[0]),target_dy_m=float(delta[1]),target_dz_m=float(delta[2]),operation=stage['operation'],stage_kind=stage['kind'],target_yx_px=current_pixel)
        if getattr(self,'vector_geometry',False):
            from cap_program import refresh_vector_properties
            result['target_xy_norm_m']=None;refresh_vector_properties(result)
        return result
    def generate(self,mon,recovery,stage,reference,context,diagnosis=None):
        rows=list(mon.rgb_rows)[-3:];index=len(self.calls);payload=dict(schema='recovery_code_policy_v2'if getattr(self,'progress_v2',False)else'recovery_code_policy_v1',user_message=self.user_message,
            selected_subgoal=stage,reference=reference,entered_step=mon.entered,frame=mon.last,
            observed_context=context,coordinate_frame='WORLD meters; incremental WORLD-axis rotations in degrees',
            observation_source='Robot proprioception and image-only YOLO/RGB-D; no simulator object pose or success labels',
            recent_frames=[dict(frame=r['frame'],robot=r['sensor'],fresh_points=r.get('image_points',[]),image_derived_world_points=r.get('geometry',{}))for r in rows],
            actual_recovery_history=recovery.events[-5:])
        if getattr(self,'progress_v2',False):payload.update(progress_diagnosis=diagnosis,code_recovery_history=self.events[-6:],upward_clearance_state='unassessed until current visual evidence')
        if getattr(self,'condition_v3',False):
            from recovery_conditions import measured_motion_contract
            try:measured=measured_motion_contract(context)
            except InvalidProgram as exc:
                record=dict(frame=mon.last,operation=stage['operation'],attempts=[],status='insufficient_measurement',validation_errors=[str(exc)],creates_completion=False,seconds=0.)
                self.calls.append(record)
                with(self.folder/'calls.jsonl').open('a')as f:f.write(json.dumps(record)+'\n')
                return None
            payload.update(schema='recovery_code_policy_v3',measured_motion_contract=measured)
        if getattr(self,'policy_v4',False):
            from recovery_effort import feasibility
            payload.update(schema='recovery_code_policy_v4',correction_effort=feasibility(context))
        if getattr(self,'vertical_approach',False):
            payload.update(schema='recovery_code_policy_v5',vertical_standoff=dict(hand_height_above_target_m=-context['target_dz_m'],
                maximum_existing_downward_step_m=.010,existing_minimum_remaining_height_m=.030,
                maximum_descent_with_three_tools_m=.030,
                note='Standoff is not grasp completion; visual approach-path evidence still required. No new gripper closure or larger motion.'))
        if getattr(self,'reentry_enabled',False):
            payload['previous_local_correction_evidence']=self.reentry_evidence.get(self.identity(mon,stage))
        if getattr(self,'vector_geometry',False):
            payload.update(schema='recovery_code_policy_v6',vector_geometry_properties={k:context.get(k)for k in('target_xy_norm_m','target_xy_unit_x','target_xy_unit_y')},
                vector_geometry_note='Current measured TARGET-HAND direction only. Tool sequence and distances remain Agent-authored; scripts never normalize or replace emitted commands.')
        # Logs may include previous measured helper evidence, never private monitors.
        bodycontent=[dict(type='text',text=json.dumps(payload))]
        for r in rows:
            image=Image.fromarray(np.concatenate([r['main'],r['wrist']],axis=1));buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=90)
            bodycontent.extend([dict(type='text',text='frame=%s MAIN left; WRIST right'%r['frame']),dict(type='image_url',image_url=dict(url='data:image/jpeg;base64,'+base64.b64encode(buffer.getvalue()).decode()))])
        prompt_name='recovery_code_prompt_v3.txt'if getattr(self,'condition_v3',False)else'recovery_code_prompt_v2.txt'if getattr(self,'progress_v2',False)else'recovery_code_prompt.txt'
        prompt=Path(__file__).with_name(prompt_name).read_text();messages=[dict(role='system',content=prompt),dict(role='user',content=bodycontent)]
        if getattr(self,'policy_v4',False):messages[0]['content']=Path(__file__).with_name('recovery_policy_v4.txt').read_text()
        if getattr(self,'vertical_approach',False):messages[0]['content']+='\n'+Path(__file__).with_name('recovery_vertical_approach.txt').read_text()
        if getattr(self,'vector_geometry',False):messages[0]['content']+='\n'+Path(__file__).with_name('recovery_vector_geometry.txt').read_text()
        record=dict(frame=mon.last,operation=stage['operation'],attempts=[],status='rejected',creates_completion=False);start=time.monotonic()
        for attempt in range(2):
            body=dict(model=self.cfg['model'],messages=messages,enable_thinking=False,response_format=dict(type='json_object'),temperature=0,max_tokens=1400)
            request=urllib.request.Request(self.cfg['chat_url'],data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
            raw=recovery_request_json(request,timeout=90);content=raw['choices'][0]['message']['content'];errors=[]
            try:prediction=json.loads(content)
            except (ValueError,TypeError):prediction={};errors.append('Return valid JSON')
            if not isinstance(prediction,dict):prediction={};errors.append('Return one JSON object')
            if prediction.get('status')not in ('program','observe_only'):errors.append('status must be program or observe_only')
            if type(prediction.get('free_upward'))is not bool:errors.append('free_upward must be a boolean')
            feedback=None
            if getattr(self,'condition_v3',False):
                from recovery_conditions import review_response
                if getattr(self,'policy_v4',False):
                    from recovery_effort import review as review_response
                if getattr(self,'vertical_approach',False):
                    from recovery_vertical import review as review_response
                reviewed=review_response(prediction,context,diagnosis or{});errors.extend(reviewed['errors']);feedback=reviewed['feedback']
                if reviewed['validated_plan_summary']is not None:prediction['validated_plan_summary']=reviewed['validated_plan_summary']
            elif prediction.get('status')=='program':
                try:
                    if getattr(self,'progress_v2',False):
                        from recovery_motion_contract import validate_strategy
                        preview=validate_strategy(prediction,context,diagnosis or{})
                        prediction['validated_plan_summary']=preview
                    else:preflight(prediction.get('policy_code'),dict(context,clear_upward=prediction.get('free_upward')is True))
                except InvalidProgram as exc:errors.append(str(exc))
            elif getattr(self,'progress_v2',False)and(prediction.get('intent')!='observe_only'or prediction.get('expected_progress')!='none'):
                errors.append('observe_only requires intent=observe_only and expected_progress=none')
            errors=list(dict.fromkeys(errors))
            attempt_record=dict(output=prediction,validation_errors=errors,usage=raw.get('usage'))
            if feedback is not None:attempt_record['validation_feedback']=feedback
            record['attempts'].append(attempt_record)
            if not errors:
                record.update(status=prediction['status'],response=prediction);break
            correction=dict(errors=errors,validation_feedback=feedback)if feedback is not None else errors
            messages=messages+[dict(role='assistant',content=content),dict(role='user',content='Regenerate from the SAME observations. Code/format validation: '+json.dumps(correction))]
        record['seconds']=time.monotonic()-start;self.calls.append(record)
        with(self.folder/'calls.jsonl').open('a')as f:f.write(json.dumps(record)+'\n')
        return record.get('response')if record['status']=='program'else None
    def maybe_start(self,mon,recovery,decision,obs,controller,frame,remaining):
        if self.active is not None or self.generated>=2 or not decision or decision.get('status')!='plan_ready':return None
        stage=decision['remaining_plan'][0];key=self.identity(mon,stage)
        attempts=self.stage_attempts.get(key,0)
        if attempts>=(2 if getattr(self,'reentry_enabled',False)else 1)or remaining<24:return None
        if not getattr(self,'progress_v2',False)and frame-mon.entered<180:return None
        if stage['kind']not in ('grasp','target','open_top','close')and not stage['operation'].startswith(('open_','close_')):return None
        context=self.context(mon,recovery,stage,decision.get('reference'));diagnosis=None
        if getattr(self,'progress_v2',False):
            diagnosis=self.progress_tracker.evaluate(stage,mon.entered,frame,list(mon.rgb_rows),context,mon.held,mon.calibration)
            token=(diagnosis['status'],diagnosis['reason'],diagnosis['eligible'])
            if self.progress_gate_log.get(key)!=token:
                self._record(dict(event='code_progress_admission',**diagnosis));self.progress_gate_log[key]=token
            if not diagnosis['eligible']:return None
        if not context['hand_empty']:
            count=self.probes.get(key,0)
            if count>=2 or recovery.inspections>=recovery.inspection_limit or frame-recovery.last_check<8:return None
            mon.diagnostics['observation_request_context']=dict(reason='grasp_has_not_completed_after_bounded_execution'if stage['kind']=='grasp'else'placement_has_not_completed_after_bounded_execution',selected_stage=stage,reference=decision.get('reference'))
            recovery.inspect(mon);self.probes[key]=count+1;context=self.context(mon,recovery,stage,decision.get('reference'))
            if not context['hand_empty']:return None
            if getattr(self,'progress_v2',False):
                diagnosis=self.progress_tracker.evaluate(stage,mon.entered,frame,list(mon.rgb_rows),context,mon.held,mon.calibration)
                if not diagnosis['eligible']:return None
        if not context['target_visible']or not context['target_supported']:return None
        if attempts:
            from recovery_reentry import assess
            admission=assess(stage,mon.entered,frame,list(mon.rgb_rows),context,diagnosis or{},self.reentry_evidence.get(key))
            token=(admission['permit'],admission['reason'])
            if self.reentry_log.get(key)!=token:
                self._record(dict(event='code_reentry_admission',frame=frame,operation=stage['operation'],**admission));self.reentry_log[key]=token
            if not admission['permit']:return None
        self.stage_attempts[key]=attempts+1;self.generated+=1
        response=self.generate(mon,recovery,stage,decision.get('reference'),context,diagnosis)
        if response is None:return None
        context['clear_upward']=response['free_upward']
        self.active=ProgramPose(response['policy_code'],obs,controller,context,key,min(48,remaining)if getattr(self,'progress_v2',False)else remaining,intent=response.get('intent')if getattr(self,'progress_v2',False)else None,diagnosis=diagnosis,finish_at_boundary=getattr(self,'policy_v4',False))
        self.pose_stage=dict(stage=copy.deepcopy(stage),reference=copy.deepcopy(decision.get('reference')),identity=key,start=frame,free_upward=response['free_upward'],intent=response.get('intent'),expected_progress=response.get('expected_progress'))
        if getattr(self,'reentry_enabled',False):
            self.reentry_evidence[key]=dict(operation=stage['operation'],entered_step=mon.entered,
                initial_target_yx=context.get('target_yx_px'),failure_mode=(diagnosis or{}).get('failure_mode'),start_frame=frame)
        started=dict(frame=frame,event='code_policy_started',operation=stage['operation'],policy_code=response['policy_code'],creates_completion=False,oracle_state_used=False)
        if getattr(self,'progress_v2',False):self._record(dict(started,intent=response['intent'],expected_progress=response['expected_progress'],progress_diagnosis=diagnosis))
        else:self.events.append(started)
        return self.active
    def _record(self,event):
        self.events.append(event)
        with(self.folder/'progress.jsonl').open('a')as stream:stream.write(json.dumps(event)+'\n')
    def advance(self,mon,recovery,frame,decision):
        if getattr(self,'progress_v2',False):
            current=(decision.get('remaining_plan')or[None])[0]if decision else None
            for review in list(self.progress_reviews):
                result=review.evaluate(frame,list(mon.rgb_rows),mon.events,current,mon.entered)
                if result is not None:
                    self._record(result);self.progress_reviews.remove(review)
                    entry=self.reentry_evidence.get((self.episode_id,review.stage['operation'],review.entered))
                    if entry is not None:
                        entry['followup_status']=result['status']
                        if 'height_gain_m'in result:entry['followup_height_gain_m']=result['height_gain_m']
        if self.active is None:return None
        stage=self.pose_stage['stage'];identity=self.identity(mon,stage)
        if decision is None or not decision.get('remaining_plan')or decision['remaining_plan'][0]['operation']!=stage['operation']:identity=None
        ctx=self.context(mon,recovery,stage,self.pose_stage['reference'],self.pose_stage['free_upward'])
        self.active.refresh(ctx,identity)
        if getattr(self,'progress_v2',False)and not self.active.done:
            reason='stage_or_episode_changed'if identity!=self.active.identity else'correction_window_expired'if frame-self.pose_stage['start']>=64 else None
            if reason is not None:self.active.done=True;self.active.reason=reason;self.active.request_replan=False
        if not self.active.done:return None
        report=dict(frame=frame,event='code_policy_finished',operation=stage['operation'],reason=self.active.reason,
            steps=self.active.ticks,request_replan=self.active.request_replan,tools=self.active.events,creates_completion=False)
        if getattr(self,'reentry_enabled',False):
            self.reentry_evidence[self.pose_stage['identity']].update(finish_frame=frame,finish_reason=self.active.reason)
        if getattr(self,'progress_v2',False):
            self._record(report)
            if self.active.reason=='program_finished':
                from recovery_progress import ProgressReview,camera_token
                self.progress_reviews.append(ProgressReview(stage,self.active.identity[2],self.pose_stage['start'],frame,self.active.initial_context,self.pose_stage['intent'],self.pose_stage['expected_progress'],camera_token(mon.rgb_rows[-1]),self.progress_tracker.settings.followup_steps))
        else:self.events.append(report)
        self.active=None;self.pose_stage=None
        return report
    def finish_case(self,frame):
        if not getattr(self,'progress_v2',False):return
        if self.active is not None:
            self._record(dict(frame=frame,event='code_policy_finished',operation=self.pose_stage['stage']['operation'],reason='episode_ended',steps=self.active.ticks,request_replan=False,tools=self.active.events,creates_completion=False))
            self.active=None;self.pose_stage=None
        for review in self.progress_reviews:self._record(review._result(frame,'insufficient_evidence','episode_ended_before_followup'))
        self.progress_reviews=[]
