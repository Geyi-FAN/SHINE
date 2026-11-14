"""Hybrid live smoke, no Oracle plan or pixel GT crosses planner boundary."""
import argparse,sys,os,json,time,gzip,traceback,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'vendor/support/metrics'))
from benchmark_metrics import load_rules,evaluate_episode
from benchmark_metrics.config import fingerprint
from benchmark_metrics.predicates import region_contains
from sim_runtime import GeometryRuntime,new_env,restore,capture,identity,get_libero_path
from eval_inputs import build_inputs,resize
from openpi_client.websocket_client_policy import WebsocketClientPolicy
from v3_markers import render_numpy
from planner import Planner,CATALOG
from completion import Completion
from extended_completion import ExtendedCompletion as ObservedCompletion,Settings
from depth_sensor import read_depth,sensed_geometry
from visual_verifier import VisualVerifier
from hold_gate import PoseHold
from switch_terminal import SwitchTerminal
from sym_geometry import project
from points import Points
from recovery_runtime import RecoveryRuntime
from observation_tools import OpenThenWithdraw
from static_depth_memory import StaticDepthMemory
from agent_transport import ProviderUnavailable
from hold_gate import CandidateGate
from terminal_gate import TerminalGate
from planning_relation_memory import PlanningRelationMemory,trusted_relation_geometry

SMALL=Path(os.environ.get('HYBRID_CASES_ROOT','/mnt/disk_2/geyi/pi05_small722_20261016'))
METRICS=Path(__file__).resolve().parents[3]/'vendor/support/metrics'
CONTRACT_FILE=Path(os.environ.get('HYBRID_CONTRACT_FILE',str(METRICS/'analysis/task_contract_v2_20261021/contracts.json')))
def relocate(p):
    q=Path(p)
    if not q.is_absolute():return SMALL/q
    if q.exists():return q
    return Path(str(p).replace('/mnt/disk_2/geyi',str(SMALL/'work'),1))

def metric_evidence(env,case,contract):
    from libero.libero.envs.predicates.base_predicates import In
    core=env.env;sim=env.sim;out={};site={5:'main_table_stove_front_region',9:'wine_rack_1_top_region'}.get(case.get('target_task'))
    if site:
        obj='wine_bottle_1' if case['target_task']==9 else 'plate_1';state=core.object_states_dict[site];siteobj=core.object_sites_dict[site]
        center=np.asarray(sim.data.get_site_xpos(site));M=np.asarray(sim.data.get_site_xmat(site)).reshape(3,3);pos=sim.data.body_xpos[core.obj_body_id[obj]];size=np.asarray(siteobj.size);parent=core.get_object(state.parent_name)
        out['regions']={site:dict(local_position=(M@(pos-center)).tolist(),lower=[-float(size[0]),-float(size[1]),float(size[2]-.005)],upper=[float(size[0]),float(size[1]),float(size[2]+.10)],parent_contact_required=parent is not None,parent_contact=True if parent is None else bool(core.check_contact(parent,core.get_object(obj))))}
    for c in contract['clauses']:
        if c['kind']=='preserve_containment':out.setdefault('containment',{})[c['id']]=bool(In()(core.object_states_dict[c['object']],core.object_states_dict['wooden_cabinet_1_top_region']))
    return out

