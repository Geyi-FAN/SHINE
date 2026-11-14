import collections
import copy
import json
import time
import traceback
from pathlib import Path
import numpy as np
import torch
from .events import RevisionEvents, eligible_phase

def evaluate_case(case,kind,policy,rt,cfg,protocol,catalog,out,save_video=False,budget_override=None):
    from .env import make_libero_env,settle_env,rotate_libero_image
    from .render_context import bind_render_context
    from .contract import contract
    from .contract_checks import repair_contract
    source=case.get('source_task',case.get('task'));target=case.get('target_task',source)
    env,_=make_libero_env(rt.suite.get_task(source),cfg);env=bind_render_context(env)
    env.env.ignore_done=True;env.env.horizon=10000;env.env.hard_reset=False
    video=None;started=time.monotonic();queue=[];action_rows=[];measurement_rows=[]
    result=dict(case_id=case['case_id'],kind=kind,case=case,source_reached=kind=='normal',
        native_success=False,sgs=False,complete_revision_success=False,status='started',
        teacher_after_switch=False,memory_bridge_after_switch=False,reset_after_switch=False,
        old_task_actions=0,new_task_actions=0,hold_steps=0)
    def record(phase):
        if video:
            a=rotate_libero_image(obs['agentview_image']);b=rotate_libero_image(obs['robot0_eye_in_hand_image'])
            video.append_data(np.concatenate([a,b],axis=1))
    def step(action,phase):
        nonlocal obs
        action=np.asarray(action,float)
        if action.shape!=(7,) or not np.isfinite(action).all():raise ValueError('nonfinite_or_wrong_action')
        obs,_,_,_=env.step(action.tolist());action_rows.append(dict(phase=phase,action=action.tolist()))
        record(phase)
    try:
        states=torch.load(case['initial_state_file'],map_location='cpu',weights_only=False)
        obs=settle_env(env,states[case['initial_state_index']],protocol[kind]['settle_steps'])
        del states
        reference=rotate_libero_image(obs['agentview_image']).copy()
        result['initial_state_sha256']=__import__('hashlib').sha256(np.asarray(env.get_sim_state())[1:].tobytes()).hexdigest()
        def forbidden(*args,**kwargs):raise RuntimeError('reset_or_live_state_write_during_episode')
        for name in ('reset','set_init_state','set_state'):
            if hasattr(env,name):setattr(env,name,forbidden)
        if save_video:
            import imageio
            video=imageio.get_writer(str(out/(case['case_id']+'.mp4')),fps=20,macro_block_size=16)
            record('initial')
        source_mon=rt.monitor(env,source);target_mon=rt.monitor(env,target)
        initial=source_mon.measure();policy.begin_normal();events=None
        if kind=='revision':
            history=[];source_stable=0;phase=None;allowed=catalog[case['config']]
            source_budget=budget_override or protocol[kind]['source_budget']
            for t in range(source_budget+1):
                m=source_mon.measure();history.append(dict(before=m,after=m))
                source_stable=source_stable+1 if rt.frame(source_mon,source)['stable'] else 0
                phase=eligible_phase(history,source,allowed,source_stable)
                if phase:
                    if source!=target and m['goals'][str(target)]:
                        result['status']='new_goal_already_true_at_trigger';return result
                    result.update(source_reached=True,switch_step=t,trigger_phase=phase,
                        switch_state_sha256=__import__('hashlib').sha256(np.asarray(env.get_sim_state())[1:].tobytes()).hexdigest(),
                        cancelled_queued_actions=len(queue))
                    break
                if t==source_budget:break
                if not queue:queue=list(policy.predict_env_action_chunk_from_obs(obs,case['previous_instruction'],protocol[kind]['execution_horizon']))
                step(queue.pop(0),'source_actor');result['old_task_actions']+=1
            if not result['source_reached']:
                result['status']='source_not_reached';return result
            queue=[];c=copy.deepcopy(allowed[phase]);c['user_text']=case['current_instruction']
            ct=repair_contract(c,contract(c,initial,m))
            if c['branch']=='CONTINUE' and phase in ('M4','C6','D2','P2','K2'):
                ct['continue_completed_source']=source
            events=RevisionEvents(ct,initial,m,target,case['current_instruction'])
            result['contract']=ct
            policy.begin_revision(case['previous_instruction'],reference)
            instruction=case['current_instruction'];budget=budget_override or protocol[kind]['target_budget']
        else:
            instruction=case['instruction'];budget=budget_override or protocol[kind]['official_goal_budget']
        stable=0;last_grip=-1.
        for t in range(budget):
            if not queue:queue=list(policy.predict_env_action_chunk_from_obs(obs,instruction,protocol[kind]['execution_horizon']))
            action=queue.pop(0);last_grip=float(action[6]);step(action,'evaluated_model');result['new_task_actions']+=1
            frame=rt.frame(target_mon,target)
            if frame['goal'] and not result['native_success']:
                result.update(native_success=True,first_goal_step=t+1)
            if events:
                sm,tm=source_mon.measure(),target_mon.measure();events.update(t+1,sm,tm,env.env._eval_predicate)
                measurement_rows.append(dict(step=t+1,source=sm,target=tm,goal_frame=frame))
            stable=stable+1 if frame['stable'] else 0
            # Standard normal success is latched at first official goal; keep
            # rolling within the fixed 300-step budget only for supplemental SGS.
            if stable>=5:break
        if stable<5:
            result['status']='goal_reached_but_not_stably_released' if result['native_success'] else 'target_budget'
            return result
        # Retain the model's last gripper command; do not help it open the hand.
        survived=True
        for t in range(protocol[kind].get('success_hold_frames',40)):
            step([0.,0.,0.,0.,0.,0.,last_grip],'sgs_hold');result['hold_steps']+=1
            frame=rt.frame(target_mon,target)
            from .metrics import hold_frame_ok
            if not hold_frame_ok(frame,target) or (target in (0,7) and not frame['no_robot_contact']):survived=False
            if events:
                sm,tm=source_mon.measure(),target_mon.measure();events.update(result['new_task_actions']+t+1,sm,tm,env.env._eval_predicate)
                measurement_rows.append(dict(step=result['new_task_actions']+t+1,source=sm,target=tm,goal_frame=frame))
        result['sgs']=bool(survived and rt.frame(target_mon,target)['stable'])
        result['status']='sustained_goal_success' if result['sgs'] else 'goal_or_pose_broken_during_hold'
        return result
    except Exception as exc:
        result.update(status='runtime_error:'+str(exc),error=traceback.format_exc());return result
    finally:
        if 'events' in locals() and events:
            result['instruction_compliance']=events.result()
            result['complete_revision_success']=bool(result['sgs'] and events.result()['passed'])
        elif kind=='normal':result['complete_revision_success']=result['sgs']
        result.update(seconds=time.monotonic()-started,actions=len(action_rows),
            executed_input=policy.last_span_info if result['source_reached'] else None)
        import gzip
        with gzip.open(out/(case['case_id']+'.trace.json.gz'),'wt') as stream:
            json.dump(dict(actions=action_rows,measurements=measurement_rows),stream,ensure_ascii=False)
        if video:video.close()
        env.close()

