"""Fixed original Agent-selected close stage from an identical full entry state.

This is a stage diagnostic, not autonomous planning/task SR. Physics has one
owner; all model HTTP waits use the tested G2.1 asynchronous bridge.
"""
import argparse,copy,gzip,hashlib,json,sys,threading,time,traceback
from pathlib import Path
import numpy as np

B=Path(__file__).resolve().parents[1];sys.path[:0]=[str(B),str(B/'g2'),str(B/'tools')]
from bootstrap import configure
from g22.context import restore_complete

def digest(values):
    h=hashlib.sha256()
    for key in sorted(values):
        a=np.ascontiguousarray(values[key]);h.update(key.encode());h.update(str(a.dtype).encode());h.update(str(a.shape).encode());h.update(a.tobytes())
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--context',type=Path,required=True);ap.add_argument('--arm',choices=['original','recovery'],required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--port',type=int,required=True);ap.add_argument('--gpu',type=int,required=True);ap.add_argument('--budget',type=int,default=400);args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=False);(args.out/'logs').mkdir()
    core,runner,authority=configure(args.out,args.gpu)
    from sim_runtime import GeometryRuntime,new_env,get_libero_path
    from bridge import SingleOwnerBridge,KernelRetired,EpisodeStopped
    from policy_backend import SmolHTTPClient,build_smol_inputs
    from sym_geometry import project
    from depth_sensor import read_depth,sensed_geometry
    from eval_inputs import resize
    fixture=json.loads((args.context.parent/'fixture.json').read_text());case=fixture['case']
    source=Path(fixture['source']);kernel=source/'kernels/g001'
    original=json.loads((kernel/'agent_calls.json').read_text())[0]['result']['output'];stage=original['remaining_plan'][0];decision=original
    meta=dict(original_case=case,stage=stage,decision=decision,task_instruction=original['complete_task'])
    import os
    os.environ['P012_DRAWER_CALIBRATION']=str(kernel/'observed_episode_drawer_reference.json')
    level=None
    if args.arm=='recovery':
        from g22.return_release import install
        install(SingleOwnerBridge)
    rt=GeometryRuntime();task=rt.suite.get_task(case['source_task']);env=new_env(Path(get_libero_path('bddl_files'))/task.problem_folder/task.bddl_file)
    context=dict(np.load(args.context));obs=restore_complete(env,context,authority);actual=authority.state.capture(env)
    common={k:bool(np.array_equal(actual[k],v,equal_nan=True))for k,v in context.items()if k in actual}
    assert all(common.values()),{k:v for k,v in common.items()if not v}
    assert np.array_equal(obs['agentview_image'],context['main_raw_image'])and np.array_equal(obs['robot0_eye_in_hand_image'],context['wrist_raw_image'])
    state=core.RobotState(args.out/'transaction_state');state.ready=True;state.mode='idle';state.obs=obs;state.observed_at=time.time();state.execution_backend='agent'
    case['authority_resource_root']=str(Path(case['snapshot_file']).parent.parent)
    bridge=SingleOwnerBridge(env,obs,state,args.out,case,runner,authority);bridge.install_hooks()
    if args.arm=='recovery':bridge.build_run_function()
    physical=[]
    def measure(phase):
        m=bridge.source.measure();error=float(np.linalg.norm(np.asarray(m['object_position'])-np.asarray(case['initial_xyz']['wine_bottle_1'])))
        physical.append(dict(world_step=bridge.physics_steps,controls=bridge.control_steps,simulation_time=float(env.sim.data.time),return_error_m=error,width_m=m['gripper_gap'],support=m['support_contact'],finger_contact=m['finger_contact'],released=m['gripper_gap']>=.065 and not m['finger_contact'],closed=error<=.035 and m['support_contact'] and not m['finger_contact'],phase=phase))
    bridge.measure=measure
    client=SmolHTTPClient(port=args.port);md=client.get_server_metadata()
    assert md['weights_sha256']=='30a620085ba28b8faec160ae68a9276d705ec0fb6d2fc9237e706379d0c5eebc'
    assert md['normalization_sha256']=='d4e03a22ef5d89a910e32c233a509465ad0d265381a06745917d69fd8924a635'
    state.policy_metadata=md
    history={}
    for p in [source/'episode_memory/points/detections.jsonl',kernel/'points/detections.jsonl']:
        if not p.exists():continue
        for line in p.read_text().splitlines():
            r=json.loads(line)
            if r['time_source']in('episode_start','instruction_takeover'):
                for point in r['points']:history[(r['time_source'],point['entity'],point['keypoint'])]=dict(point,time_source=r['time_source'],frame=r['frame'])
    points=runner.Points(args.out/'points',episode_id=state.episode,episode_frame_at_takeover=0);points.memory=copy.deepcopy(history)
    cold=time.monotonic();points.observe(np.ascontiguousarray(obs['agentview_image'][::-1,::-1]),0);cold=time.monotonic()-cold
    mon=runner.ObservedCompletion(history=history);verifier=runner.VisualVerifier(args.out/'verifier');mon.verifier=verifier
    from PIL import Image
    def old_image(name,fallback):
        p=kernel/'points'/name
        if not p.exists():p=source/'episode_memory/points'/name
        return resize(np.asarray(Image.open(p).convert('RGB')))if p.exists()else resize(fallback)
    verifier.configure(old_image('-1_episode_start.png',obs['agentview_image'][::-1,::-1]),old_image('0_instruction_takeover.png',obs['agentview_image'][::-1,::-1]),old_image('0_wrist.png',obs['robot0_eye_in_hand_image'][::-1,::-1]),meta['task_instruction'])
    ref=history[('episode_start','wine_bottle','K2')];yx=np.rint((np.asarray(ref['yx224'])+.5)*256/224-.5).astype(int).tolist()
    prompt=decision['policy_prompt_template'].replace('{episode_start.wine_bottle.K2}','<'+','.join(map(str,yx))+'>');first_inputs=build_smol_inputs(obs,prompt)
    (args.out/'initial_identity.json').write_text(json.dumps(dict(source=str(args.context),full_context_sha256=digest(context),restored_keys=common,body_state_identity=authority.state.identity(actual),expected_body_identity=fixture['controller_identity'],MAIN_exact=True,WRIST_exact=True,first_policy_arrays_sha256=digest({k:v for k,v in first_inputs.items()if isinstance(v,np.ndarray)}),prompt=prompt,seed=case['policy_seed']),indent=2))
    bridge.command('robot_start_task',instruction=meta['task_instruction']);bridge.generation=1;bridge.last_token=bridge.token();result_event=None;stale=0;calls=0;selected=False
    recovery=bridge.recovery_class(args.out/'recovery',meta['task_instruction']);release_pose=None;review_until=-1;clear_until=-1;clear_used=False
    def run():
        nonlocal result_event,stale,calls,selected,release_pose,review_until,clear_until,clear_used
        env=bridge.view;queue=[];step=0;obs=copy.deepcopy(bridge.obs);refine_hold=None
        bridge.env_lock.acquire()
        try:
            while bridge.control_steps<args.budget:
                try:
                    step=bridge.control_steps
                    if not queue:
                        points.observe(np.ascontiguousarray(obs['agentview_image'][::-1,::-1]),step)
                        eef=np.asarray(obs['robot0_eef_pos']);yx,valid=project(env.sim,eef);depth,cal=read_depth(env);geometry=sensed_geometry(list(points.current.values()),depth,cal)
                        mon.supply(step,resize(np.ascontiguousarray(obs['agentview_image'][::-1,::-1])),resize(np.ascontiguousarray(obs['robot0_eye_in_hand_image'][::-1,::-1])),geometry)
                        mon.rgb_rows[-1].update(camera_calibration=cal,image_points=list(points.current.values()),static_destination_geometry={})
                        mon.final_stage=False
                        event=mon.observe(step,eef.tolist(),np.asarray(obs['robot0_gripper_qpos']).tolist(),yx.tolist()if valid else None,list(points.current.values()))
                        if event:
                            result_event=dict(event,world_step=bridge.physics_steps,controls=bridge.control_steps);bridge.log('stage_diagnostic_event',event=result_event);break
                        if not selected:
                            mon.select(stage);mon.entered=-1196;selected=True # carried age: original stage entered44, last recorded1240
                        from hold_gate import PoseHold
                        if args.arm=='recovery':
                            from g22.return_release import inspect_stalled_return
                            if recovery.pending and recovery.grip_release_until is None and step>=review_until:
                                recovery.inspect(mon)
                                if recovery.grip_release_until is None:recovery.pending=None
                            if not recovery.pending and recovery.grip_release_until is None and inspect_stalled_return(mon,recovery,step,decision):review_until=step+8
                            if recovery.grip_release_until is not None and step>=recovery.grip_release_until:
                                recovery.grip_release_until=None;recovery.pending=None
                                if not clear_used and mon.samples[-1]['width']>=.065:
                                    mon.diagnostics['observation_request_context']=dict(reason='supported_in_place_release_executed_but_hand_may_still_intersect_old_object',released_object='wine_bottle',selected_stage=stage)
                                    prediction=recovery.inspect(mon);clear_used=True
                                    if prediction and prediction.get('recovery_request')=='clear_supported_object' and prediction.get('support_visible',{}).get('wine_bottle') is True:
                                        release_pose=PoseHold(obs,env.env.robots[0].controller);release_pose.xyz[2]+=.060;clear_until=step+16
                                        recovery.events.append(dict(frame=step,event='agent_requested_supported_object_clearance',object='wine_bottle',height_m=.060,creates_completion=False))
                        if step<12 or recovery.pending or recovery.grip_release_until is not None or step<clear_until:
                            if release_pose is None:release_pose=PoseHold(obs,env.env.robots[0].controller)
                            refine_hold=release_pose;queue=[None]*min(4,max(1,review_until-step)if recovery.pending and recovery.grip_release_until is None else 4)
                        elif mon.request_observation_hold:
                            from hold_gate import PoseHold
                            if refine_hold is None:refine_hold=PoseHold(obs,env.env.robots[0].controller)
                            queue=[None]*3
                        else:
                            refine_hold=None
                            req=build_smol_inputs(obs,prompt);req.update(evaluation_case_id='G22-stage:'+args.out.name+':'+args.out.parent.name,evaluation_call_index=calls)
                            if calls==0:req['evaluation_seed']=case['policy_seed']
                            calls+=1;ans=bridge.network('policy',client.infer,req)
                            actions=np.clip(np.asarray(ans['actions'],float)[:4],-1,1);actions[:,6]=np.where(actions[:,6]>0,1.,-1.);queue=list(actions)
                    action=queue.pop(0)
                    control=np.asarray(refine_hold.action(obs)if action is None else action)
                    if recovery.grip_release_until is not None and step<recovery.grip_release_until or step<clear_until:control[6]=-1.
                    obs,_,_,_=env.step(control)
                except KernelRetired:
                    stale+=1;queue=[]
                    if stale>2:raise
                    bridge.generation+=1;bridge.last_token=bridge.token()
                    obs,_,_,_=env.step(bridge.pose.action(bridge.obs))
        except EpisodeStopped:pass
        except BaseException:bridge.kernel_error=traceback.format_exc()
        finally:bridge.env_lock.release();bridge.worker_done.set()
    begin=time.monotonic();bridge.thread=threading.Thread(target=run,daemon=True);bridge.thread.start();tick=begin
    try:
        while not bridge.worker_done.is_set()and bridge.control_steps<args.budget and time.monotonic()-begin<600:
            if bridge.pump(time.monotonic()>=tick):tick=time.monotonic()+.05
            time.sleep(.002)
    finally:
        state._hold('cancelled','stage_diagnostic_end');bridge.close()
        with gzip.open(args.out/'physical_trace.json.gz','wt')as f:json.dump(physical,f)
        recent=physical[-5:];current_closed=len(recent)==5 and all(r['closed']for r in recent)
        closed_windows=[physical[i]['world_step']for i in range(4,len(physical))if all(r['closed']for r in physical[i-4:i+1])]
        skipped=getattr(verifier,'preflight_skips',0)
        result=dict(scope='development supported-return fixture: inherited stage age1196, first12 control observations both arms; only recovery arm permits Agent-requested release; not autonomous/task SR',context=str(args.context),case_id=case['case_id'],arm=args.arm,control_budget=args.budget,controls=bridge.control_steps,world_ticks=bridge.physics_steps,async_hold_ticks=bridge.async_hold_steps,model_calls=calls,close_visual_calls=len(verifier.calls),skipped_visual_calls=skipped,stage_event=result_event,observed_complete=result_event is not None,private_current_closed_5ticks=current_closed,private_ever_closed_5ticks=bool(closed_windows),first_private_close_world_step=closed_windows[0]if closed_windows else None,false_completion=result_event is not None and not current_closed,kernel_error=bridge.kernel_error,late_discarded=bridge.stale_discarded,stale_restarts=stale,seconds=time.monotonic()-begin,cold_detector_seconds=cold,policy_metadata=md,recovery_events=recovery.events,recovery_calls=recovery.observer.calls,source_initial_restored_only=True,geometry_view_requested=mon.request_geometry_observation,video=str(args.out/'gateway_environment.mp4'))
        (args.out/'result.json').write_text(json.dumps(result,indent=2));env.close();state.db.close()
    print(json.dumps({k:v for k,v in result.items()if k not in('policy_metadata','stage_event','recovery_calls','recovery_events')}),flush=True)

if __name__=='__main__':main()