def run(case,planner,client,out,budget,snapshot_only=False):
    out.mkdir(parents=True,exist_ok=False);env=points=video=shadow=mon=None;records=[];reviews=[];measurements=[];actions=[];chunks=[];events=[];initial={};start=time.monotonic()
    s1=os.environ.get('HYBRID_COMPLETION','S0')=='S1'
    d1=os.environ.get('HYBRID_FINAL_PROTOCOL','D1')=='D1';switch_terminal=None
    d0=os.environ.get('HYBRID_FINAL_PROTOCOL','historical')=='D0';terminal=None;terminal_checks=[];final_candidates=[]
    if not s1:raise ValueError('All P012 arms use the same observable planner facts')
    arm_id=os.environ['P012_ARM']
    selected_stages=[];detector_rows=[];oracle_events=[];gate=None;gate_logs=[];cooldown_until=-1;gate_attempts={};arm=os.environ.get('S1_OBSERVE_ARM','B')
    rules=load_rules();result=dict(case_id=case['case_id'],group=case['group'],mode='Agent + S1 RGB/proprio completion + YOLO; observable memory validity' if s1 else 'Agent + Oracle completion + YOLO; observable memory validity',m2_current_only=os.environ.get('HYBRID_M2_CURRENT_ONLY','0')=='1',static_cache_enabled=os.environ.get('HYBRID_STATIC_CACHE','1')=='1',cache_validity_source='observable_visual_estimate',rules_version=rules['version'],rules_sha256=fingerprint(rules),budget=budget,smoke_only=budget<case['budget'],oracle_plan_input=False,oracle_pixel_input=False,reset_after_start=False,det_threshold=float(os.environ.get('HYBRID_DET_CONF','0.1')),keypoint_threshold=float(os.environ.get('HYBRID_KPT_CONF','0.1')))
    try:
        rt=GeometryRuntime();new=case['kind']=='new_revision'
        if new:bddl=relocate(case['bddl_file'])
        else:
            t=rt.suite.get_task(case['source_task']);bddl=Path(get_libero_path('bddl_files'))/t.problem_folder/t.bddl_file
        env=new_env(bddl);context=dict(np.load(relocate(case['context_file'] if new else case['snapshot_file'])));obs=restore(env,context)
        result['start_state_identity']=identity(capture(env))
        points=Points(out/'points',episode_id=case['case_id'],episode_frame_at_takeover=case.get('fixed_switch_step'))
        if new:im=np.asarray(Image.open(relocate(case['reference_image'])).convert('RGB'))
        else:im=np.ascontiguousarray(np.load(relocate(case['initial_state_file']))['main_raw_image'][::-1,::-1])
        if im.shape!=(256,256,3):raise ValueError('Initial memory image must be native MAIN256')
        private_mon=Completion(env,case.get('initial_xyz',{}),case['source_task'],case.get('previous_instruction',''));private_mon.observe(0)
        mon=private_mon
        result['scene_memory_configuration']=dict(points.scene.configuration,
            static_window_translation_m=mon.memory_window_translation,
            static_window_rotation_deg=mon.memory_window_rotation)
        points.update_evidence(0,{},mon.memory_camera_id())
        history=None
        if points.scene.transfer_enabled and points.scene.enabled:
            from episode_history import load_initial_object_history
            try:
                history=load_initial_object_history(case,bddl,im,relocate,rgbd_file=out/'episode_start_observed_rgbd.npz' if os.environ.get('HYBRID_KNOWN_CLOSED_EPISODE_START','0')=='1' else None)
                (out/'episode_initial_validity_evidence.json').write_text(json.dumps(history,indent=2))
                result['episode_object_history']=dict(status='validated',source=history['source'],
                    render_image_mae=history['render_image_mae'],seconds=history['seconds'])
            except Exception:
                result['episode_object_history']=dict(status='unavailable',error=traceback.format_exc())
                points.scene.log('history_adapter_unavailable',reason=result['episode_object_history']['error'])
        points.observe(im,-1,'episode_start',camera_id=history['camera_transform_id'] if history else None)
        if history:points.transfer_episode_objects(history)
        points.begin_instruction(np.ascontiguousarray(obs['agentview_image'][::-1,::-1]),0)
        result['known_closed_episode_start_setup_prior']=os.environ.get('HYBRID_KNOWN_CLOSED_EPISODE_START','0')=='1'
        if result['known_closed_episode_start_setup_prior'] and history and history.get('initial_observed_rgbd_file'):
            # Same typed YOLO K1 on historical RGB-D; private cache validity facts
            # and simulator object/joint poses are not estimator inputs.
            from episode_handle_reference import build as build_episode_reference
            measured=np.load(history['initial_observed_rgbd_file'])
            original_calibration=json.loads(Path(os.environ['P012_DRAWER_CALIBRATION']).read_text())
            initial_points=[p for (t,e,k),p in points.memory.items()if t=='episode_start'and e in('top_handle','middle_handle')and k=='K1']
            corrected=build_episode_reference(initial_points,measured['depth'],json.loads(str(measured['calibration'])),original_calibration)
            calibration_file=out/'observed_episode_drawer_reference.json'
            calibration_file.write_text(json.dumps(corrected,indent=2))
            os.environ['P012_DRAWER_CALIBRATION']=str(calibration_file)
            result['drawer_reference_provenance']=corrected['reference_provenance']
        if s1:
            mon=ObservedCompletion(history=dict(points.memory),settings=Settings(confidence=float(os.environ.get('S1_POINT_CONF','0.35'))))
        result.update(completion_variant='S1' if s1 else 'S0',final_stop='controller_confirmed_final_stage',oracle_cache_validity=False,oracle_final_stop=False,detector_uses_cached_current_points=False)
        if s1:
            result['detector_settings']=vars(mon.settings)
            if arm_id=='P2':
                mon.verifier=VisualVerifier(out/'verifier')
                if hasattr(mon.verifier,'configure'):mon.verifier.configure(resize(im),resize(np.ascontiguousarray(obs['agentview_image'][::-1,::-1])),resize(np.ascontiguousarray(obs['robot0_eye_in_hand_image'][::-1,::-1])),case.get('instruction_original',case['instruction']))
        result.update(experiment_arm=arm_id,intermediate_completion='Oracle selected-stage only' if arm_id=='P0' else 'S1 RGB-D' if arm_id=='P1' else 'S1 RGB-D plus conditional visual verifier',planner_state_source='same observed RGB-D/proprioception interface in all arms')
        source=rt.monitor(env,case['source_task']);target=rt.monitor(env,case['target_task'])
        initial=dict(articulation=source.measure()['articulation'],native_goal=bool(rt.frame(target,case['target_task'])['goal']))
        # Canonical scoring contracts are private to this runner, NEVER planner input.
        contract=next(c for c in json.loads(CONTRACT_FILE.read_text()) if c['case_id']==case['case_id'])
        if os.environ.get('HYBRID_ORACLE_REVIEW','1')=='1':
            from oracle_review import ShadowOracle
            shadow=ShadowOracle(env,case,contract,rules,initial,budget)
        result['raw_user_message']=case.get('instruction_original',case['instruction'])
        if d1:
            switch_terminal=SwitchTerminal(case,contract,rules,initial)
            result.update(final_stop='switch_v25_instruction_adjusted',oracle_final_stop=True,final_protocol='D1',terminal_feedback_scope='private full Switch contract; causal prefix only')
        elif d0:
            terminal=TerminalGate(case['target_task'],result['raw_user_message'])
            result.update(final_stop='native_benchmark_plus_original_s1_release_guards',oracle_final_stop=True,final_protocol='D0',terminal_feedback_scope='current_target_task_success_bit_only',necessary_constraints_source='Agent initial prefix plus existing S1 release/stability/separation; private scoring clauses excluded')
        else:result['final_protocol']='historical'
        result['scoring_instruction']=case['instruction'];result['scoring_instruction_differs_from_raw']=result['raw_user_message']!=case['instruction']
        if not snapshot_only:
            import imageio
            video=imageio.get_writer(str(out/'policy_input.mp4'),fps=6,macro_block_size=16)
        def forbidden(*a,**k):raise RuntimeError('No reset/state mutation after start')
        for name in ('reset','set_init_state','set_state','regenerate_obs_from_state'):
            if hasattr(env,name):setattr(env,name,forbidden)
        decision=None;queue=[];call=0;status='budget_exhausted';pending=False;hold_only=False
        recovery=RecoveryRuntime(out/'recovery',result['raw_user_message'])
        if os.environ.get('CAP_RETURN_RELEASE_REVIEW','0')=='1':
            from return_release_review import specialize
            recovery=specialize(recovery)
        from observed_state_memory import ObservedStateMemory
        observed_states=ObservedStateMemory(mon.calibration,out/'observed_state_memory.jsonl')
        planning_relations=PlanningRelationMemory(out/'planning_relation_memory.jsonl')
        recovery_wait_until=-1;recovery_pose=None;recovery_reason=None;perception_bootstrap_done=False
        target_observation_until=-1;empty_gripper_until=-1;stage_observation_attempts={};static_depth=StaticDepthMemory()
        ownership_replan_pending=False
        from post_return_handoff import PostReturnHandoff
        post_return_handoff=PostReturnHandoff()
        hold_pose=PoseHold(obs,env.env.robots[0].controller);refine_hold_pose=None
        from cap_recovery import CodeRecovery
        cap_recovery=CodeRecovery(out/'code_recovery',result['raw_user_message'],case['case_id']) if os.environ.get('CAP_RECOVERY_ENABLED','0')=='1' else None
        for step in range(budget):
            if not queue:
                points.observe(np.ascontiguousarray(obs['agentview_image'][::-1,::-1]),step)
                if s1:
                    eef=np.asarray(obs['robot0_eef_pos']);yx,valid=project(env.sim,eef)
                    # Camera calibration + robot proprio only; no object pose projection.
                    depth,cal=read_depth(env)
                    geometry=sensed_geometry(list(points.current.values()),depth,cal)
                    mon.supply(step,resize(np.ascontiguousarray(obs['agentview_image'][::-1,::-1])),resize(np.ascontiguousarray(obs['robot0_eye_in_hand_image'][::-1,::-1])),geometry)
                    mon.rgb_rows[-1]['camera_calibration']=cal
                    mon.rgb_rows[-1]['image_points']=list(points.current.values())
                    mon.rgb_rows[-1]['static_destination_geometry']=static_depth.update(points.scene,geometry,step)
                    Image.fromarray(np.ascontiguousarray(obs['robot0_eye_in_hand_image'][::-1,::-1])).save(out/'points'/f'{step}_wrist.png')
                    mon.final_stage=decision is not None and len(decision['remaining_plan'])==1
                    mon.observation_action_end=target_observation_until
                    event=mon.observe(step,eef.tolist(),np.asarray(obs['robot0_gripper_qpos']).tolist(),yx.tolist() if valid else None,list(points.current.values()))
                    detector_rows.append(dict(sensor=dict(frame=step,eef_xyz=eef.tolist(),gripper_qpos=np.asarray(obs['robot0_gripper_qpos']).tolist(),eef_yx=yx.tolist() if valid else None),estimated=mon.snapshot,diagnostics=mon.diagnostics,oracle_for_scoring_only=private_mon.snapshot))
                    with (out/'completion_observations.jsonl').open('a') as f:f.write(json.dumps(detector_rows[-1])+'\n')
                    if event and arm in ('H','W'):
                        # Event is only a candidate: do not send it to Agent before observation.
                        mon.events.pop();key=(event['operation'],event['entered_step'])
                        if gate is None and step>=cooldown_until and gate_attempts.get(key,0)<2:
                            gate=CandidateGate(event,decision['remaining_plan'][0],step,obs,env.env.robots[0].controller)
                            gate_attempts[key]=gate_attempts.get(key,0)+1
                            gate_logs.append(dict(start=step,operation=event['operation'],entered_step=event['entered_step'],arm=arm,initial_xyz={k:list(v[-1]['object_position']) for k,v in private_mon.windows.items()},status='observing'))
                        elif gate_attempts.get(key,0)>=2:
                            status='need_observation';result['blocked_reason']='Completion evidence unresolved after two observation windows';break
                        else:
                            mon.active=dict(decision['remaining_plan'][0])
                        event=None
                    if gate is not None:
                        verdict=gate.check(mon,step,obs)
                        if verdict!='observe':
                            gate_logs[-1].update(end=step,status=verdict,max_eef_drift_m=gate.max_drift,evidence=gate.rows,final_xyz={k:list(v[-1]['object_position']) for k,v in private_mon.windows.items()})
                            if verdict=='accept':
                                event=dict(gate.event,confirmed_step=step,source='s1_candidate_observed_'+arm);mon.events.append(event)
                            else:
                                mon.active=dict(gate.stage);cooldown_until=step+30;mon.confirm_counts={}
                            gate=None
                        (out/'hold_events.json').write_text(json.dumps(gate_logs,indent=2))
                    if event and (d0 or d1) and decision is not None and len(decision['remaining_plan'])==1:
                        # A final S1 declaration is audit-only. Native goal plus
                        # observed release guards decides terminal completion.
                        final_candidates.append(dict(event))
                        mon.events.pop();mon.active=dict(decision['remaining_plan'][0]);event=None
                    if event:
                        events.append(event)
                        final=decision is not None and len(decision['remaining_plan'])==1
                        decision=None
                        if final:status='controller_final_stage_completed';break
                observed_states.update(step,geometry,points.camera_id,mon.active,mon.events)
                recovery.apply_visual_facts(mon)
                if os.environ.get('PLANNING_RELATION_REPAIR','1')=='1':
                    relation_geometry=trusted_relation_geometry(geometry,list(points.current.values()),step,mon.settings.confidence)
                    planning_relations.observe(case['case_id'],step,points.camera_id,mon.snapshot,relation_geometry,
                        mon.active,mon.events,recovery.events,mon.diagnostics)
                observation_wait=step<target_observation_until
                if post_return_handoff.pending is not None:
                    handoff=post_return_handoff.advance(mon,recovery,step)
                    if handoff and handoff['phase']=='start_move':
                        recovery_pose=PoseHold(obs,env.env.robots[0].controller);recovery_pose.xyz[2]+=handoff['height_m']
                        target_observation_until=handoff['until'];observation_wait=True
                    elif handoff and handoff['phase']in('wait','move'):
                        target_observation_until=handoff['until'];observation_wait=True
                    elif handoff and handoff['phase']=='finished':
                        decision=None;mon.active=None;private_mon.active=None
                if recovery.pending is not None:
                    if recovery.grip_release_until is not None:
                        if step<recovery.grip_release_until:observation_wait=True
                        else:
                            recovery.grip_release_until=None;recovery.visual_facts=None
                            recovery.pending=None;decision=None;hold_only=False
                            if recovery.inspections<recovery.inspection_limit and mon.samples[-1]['width']>=.065:
                                released=next((e['object'] for e in reversed(recovery.events) if e['event']=='agent_requested_supported_release'),None)
                                mon.diagnostics['observation_request_context']=dict(reason='supported_in_place_release_executed_but_hand_may_still_intersect_old_object',released_object=released,gripper_open=True,allowed_tool='clear_supported_object')
                                prediction=recovery.inspect(mon)
                                near=mon.diagnostics.get('holding',{}).get('near_px',{}).get(released)
                                if prediction and prediction.get('recovery_request')=='clear_supported_object' and released is not None and prediction.get('support_visible',{}).get(released) is True and near is not None and near<=26:
                                    recovery_pose=PoseHold(obs,env.env.robots[0].controller);recovery_pose.xyz[2]+=.060
                                    target_observation_until=step+16;observation_wait=True
                                    recovery.events.append(dict(frame=step,event='agent_requested_supported_object_clearance',object=released,height_m=.060,gripper='open',reason='clear old object before next grasp',oracle_pixel_used=False))
                    elif step>=recovery_wait_until:
                        recovery.inspect(mon)
                        if recovery.grip_release_until is not None:
                            observation_wait=True
                        elif mon.snapshot['held_object']=='unknown' and recovery.inspections<recovery.inspection_limit:
                            recovery_wait_until=step+8;observation_wait=True
                        else:
                            recovery.pending=None;decision=None;hold_only=False
                    else:observation_wait=True
                if getattr(mon,'request_geometry_observation',False) and decision is not None and not observation_wait:
                    current=decision['remaining_plan'][0];stage_key=(current['operation'],mon.entered)
                    if stage_observation_attempts.get(stage_key,0)<2 and recovery.inspections<recovery.inspection_limit:
                        mon.diagnostics['observation_request_context']=dict(reason='close_candidate_needs_clearer_geometry_or_visual_identity',selected_stage=current,reference=None)
                        inspections_before=recovery.inspections
                        prediction=recovery.inspect(mon)
                        if recovery.inspections>inspections_before:stage_observation_attempts[stage_key]=stage_observation_attempts.get(stage_key,0)+1
                        if prediction and prediction.get('recovery_request')=='observe_clear_cabinet' and (mon.samples[-1]['width']>=.065 or mon.samples[-1]['width']<.002) and mon.held=='none':
                            level='top' if current['operation'].endswith('top') else 'middle'
                            axis=np.asarray(mon.calibration['closed_handles'][level]['opening_axis'],float);axis/=np.linalg.norm(axis)
                            opening=16 if mon.samples[-1]['width']<.002 else 0
                            recovery_pose=OpenThenWithdraw(obs,env.env.robots[0].controller,axis,open_steps=opening)
                            target_observation_until=step+opening+12;observation_wait=True
                            recovery.events.append(dict(frame=step,event='agent_requested_cabinet_observation',offset_xyz_m=(axis*.040).tolist(),gripper='open before withdrawal',opening_steps=opening,reason='fresh drawer geometry; not completion',oracle_pixel_used=False))
                    mon.request_geometry_observation=False
                if not perception_bootstrap_done and decision is None:
                    import re
                    needs_inspection=mon.snapshot['held_object']=='unknown' or ('bowl' in result['raw_user_message'].lower() and 'cheese' in result['raw_user_message'].lower()) or bool(re.search(r'\b(?:leave|keep)\s+the\s+\w+\s+(?:inside|in)\b',result['raw_user_message'],re.I))
                    perception_bootstrap_done=True
                    if needs_inspection:
                        prediction=recovery.inspect(mon)
                        if (prediction and prediction.get('recovery_request')=='release_supported_in_place') or mon.snapshot['held_object']=='unknown':
                            recovery.pending='holding';recovery_wait_until=step+8;observation_wait=True
                if os.environ.get('CAP_RETURN_RELEASE_REVIEW','0')=='1'and not observation_wait:
                    from return_release_review import request as request_return_review
                    if request_return_review(mon,recovery,step,decision):
                        recovery_wait_until=step+8;observation_wait=True
                if os.environ.get('REPAIR_STAGNATION_OBSERVATION','0')=='1' and decision is not None and not observation_wait and decision.get('status')=='plan_ready':
                    current=decision['remaining_plan'][0];stage_key=(current['operation'],mon.entered)
                    count=stage_observation_attempts.get(stage_key,0)
                    lost_ownership_enabled=os.environ.get('REPAIR_LOST_OWNERSHIP','0')=='1'
                    inspection_bound=5 if lost_ownership_enabled and current['operation']=='cheese_bowl' else 2
                    if (current['operation']=='cheese_bowl' or current['kind']=='grasp') and step-mon.entered>=180*(count+1) and count<inspection_bound and recovery.inspections<recovery.inspection_limit:
                        mon.diagnostics['observation_request_context']=dict(reason='grasp_has_not_completed_after_bounded_execution' if current['kind']=='grasp' else 'placement_has_not_completed_after_bounded_execution',selected_stage=current,reference=decision['reference'])
                        inspections_before=recovery.inspections
                        prediction=recovery.inspect(mon)
                        if recovery.inspections>inspections_before:stage_observation_attempts[stage_key]=count+1
                        from ownership_recovery import empty_hand_replan_evidence
                        ownership=empty_hand_replan_evidence(list(mon.rgb_rows),current,prediction or {},step) if lost_ownership_enabled else dict(passed=False)
                        if prediction and prediction.get('recovery_request')=='open_empty_gripper' and current['operation']=='cheese_bowl' and ownership['passed'] and recovery.replans<2:
                            recovery_pose=PoseHold(obs,env.env.robots[0].controller)
                            empty_gripper_until=step+16;target_observation_until=step+16;observation_wait=True
                            ownership_replan_pending=True
                            recovery.events.append(dict(frame=step,event='agent_requested_empty_placement_reopen',operation=current['operation'],gripper='open',translation_m=0,evidence=ownership,creates_completion=False))
                        elif prediction and prediction.get('recovery_request')=='open_empty_gripper' and current['kind']=='grasp' and mon.samples[-1]['width']<.002 and mon.point(mon.samples[-1],current['object'],'K1') is not None:
                            recovery_pose=PoseHold(obs,env.env.robots[0].controller)
                            empty_gripper_until=step+16;target_observation_until=step+16;observation_wait=True
                            recovery.events.append(dict(frame=step,event='agent_requested_empty_hand_reopen',operation=current['operation'],gripper='open',translation_m=0))
                        elif prediction and prediction.get('recovery_request')=='replan_current_task' and current['operation']=='cheese_bowl' and mon.samples[-1]['width']>=.065 and prediction.get('held_object')=='none' and prediction.get('relations',{}).get('cheese_bowl') is False and prediction.get('support_visible',{}).get('cheese') is True and recovery.replans<2:
                            recovery.replans+=1
                            recovery.events.append(dict(frame=step,event='agent_requested_replan',interrupted_operation=current['operation'],creates_completion=False,reason='observed empty hand and supported object outside destination'))
                            mon.active=None;decision=None;queue=[]
                        elif prediction and prediction.get('recovery_request')=='observe_above' and mon.samples[-1]['width']<.060:
                            recovery_pose=PoseHold(obs,env.env.robots[0].controller);recovery_pose.xyz[2]+=.030
                            target_observation_until=step+12;observation_wait=True
                            recovery.events.append(dict(frame=step,event='agent_requested_camera_raise',height_m=.030,gripper='retain',reason='placement progress review',oracle_pixel_used=False))
                # Local Agent chooses a bounded view/reset action for a stalled
                # drawer-opening stage; benchmark/physical acceptance is untouched.
                if os.environ.get('REPAIR_STAGNATION_OBSERVATION','0')=='1' and decision is not None and not observation_wait and decision.get('status')=='plan_ready':
                    current=decision['remaining_plan'][0];stage_key=(current['operation'],mon.entered)
                    count=stage_observation_attempts.get(stage_key,0)
                    recent=list(mon.rgb_rows)[-mon.settings.minimum_frames:]
                    poses=[np.asarray(r['sensor']['eef_xyz'],float) for r in recent if r.get('sensor')]
                    stationary=len(poses)==mon.settings.minimum_frames and recent[-1]['frame']-recent[0]['frame']>=mon.settings.stable_steps and max(float(np.linalg.norm(p-poses[0])) for p in poses)<=mon.settings.motion_m
                    if current['operation'] in ('open_top','open_middle','close_top','close_middle') and stationary and step-mon.entered>=180*(count+1) and count<2 and recovery.inspections<recovery.inspection_limit:
                        mon.diagnostics['observation_request_context']=dict(reason='drawer_has_not_completed_after_bounded_execution',selected_stage=current,reference=None,
                            elapsed_steps=step-mon.entered,previous_stage_observation_attempts=count,stationary_robot_window=dict(frames=[r['frame'] for r in recent],radius_m=mon.settings.motion_m,span_steps=recent[-1]['frame']-recent[0]['frame']),
                            allowed_tool='observe_clear_cabinet only if empty and clear; otherwise observe_only or none')
                        inspections_before=recovery.inspections
                        prediction=recovery.inspect(mon)
                        if recovery.inspections>inspections_before:stage_observation_attempts[stage_key]=count+1
                        width=mon.samples[-1]['width']
                        if prediction and prediction.get('recovery_request')=='observe_clear_cabinet' and prediction.get('held_object')=='none' and mon.held=='none' and (width>=.065 or width<.002):
                            level='top' if current['operation'].endswith('top') else 'middle'
                            axis=np.asarray(mon.calibration['closed_handles'][level]['opening_axis'],float);axis/=np.linalg.norm(axis)
                            opening=16 if width<.002 else 0
                            recovery_pose=OpenThenWithdraw(obs,env.env.robots[0].controller,axis,open_steps=opening)
                            target_observation_until=step+opening+12;observation_wait=True
                            recovery.events.append(dict(frame=step,event='agent_requested_stalled_drawer_observation',operation=current['operation'],offset_xyz_m=(axis*.040).tolist(),gripper='open before withdrawal',opening_steps=opening,
                                reason='Agent selected bounded view/reset after stationary open-stage failure',creates_completion=False,oracle_pixel_used=False))
                if ownership_replan_pending and step>=empty_gripper_until and not observation_wait:
                    recovery.replans+=1;ownership_replan_pending=False
                    mon.active=None;decision=None;queue=[]
                    # The observation Agent must refresh ownership after the tool;
                    # the planning Agent, not this script, chooses the next subgoal.
                    mon.diagnostics['observation_request_context']=dict(reason='empty_placement_hand_reopened_for_agent_replan',selected_stage=None)
                    recovery.inspect(mon)
                    recovery.events.append(dict(frame=step,event='agent_requested_replan',interrupted_operation='cheese_bowl',creates_completion=False,reason='empty-hand opening completed; regenerate from fresh observations'))
                if cap_recovery is not None:
                    finished=cap_recovery.advance(mon,recovery,step,decision)
                    if finished is not None:
                        target_observation_until=step;observation_wait=False;recovery_pose=None;queue=[]
                        mon.last_code_recovery_frame=step
                        if getattr(cap_recovery,'progress_v2',False):mon.observation_action_end=step
                        if finished['request_replan']:
                            mon.active=None;private_mon.active=None;decision=None
                    if cap_recovery.active is None and not observation_wait and decision is not None:
                        generated_pose=cap_recovery.maybe_start(mon,recovery,decision,obs,env.env.robots[0].controller,step,budget-step)
                        if generated_pose is not None:
                            recovery_pose=generated_pose;target_observation_until=min(budget,step+64);observation_wait=True;queue=[]
                if decision is None and not observation_wait:
                    hand=np.asarray(obs['robot0_eef_pos'])
                    mon.snapshot['robot']=dict(eef_world_xyz_m=hand.tolist(),gripper_width_m=mon.samples[-1]['width'],
                        hand_to_top_handle_m=None if geometry.get('top_handle.K1') is None else float(np.linalg.norm(hand-np.asarray(geometry['top_handle.K1']))),
                        hand_to_middle_handle_m=None if geometry.get('middle_handle.K1') is None else float(np.linalg.norm(hand-np.asarray(geometry['middle_handle.K1']))),
                        source='robot proprioception plus fresh measured RGB-D, not object pose truth',
                        handoff_for_close_step=next((e['preceding_close_step'] for e in reversed(recovery.events) if e['event']=='planning_agent_requested_cabinet_handoff'),None))
                    planning_facts=observed_states.planning_snapshot(mon.snapshot)
                    if os.environ.get('PLANNING_RELATION_REPAIR','1')=='1':
                        # Include a new same-frame accepted bootstrap inspection,
                        # while continuous observations above handle invalidation.
                        relation_geometry=trusted_relation_geometry(geometry,list(points.current.values()),step,mon.settings.confidence)
                        planning_relations.observe(case['case_id'],step,points.camera_id,mon.snapshot,relation_geometry,
                            mon.active,mon.events,recovery.events,mon.diagnostics)
                        planning_facts=planning_relations.planning_snapshot(planning_facts)
                    inp=dict(user_message=result['raw_user_message'],physical_state=planning_facts,completed_events=mon.events,
                             reference_availability=points.available(CATALOG),episode_id=case['case_id'],task_version=1,frame=step,
                             mode='S1 estimated visual/proprio facts; nullable unknown; no simulator state or Oracle next stage' if s1 else 'S0 simulator facts; no Oracle next stage')
                    # Round-trip detaches past-event lists from future mutation.
                    inp=json.loads(json.dumps(inp));generated=planner.generate(inp);records.append(dict(input=inp,result=generated))
                    (out/'agent_calls.json').write_text(json.dumps(records,indent=2))
                    if shadow:
                        reviews.append(dict(agent_call=len(records)-1,reference=shadow.snapshot(step)))
                        (out/'oracle_comparison.json').write_text(json.dumps(reviews,indent=2))
                    decision=generated['output']
                    if decision is None:status='agent_validation_failed';break
                    if decision['status']=='hold' and not decision['remaining_plan']:
                        hold_only=True
                    elif decision['status']=='need_observation' and recovery.inspections<recovery.inspection_limit:
                        recovery.pending='agent_requested';recovery_wait_until=step+8
                        recovery.events.append(dict(frame=step,event='agent_requested_observation',request=decision.get('request')))
                        decision=None;observation_wait=True
                    elif decision['status']!='plan_ready':status=decision['status'];break
                    stage_admission=None
                    if os.environ.get('CAP_STAGE_LIFECYCLE_GUARD','0')=='1' and decision is not None and not hold_only:
                        from stage_lifecycle import classify
                        stage_admission=classify(mon.active,decision['remaining_plan'],step,
                            mon.samples[-1]['width'],mon.held,recovery.visual_facts)
                        recovery.events.append(dict(frame=step,event='agent_plan_stage_admission',**stage_admission))
                        if stage_admission['mode']=='reject':
                            if recovery.inspections<recovery.inspection_limit:
                                recovery.pending='agent_requested';recovery_wait_until=step+8
                                mon.diagnostics['observation_request_context']=dict(reason=stage_admission['reason'],selected_stage=dict(mon.active))
                                decision=None;observation_wait=True
                            else:
                                status='need_observation';result['blocked_reason']=stage_admission['reason'];break
                    if decision is not None and decision.get('handoff_action')=='open_observed_empty_gripper':
                        from empty_hand_evidence import measured_clearance
                        current_clearance=measured_clearance(list(mon.rgb_rows),step)
                        if mon.held!='none' or recovery.empty_hand_proof is None or current_clearance is None or not .002<=mon.samples[-1]['width']<.065:
                            status='need_observation';result['blocked_reason']='Agent requested empty-hand opening without current independent clearance';break
                        recovery_pose=PoseHold(obs,env.env.robots[0].controller)
                        empty_gripper_until=step+16;target_observation_until=step+20;observation_wait=True
                        recovery.events.append(dict(frame=step,event='planning_agent_requested_verified_empty_open',
                            requested_by='planning_agent',tool='open_observed_empty_gripper',opening_steps=16,
                            commanded_Cartesian_translation_m=0.,gripper='open',proof=dict(recovery.empty_hand_proof),
                            current_clearance=current_clearance,creates_completion=False,oracle_pixel_used=False))
                    if decision is not None and decision.get('handoff_action')=='observe_clear_cabinet' and mon.events and mon.events[-1]['operation'].startswith('close_') and mon.held=='none' and (mon.samples[-1]['width']>=.065 or mon.samples[-1]['width']<.002):
                        level='top' if mon.events[-1]['operation'].endswith('top') else 'middle'
                        axis=np.asarray(mon.calibration['closed_handles'][level]['opening_axis'],float);axis/=np.linalg.norm(axis)
                        opening=16 if mon.samples[-1]['width']<.002 else 0
                        recovery_pose=OpenThenWithdraw(obs,env.env.robots[0].controller,axis,open_steps=opening)
                        target_observation_until=step+opening+12;observation_wait=True
                        recovery.events.append(dict(frame=step,event='planning_agent_requested_cabinet_handoff',preceding_operation=mon.events[-1]['operation'],preceding_close_step=mon.events[-1]['confirmed_step'],offset_xyz_m=(axis*.040).tolist(),opening_steps=opening,gripper='open before withdrawal',changes_subgoal=False,oracle_pixel_used=False))
                    if terminal and decision is not None:terminal.register_plan(decision['remaining_plan'])
                    if not hold_only and decision is not None:
                        if stage_admission is not None:
                            from stage_lifecycle import apply
                            new_stage_selected=apply(mon,decision['remaining_plan'][0],stage_admission)
                        else:
                            mon.select(decision['remaining_plan'][0]);new_stage_selected=True
                        if new_stage_selected:
                            selected_stages.append(dict(operation=decision['remaining_plan'][0]['operation'],entered_step=mon.entered,role='final' if len(decision['remaining_plan'])==1 else 'intermediate'))
                    if s1 and not hold_only and decision is not None and new_stage_selected:
                        private_mon.active=None
                        private_mon.select(decision['remaining_plan'][0])
                if terminal:
                    native_now=bool(initial['native_goal']) if not measurements else bool(measurements[-1]['goal_frame']['goal'])
                    check=terminal.check(mon,decision,native_now,step,case['target_task']);terminal_checks.append(check)
                    with (out/'terminal_checks.jsonl').open('a') as f:f.write(json.dumps(check)+'\n')
                    if check['passed']:
                        final_event=dict(operation=decision['remaining_plan'][0]['operation'],object=decision['remaining_plan'][0]['object'],outcome='completed',reason='scoped_native_goal_and_original_s1_release_constraints',entered_step=mon.entered,confirmed_step=step,source='benchmark_final_plus_s1_constraints')
                        events.append(final_event);mon.events.append(final_event);mon.active=None
                        result['terminal_evidence']=check;status='benchmark_final_with_observed_constraints';break
                if switch_terminal:
                    check=switch_terminal.check(measurements,decision)
                    if check.get('stop',check['passed']):
                        terminal_checks.append(check);result['terminal_evidence']=check
                        status='switch_oracle_contract_completed' if check['passed'] else 'benchmark_terminated';break
                if observation_wait:
                    if recovery_pose is None:recovery_pose=PoseHold(obs,env.env.robots[0].controller)
                    queue=[None]*4
                    if video:video.append_data(np.concatenate([np.ascontiguousarray(obs['agentview_image'][::-1,::-1]),np.ascontiguousarray(obs['robot0_eye_in_hand_image'][::-1,::-1])],axis=1))
                elif hold_only:
                    queue=[None]*3
                elif getattr(mon,'request_observation_hold',False):
                    if refine_hold_pose is None:refine_hold_pose=PoseHold(obs,env.env.robots[0].controller)
                    queue=[None]*3
                elif gate is not None and arm=='H':
                    # No policy request and no reference binding during hold; use fresh sensor control.
                    queue=[None]*3
                    if video:video.append_data(np.concatenate([resize(np.ascontiguousarray(obs['agentview_image'][::-1,::-1])),resize(np.ascontiguousarray(obs['robot0_eye_in_hand_image'][::-1,::-1]))],axis=1))
                else:
                    refine_hold_pose=None
                    begun=any(chunk.get('agent_operation')==decision['remaining_plan'][0]['operation']and chunk['step']>=mon.entered for chunk in chunks)
                    handoff=None if begun else post_return_handoff.propose(mon,recovery,decision,step)
                    if handoff is not None:
                        # No grasp controller step has executed. Cancel selection,
                        # preserve the task history, and replan on fresh evidence
                        # after observation; the clearance cannot inflate its lift.
                        if selected_stages and selected_stages[-1]['entered_step']==mon.entered:
                            selected_stages[-1]['cancelled_before_policy_for_observation']=True
                        decision=None;mon.active=None;private_mon.active=None
                        recovery_pose=PoseHold(obs,env.env.robots[0].controller)
                        target_observation_until=handoff.get('until',step+8);queue=[None]*4
                        if video:video.append_data(np.concatenate([np.ascontiguousarray(obs['agentview_image'][::-1,::-1]),np.ascontiguousarray(obs['robot0_eye_in_hand_image'][::-1,::-1])],axis=1))
                    else:
                        try:text,marker=points.bind(decision,step)
                        except ValueError as exc:
                            if recovery.missing_since is None:recovery.missing_since=step;recovery.missing_attempts+=1
                            if step-recovery.missing_since>=48 or recovery.missing_attempts>2:
                                status='need_observation';result['blocked_reason']=str(exc)+'; bounded observation recovery exhausted';break
                            if recovery_pose is None:recovery_pose=PoseHold(obs,env.env.robots[0].controller)
                            stage_key=(decision['remaining_plan'][0]['operation'],mon.entered)
                            if recovery.missing_inspections<2 and recovery.inspections<recovery.inspection_limit:
                                visual_key=(decision['reference']['entity'],decision['reference']['keypoint'])
                                mon.diagnostics['observation_request_context']=dict(reason='current_target_reference_missing',selected_stage=decision['remaining_plan'][0],reference=decision['reference'],
                                    missing_for_control_steps=step-recovery.missing_since,
                                    last_visual_reference_frame=points.last_image_points.get(visual_key,{}).get('frame'),
                                    stationary_observation_has_not_reacquired=step-recovery.missing_since>=8)
                                inspections_before=recovery.inspections
                                prediction=recovery.inspect(mon)
                                if recovery.inspections>inspections_before:recovery.missing_inspections+=1
                                if prediction and prediction.get('recovery_request')=='observe_above' and decision['remaining_plan'][0]['operation']=='cheese_bowl' and mon.samples[-1]['width']<.060:
                                    recovery_pose.xyz[2]+=.030;target_observation_until=step+12
                                    recovery.events.append(dict(frame=step,event='agent_requested_camera_raise',height_m=.030,gripper='retain',reason='target occlusion',oracle_pixel_used=False))
                            recovery.events.append(dict(frame=step,event='missing_point_observation',reference=decision['reference'],reason=str(exc)))
                            queue=[None]*4
                            if video:video.append_data(np.concatenate([np.ascontiguousarray(obs['agentview_image'][::-1,::-1]),np.ascontiguousarray(obs['robot0_eye_in_hand_image'][::-1,::-1])],axis=1))
                            text=None;marker=None
                        if text is not None:
                            recovery.point_recovered(step,decision['reference'],marker)
                            from policy_backend import build_replay_smol_inputs
                            req=build_replay_smol_inputs(obs,text,context,step,call)
                            assert req['observation/state'].shape==(8,) and marker['valid'] is False
                            Image.fromarray(req['observation/image']).save(out/('policy_main_%04d.png'%call))
                            if video:video.append_data(np.concatenate([np.asarray(Image.fromarray(req['observation/image']).resize((256,256))),np.asarray(Image.fromarray(req['observation/wrist_image']).resize((256,256)))],axis=1))
                            if snapshot_only:status='snapshot_plan_bound';chunks.append(dict(step=step,prompt=text,marker=marker));break
                            namespace=os.environ.get('HYBRID_POLICY_NAMESPACE','')
                            req.update(evaluation_case_id=(namespace+':'+case['case_id']) if namespace else case['case_id'],evaluation_call_index=call)
                            result['policy_request_namespace']=namespace
                            if call==0:req['evaluation_seed']=case['policy_seed']
                            ans=client.infer(req);assert ans['evaluation_call_index']==call
                            raw=np.asarray(ans['actions'],float);assert raw.shape==(10,7) and np.isfinite(raw).all()
                            execution=np.clip(raw[:3],-1,1);execution[:,6]=np.where(execution[:,6]>0,1.,-1.)
                            queue=list(execution);chunks.append(dict(step=step,prompt=text,marker=marker,prompt_token_length=ans['prompt_token_length'],oracle_reference=shadow.stage() if shadow else None,agent_operation=decision['remaining_plan'][0]['operation'],paired_request_sha256=ans['paired_request_sha256'],paired_response_memo_hit=ans['paired_response_memo_hit'],paired_action_sha256=ans['paired_action_sha256']));call+=1
            action=queue.pop(0)
            phase='hold_observe' if action is None else 'policy'
            if action is None and cap_recovery is not None and cap_recovery.active is not None:phase='recovery_code'
            if action is None:
                pose=recovery_pose if recovery_pose is not None else hold_pose if hold_only else refine_hold_pose if getattr(mon,'request_observation_hold',False) and refine_hold_pose is not None else gate.pose
                action=np.array(pose.action(obs))
                if recovery.grip_release_until is not None and step<recovery.grip_release_until or step<empty_gripper_until:action[6]=-1.
            elif recovery_pose is not None:recovery_pose=None
            obs,_,_,_=env.step(action.tolist());actions.append(dict(phase=phase,action=action.tolist()))
            if s1 and decision is not None and not hold_only:
                # Audit current readiness at every step; NEVER used for S1 control.
                private_mon.active=dict(decision['remaining_plan'][0]);private_mon.entered=mon.entered
            oracle_event=private_mon.observe(step+1)
            points.update_evidence(step+1,{},private_mon.memory_camera_id())
            if oracle_event and not any(e['operation']==oracle_event['operation'] and e['entered_step']==oracle_event['entered_step'] for e in oracle_events):oracle_events.append(oracle_event)
            if arm_id=='P0' and oracle_event and decision is not None and len(decision['remaining_plan'])>1:
                mon.events.append(dict(oracle_event));mon.active=None
                if oracle_event['outcome']=='completed' and oracle_event['operation'].startswith('grasp_'):mon.held=oracle_event['object'];mon.last_held_frame=step+1
                events.append(oracle_event)
                final=False
                if decision is not None and len(decision['remaining_plan'])>1:decision=None;queue=[]
            else:final=False
            sm=source.measure();tm=target.measure();frame=rt.frame(target,case['target_task']);ev=metric_evidence(env,case,contract)
            adjusted=bool(frame['goal'])
            for site,x in ev.get('regions',{}).items():adjusted=adjusted or bool(region_contains(x,rules['target_regions'][site]['margin_m']))
            measurements.append(dict(step=step+1,phase='policy',source=sm,target=tm,goal_frame=frame,metric_evidence=ev,adjusted_goal=bool(adjusted),oracle_stage_ready_for_audit=bool(oracle_event),oracle_checked_operation=None if decision is None or not decision['remaining_plan'] else decision['remaining_plan'][0]['operation']))
            measurements[-1]['observation_gate_active']=gate is not None
            if gate is not None:measurements[-1]['audit_object_positions']={k:list(v[-1]['object_position']) for k,v in private_mon.windows.items()}
            if shadow:shadow.observe(measurements[-1])
            if switch_terminal:
                check=switch_terminal.check(measurements,decision)
                if check['final_agent_stage']:
                    terminal_checks.append(check)
                    with (out/'terminal_checks.jsonl').open('a') as f:f.write(json.dumps(check)+'\n')
                if check.get('stop',check['passed']):
                    result['terminal_evidence']=check
                    status='switch_oracle_contract_completed' if check['passed'] else 'benchmark_terminated'
                    queue=[]
                    break

            # End only when the selected controller confirms its final stage. Benchmark scores are side-channel logs.
            if final:status='controller_final_stage_completed';break
        trace=dict(measurements=measurements,actions=actions,chunks=chunks,metric_initial=initial,agent_calls=records,execution_events=events)
        if measurements:result['metrics']=evaluate_episode(trace,case,contract,rules)
        result.update(status=status,actions=len(actions),agent_calls=len(records),execution_events=events,policy_calls=len(chunks),yolo_median_seconds=float(np.median(points.timings)),agent_seconds=[r['result']['seconds'] for r in records])
        with gzip.open(out/'trace.json.gz','wt') as f:json.dump(trace,f)
    except ProviderUnavailable as exc:
        result.update(status='blocked_external_api',valid_for_performance=False,error=str(exc),provider_error_code='Arrearage')
    except Exception:result.update(status='runtime_error',error=traceback.format_exc())
    finally:
        # Preserve partial execution even on infrastructure errors or missing points.
        result.setdefault('actions',len(actions));result.setdefault('agent_calls',len(records));result.setdefault('execution_events',events)
        result['terminal_checks']=terminal_checks
        result['s1_final_candidates_for_audit']=final_candidates
        result['observation_arm']=arm
        result['observation_gate_events']=gate_logs
        (out/'hold_events.json').write_text(json.dumps(gate_logs,indent=2))
        result['oracle_completion_events_for_scoring_only']=oracle_events
        result['selected_stages']=selected_stages
        if s1 and getattr(mon,'verifier',None):
            result['verifier_calls']=mon.verifier.calls
            result['p2_variant']=getattr(mon,'variant','BASE')
            result['verifier_triggers']=getattr(mon,'trigger_log',[])
        result['oracle_shadow_transitions']=shadow.executor.transitions if shadow else []
        with gzip.open(out/'trace.json.gz','wt') as f:json.dump(dict(measurements=measurements,actions=actions,chunks=chunks,metric_initial=initial,agent_calls=records,execution_events=events),f)
        if points:result['scene_memory_counts']=points.scene.counts
        if 'recovery' in locals():
            result['recovery_events']=recovery.events
            result['recovery_inspections']=recovery.observer.calls
            (out/'recovery/events.json').write_text(json.dumps(recovery.events,indent=2))
        if 'cap_recovery' in locals() and cap_recovery is not None:
            cap_recovery.finish_case(len(actions))
            result['code_recovery_calls']=cap_recovery.calls;result['code_recovery_events']=cap_recovery.events
        if s1 and hasattr(mon,'rule_verifier_gate'):result['rule_verifier_admission']=mon.rule_verifier_gate.events
        result['seconds']=time.monotonic()-start
        (out/'result.json').write_text(json.dumps(result,indent=2))
        if video:video.close()
        if points:points.close()
        if env:env.close()
    print(json.dumps(result),flush=True);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--port',type=int,default=19865);p.add_argument('--budget',type=int,default=240);p.add_argument('--snapshot-only',action='store_true');p.add_argument('--jobs',type=Path);p.add_argument('--groups',default='new_training_scene,close_then_switch,current_bowl_location');a=p.parse_args()
    cases=[json.loads(l) for l in (SMALL/'work/pi05_small722_data_v1/mini/cases.jsonl').read_text().splitlines()]
    byid={c['case_id']:c for c in cases}
    jobs=json.loads(a.jobs.read_text()) if a.jobs else [dict(case_id=next(c['case_id'] for c in cases if c['group']==g),budget=a.budget,cohort='') for g in a.groups.split(',')]
    planner=Planner();client=None if a.snapshot_only else WebsocketClientPolicy('127.0.0.1',a.port)
    if client:a.out.mkdir(parents=True,exist_ok=True);(a.out/'policy_metadata.json').write_text(json.dumps(client.get_server_metadata(),indent=2))
    for job in jobs:
        c=byid[job['case_id']]
        r=run(c,planner,client,a.out/job.get('cohort','')/c['case_id'],job.get('budget',a.budget),a.snapshot_only)
        if r['status']=='runtime_error':raise RuntimeError(r['error'])