def aggregate(out,expected=None):
    rows=[json.loads(p.read_text()) for p in Path(out).glob('*.json') if not p.name.startswith('summary')]
    def stats(rs):
        n=len(rs);reach=sum(r['source_reached'] for r in rs);s=sum(r['sgs'] for r in rs);c=sum(r['complete_revision_success'] for r in rs)
        return dict(total=n,source_reached=reach,native_success=sum(r['native_success'] for r in rs),sgs=s,complete=c,
            official_rate=sum(r['native_success'] for r in rs)/n if n else None,sgs_rate=s/n if n else None,
            complete_rate=c/n if n else None,conditional_sgs=s/reach if reach else None,
            statuses=dict(collections.Counter(r['status'] for r in rs)))
    def grouped(key):return {k:stats([r for r in rows if key(r)==k]) for k in sorted({key(r) for r in rows})}
    configs=grouped(lambda r:r['case'].get('config',str(r['case'].get('task'))))
    return dict(expected=expected,finished=len(rows),overall=stats(rows),by_config=configs,
        runtime_errors=sum(r['status'].startswith('runtime_error:') for r in rows),
        config_macro_sgs=float(np.mean([r['sgs_rate'] for r in configs.values()])) if configs else None,
        by_state=grouped(lambda r:f"T{r['case']['source_task']:02d}_"+r['case']['source_state'] if r['kind']=='revision' else 'normal'),
        by_category=grouped(lambda r:r['case'].get('category','normal')),
        by_training_coverage=grouped(lambda r:'normal' if r['kind']=='normal' else 'zero_training' if r['case']['train_trajectory_count']==0 else 'has_training'))
