"""The only policy-action producer when VOICE_EXECUTION_MODE=agent.

Front-end tools still authorize task intents; neither Qwen voice nor the planner
can submit action arrays. Planning, grounding and inference are version fenced.
"""
import concurrent.futures
import copy
import json
import os
import time
from pathlib import Path


def identity(state):
    return state.episode, state.task_id, state.version


def bind_snapshot(decision, packet):
    import numpy as np
    from hybrid_planner.execution_profile import is_smol
    ref = decision['reference']
    if ref is None:
        from hybrid_planner.planner import CATALOG
        op=decision['remaining_plan'][0]['operation']
        if CATALOG[op]['reference'] is not None:raise ValueError('missing required reference')
        text=decision['policy_prompt_template']
        if '{' in text or '}' in text:raise ValueError('unbound position reference')
        return text,dict(yx=None,valid=False,source='no_point_operator',reference=None)
    key = '.'.join(ref[k] for k in ('time_source','entity','keypoint'))
    entry = packet['references'].get(key)
    if not entry or entry['point'] is None:
        raise ValueError('required YOLO point unavailable; no valid static cache: '+key)
    p = entry['point']
    point = np.asarray(p['yx224'],float)
    if point.shape != (2,) or not np.isfinite(point).all() or (point<0).any() or (point>223).any():
        raise ValueError('invalid YOLO point; cannot bind position reference')
    yx = np.rint((point+.5)*(256/224)-.5 if is_smol() else point).astype(int).tolist()
    text = decision['policy_prompt_template'].replace('{'+key+'}', '<'+','.join(map(str,yx))+'>')
    if '{' in text or '}' in text:
        raise ValueError('unbound position reference')
    marker = dict(yx=yx, valid=not is_smol() and decision['remaining_plan'][0]['kind']=='return',
                  source='yolo', reference=ref, resolution=entry['resolution'],
                  source_frame=p['frame'], source_time_source=p.get('time_source'),
                  observation_frame=packet['frame'], camera_transform_id=packet['camera'])
    return text, marker


class UnifiedExecution:
    def __init__(self, env, memory, client, root, planner=None, completion_type=None):
        from hybrid_planner.planner import make_planner
        if completion_type is None:
            from hybrid_planner.completion import Completion
            completion_type = Completion
        self.env, self.memory, self.client = env, memory, client
        self.planner = planner or make_planner()
        self.completion_type = completion_type
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.policy_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.owner = None; self.epoch = 0; self.future = None; self.orphans=[]
        self.decision = None; self.monitor = None; self.call = 0
        self.stale_plan_replans = 0
        self.initial = {}; self.initial_episode = None
        self.backend = type(self.planner).__name__
        self.executor_type = os.environ.get('HYBRID_EXECUTOR', 'pi05_v3r')
        self.memory_wait_since = None
        self.suspended_plan = None
        self.resume_candidate = None
        self.recovery_owner = None
        self.recovery_attempts = 0
        self.recovery_feedback = None
        self.wrong_hold_key = None
        self.wrong_hold_steps = []

    def log(self, kind, **data):
        with (self.root/'execution.jsonl').open('a') as f:
            f.write(json.dumps(dict(time=time.time(),kind=kind,backend=self.backend,**data))+'\n')

    def select_backend(self, state, backend, episode, version, config_path):
        """Called under state.lock; no reset, no actions, rejects concurrent intents."""
        from hybrid_planner.planner import make_planner
        if backend not in ('qwen','codex'):raise ValueError('invalid_planner_backend')
        if episode!=state.episode or version!=state.version:raise ValueError('stale_planner_request')
        if not state.ready or state.mode not in ('idle','paused','completed','cancelled','budget_exhausted','needs_review'):
            raise ValueError('pause_before_planner_switch')
        path=Path(config_path);config=json.loads(path.read_text())
        if backend not in config.get('allowed_backends',('qwen','codex')):raise ValueError('planner_backend_disabled')
        if state.execution_backend==backend:return state.snapshot()
        planner=make_planner(backend)
        config['backend']=backend
        temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(config,indent=2)+'\n');temporary.replace(path)
        self.invalidate(state)
        state._hold(state.mode,'planner_backend_changed')
        self.planner=planner;self.backend=type(planner).__name__;state.execution_backend=backend
        state.agent_execution=dict(backend=self.backend,phase='selected',generation=self.epoch)
        state.event('planner_backend_selected',dict(planner_backend=backend))
        return state.snapshot()

    def invalidate(self, state):
        if self.future:
            self.future.cancel()
            self.orphans.append(self.future)
        self.future = None; self.decision = None; self.epoch += 1
        state.agent_execution = dict(backend=self.backend,phase='completed' if state.mode=='completed' else 'invalidated',generation=self.epoch)
        self.call = 0
        self.stale_plan_replans = 0
        self.wrong_hold_key = None
        self.wrong_hold_steps = []
        if self.monitor: self.monitor.active = None
        self.log('generation_invalidated', identity=list(identity(state)), epoch=self.epoch)

    def _input(self, state, packet):
        record = state.task_record or {}
        raw = record.get('user_utterance') or record.get('requested_instruction') or state.instruction
        evidence=record.get('clarification_evidence')
        if (record.get('confirmed_proposal_id') or record.get('reference_memory_ids') or
            record.get('operation')=='robot_restore_task' or
            (getattr(self,'executor_type','pi05_v3r')=='smolvla_e3_v4' and record.get('source')=='qwen_realtime_current_user')):
            raw=state.instruction
        elif evidence and evidence.get('status')=='resolved':
            raw=evidence['resolved_instruction']
        inp = dict(user_message=raw,
                    original_user_message=record.get('user_utterance') or raw,
                    physical_state=copy.deepcopy(self.monitor.snapshot),
                    completed_events=copy.deepcopy(self.monitor.events),
                    reference_availability=[dict(x['reference'],available=x['point'] is not None) for x in packet['references'].values()],
                    episode_id=state.episode, task_version=state.version, frame=state.step,
                    mode='Agent planning + Oracle physical facts/completion + YOLO M1; no Oracle next stage')
        if self.recovery_feedback is not None:
            inp['execution_feedback'] = copy.deepcopy(self.recovery_feedback)
        return inp

    def _recover_wrong_grasp(self, state, current):
        """Stop stale actions after five observed wrong-object holds; Agent replans."""
        if os.environ.get('HYBRID_WRONG_OBJECT_RECOVERY','1') != '1':return False
        first = (self.decision or {}).get('remaining_plan') or []
        operation = first[0] if first else {}
        facts = self.monitor.snapshot
        held = facts.get('held_object')
        expected = operation.get('object')
        known = {'bowl', 'cheese', 'wine_bottle', 'plate'}
        wrong = operation.get('kind') == 'grasp' and held in known and expected in known and held != expected
        if not wrong:
            self.wrong_hold_key = None; self.wrong_hold_steps = []
            return False
        key = (expected, held)
        if key != self.wrong_hold_key:
            self.wrong_hold_key = key; self.wrong_hold_steps = []
        if not self.wrong_hold_steps or self.wrong_hold_steps[-1] != state.step:
            self.wrong_hold_steps.append(state.step)
        if len(self.wrong_hold_steps) < 5:return False
        feedback = dict(kind='wrong_object_held', operation=operation.get('operation'),
            expected_object=expected, observed_held_object=held,
            first_observed_step=self.wrong_hold_steps[0], confirmed_step=state.step,
            source='simulator_v2.5_hybrid_monitor', actions_stopped=True)
        state.queue.clear()
        self.invalidate(state)
        if self.recovery_attempts >= 2:
            state.failure_detail = dict(code='wrong_object_recovery_exhausted', **feedback,
                recovery='抓持对象与当前子任务不符，有限恢复未完成，已停止；任务尚未完成。')
            self.log('wrong_object_recovery_exhausted', identity=list(current), evidence=feedback)
            state._hold('needs_review', 'wrong_object_recovery_exhausted')
            state.event('task_needs_review', state.failure_detail)
            return True
        self.recovery_attempts += 1
        feedback.update(recovery_attempt=self.recovery_attempts, recovery_limit=2)
        self.recovery_feedback = feedback
        state.agent_execution = dict(backend=self.backend, phase='planning', generation=self.epoch,
                                     recovery_feedback=copy.deepcopy(feedback))
        self.log('wrong_object_recovery_started', identity=list(current), evidence=feedback)
        state.event('agent_recovery_started', copy.deepcopy(feedback))
        return True

    def _infer(self, decision, packet, task_key, call):
        import numpy as np
        binding_start=time.monotonic()
        text,marker=bind_snapshot(decision,packet)
        self.log("point_binding_finished", task_key=task_key, call=call, frame=packet["frame"], seconds=time.monotonic()-binding_start)
        if self.executor_type == 'smolvla_e3_v4':
            from policy_backend import build_smol_inputs
            req=build_smol_inputs(packet['observation'],text)
            execute_steps=4
        else:
            from eval_inputs import build_inputs
            from v3_markers import render_numpy
            req=build_inputs(dict(instruction=text),'A',packet['observation'],None)
            req['observation/image']=render_numpy(req['observation/image'],marker)
            execute_steps=3
        if os.environ.get('VOICE_EVAL_RECORD_DIR'):
            from PIL import Image
            directory = Path(os.environ['VOICE_EVAL_RECORD_DIR'])/'policy_inputs'/task_key.replace('/', '_')
            directory.mkdir(parents=True,exist_ok=True)
            Image.fromarray(req['observation/image']).save(directory/f'{call:06d}.png')
        req.update(evaluation_case_id=task_key,evaluation_call_index=call)
        if call==0:req['evaluation_seed']=7
        self.log("policy_started", task_key=task_key, call=call, frame=packet["frame"])
        start=time.monotonic();ans=self.client.infer(req)
        self.log("policy_finished", task_key=task_key, call=call, frame=packet["frame"], seconds=time.monotonic()-start, server_seconds=ans.get("inference_seconds"))
        actions=np.asarray(ans['actions'],float)
        if actions.shape!=(10,7) or not np.isfinite(actions).all():raise ValueError('invalid policy action chunk')
        actions=np.clip(actions[:execute_steps],-1,1);actions[:,6]=np.where(actions[:,6]>0,1.,-1.)
        return dict(actions=actions,seconds=time.monotonic()-start,prompt=text,marker=marker,
                    frame=packet['frame'],tokens=ans.get('prompt_token_length'))

    def _plan(self, inp):
        self.log('planning_started',input=inp)
        start=time.monotonic()
        result=self.planner.generate(inp)
        self.log('planning_finished',result=result,seconds=time.monotonic()-start)
        if str(result.get('error','')).startswith('planner_service_'):
            raise RuntimeError('planner_service_unavailable: bounded read-only planning retries exhausted; robot actions were not replayed; '+result['error'])
        return result

    def tick(self, state, obs):
        # Called with state.lock on the simulation thread. All slow work is async.
        self.orphans=[f for f in self.orphans if not f.done()]
        current=identity(state)
        recovery_owner=(state.episode,state.task_id,getattr(state,'task_intent_revision',0))
        if recovery_owner != self.recovery_owner:
            self.recovery_owner=recovery_owner;self.recovery_attempts=0;self.recovery_feedback=None
            self.wrong_hold_key=None;self.wrong_hold_steps=[]
        if self.initial_episode!=state.episode:
            self.initial_episode=state.episode
            self.initial={name:self.env.sim.data.body_xpos[self.env.env.obj_body_id[name]].tolist()
                          for name in ('akita_black_bowl_1','cream_cheese_1','wine_bottle_1','plate_1')}
        if self.owner!=current:
            previous=self.owner
            same_task=previous is not None and previous[:2]==current[:2]
            if same_task and state.mode=='paused' and self.decision is not None:
                self.suspended_plan=dict(episode=state.episode,task=state.task_id,intent_revision=state.task_intent_revision,
                    instruction=state.instruction,decision=copy.deepcopy(self.decision),
                    active=copy.deepcopy(self.monitor.active),entered=getattr(self.monitor,"entered",None))
                self.log('resume_plan_suspended',operation=self.decision['remaining_plan'][0]['operation'],intent_revision=state.task_intent_revision)
            if not same_task or state.mode in ('cancelled','resetting','superseded','error','needs_review','budget_exhausted','completed'):
                self.suspended_plan=None;self.resume_candidate=None
            candidate=self.suspended_plan if same_task and state.mode=='running' else None
            self.invalidate(state);self.owner=current
            self.memory_wait_since=None
            if previous is None or previous[:2]!=current[:2]:
                self.monitor=self.completion_type(self.env,self.initial,0,'')
                self.call=0
            if candidate:self.resume_candidate=candidate;self.suspended_plan=None
        facts=getattr(self.monitor,'drawer_qa_facts',None)
        previous_facts=getattr(state,'qa_drawers',{})
        if facts and (previous_facts.get('episode_id')!=state.episode or time.time()-previous_facts.get('observed_at',0)>=0.2):
            state.qa_drawers=dict(source='simulator_physical_facts_v2.5',episode_id=state.episode,
                                  observed_step=state.step,observed_at=time.time(),drawers=facts())
        if state.mode=='completed' and state.completion_status=='verified' and self.monitor:
            self.monitor.observe(state.step)
            check=getattr(self.monitor,'current_completion_valid',None)
            valid=check() if check else None
            previous=state.agent_execution.get('completion_current_verified')
            state.agent_execution.update(completion_current_verified=valid,completion_checked_step=state.step)
            if valid is not None and previous!=valid:
                state.event('completion_rechecked',dict(valid=valid,checked_step=state.step,evidence='same_v2.5_stage_predicates'))
            if valid is True and state.deferred_task:
                # Completion may have occurred during speech. Resume the single
                # pending handoff only after its input guard has been resolved.
                state._run_deferred()
                return
        if state.mode!='running' or not state.task_id:
            if self.future or self.decision:self.invalidate(state)
            return
        event=self.monitor.observe(state.step)
        if event:
            self.log('stage_event', identity=list(current),event=event)
            state.queue.clear()
            if event['outcome']!='completed':
                state.failure_detail=dict(code='task_constraint_violated',detail=event.get('reason','subgoal_physical_failure'),
                    operation=event.get('operation'),object=event.get('object'),evidence_step=event.get('confirmed_step'),
                    recovery='物体释放或任务约束未通过物理检查，已停止；任务尚未完成。检查现场后明确要求重新执行或修改任务。')
                self.invalidate(state);state._hold('needs_review','subgoal_physical_failure')
                state.event('task_needs_review',state.failure_detail);return
            last=self.decision and len(self.decision['remaining_plan'])==1
            self.invalidate(state)
            self.recovery_feedback = None
            if last:
                state._hold('completed','agent_plan_physically_verified')
                state.completion_status='verified'
                state.event('task_completed',dict(instruction=state.instruction,evidence='simulator_v2.5_hybrid_monitor',planner_backend=self.backend))
                state._run_deferred()
                return
        if self._recover_wrong_grasp(state,current):return
        packet=self.memory.worker.observation(*current)
        if packet is None or state.step-packet['frame']>20:
            if self.memory_wait_since is None:
                self.memory_wait_since=time.monotonic()
                self.log('memory_wait_started', identity=list(current), frame=state.step)
            return
        if self.memory_wait_since is not None:
            self.log('memory_wait_finished', identity=list(current), frame=state.step, seconds=time.monotonic()-self.memory_wait_since)
            self.memory_wait_since=None
        if self.resume_candidate is not None:
            candidate=self.resume_candidate;self.resume_candidate=None
            same=(candidate['episode']==state.episode and candidate['task']==state.task_id and
                  candidate['intent_revision']==state.task_intent_revision and candidate['instruction']==state.instruction)
            from hybrid_planner.planner import validate
            errors=validate(self._input(state,packet),candidate['decision'],m2=False) if same else ['task/intent changed']
            if not errors and candidate['active'] is not None:
                self.decision=candidate['decision'];self.monitor.active=candidate['active'];self.monitor.entered=candidate['entered']
                state.agent_execution=dict(backend=self.backend,phase='executing',generation=self.epoch,
                    operation=self.decision['remaining_plan'][0]['operation'],subgoal=self.decision['current_subgoal_template'],resumed_validated_plan=True)
                self.log('resume_plan_reused',identity=list(current),operation=self.decision['remaining_plan'][0]['operation'],actions_replayed=0)
            else:self.log('resume_plan_rejected_replanning',errors=errors)
        if self.future and self.future.done():
            work=self.future;self.future=None
            if self.work_owner!=(current,self.epoch):
                self.log('stale_result_discarded');return
            try:result=work.result()
            except Exception as exc:
                detail=str(exc)[:500]
                state.failure_detail=dict(code='point_missing' if 'YOLO point unavailable' in detail else 'planner_or_policy_error',detail=detail,operation=(self.decision or {}).get('current_subgoal_template'),recovery='定位点缺失：检查遮挡和相机，明确要求重新执行后才会重试；不会自动恢复。' if 'YOLO point unavailable' in detail else '规划或推理出错：查看错误详情；明确要求重新执行，仍失败时保留日志排查。')
                self.log('worker_error',error=type(exc).__name__+': '+detail);state._hold('needs_review','planner_or_policy_failure');state.event('task_needs_review',state.failure_detail);return
            if self.work_kind=='plan':
                from hybrid_planner.planner import validate
                out=result.get('output');inp=self._input(state,packet)
                self.log('agent_result',identity=list(current),input=self.plan_input,result=result)
                errors=validate(inp,out,m2=False)
                dynamic_errors=('already holding this object','cannot acquire with another object held',
                                'placement prerequisite not met','top drawer not open','current reference unavailable')
                if (errors and self.stale_plan_replans < 2 and
                        all(any(str(error).startswith(prefix) for prefix in dynamic_errors) for error in errors) and
                        not validate(self.plan_input,out,m2=False)):
                    # The Agent's plan was valid for its input, but the physical
                    # scene changed during the read-only request. Ask the Agent
                    # again with CURRENT evidence. Do not execute the stale plan,
                    # replay a robot tool, refresh task identity, or invent a stage.
                    self.stale_plan_replans += 1
                    self.log('plan_stale_physical_state',errors=errors,replan=self.stale_plan_replans,
                             original_frame=self.plan_input['frame'],current_frame=inp['frame'])
                    state.queue.clear();self.plan_input=inp
                    state.agent_execution=dict(backend=self.backend,phase='planning',generation=self.epoch,
                                               stale_plan_replans=self.stale_plan_replans)
                    self.future=self.pool.submit(self._plan,self.plan_input)
                    self.work_owner=(current,self.epoch)
                    return
                if errors or out['status']!='plan_ready':
                    # Empty plan/hold is not independent success evidence.
                    self.log('plan_not_executable',errors=errors,status=None if out is None else out['status'])
                    state.failure_detail=dict(code='plan_invalid' if errors else out['status'],detail='; '.join(map(str,errors))[:500] if errors else str(out.get('request',''))[:500],recovery='请回答当前澄清问题；若需要补充观察，检查遮挡后明确要求重新执行。仅说正确不会恢复动作。')
                    state._hold('needs_review','agent_requires_observation_or_clarification')
                    state.event('task_needs_review',state.failure_detail)
                    if not errors and out['status']=='need_clarification':
                        question=out.get('request')
                        if isinstance(question,str) and question:
                            state.command('robot_begin_clarification',dict(episode_id=state.episode,
                                expected_task_version=state.version,user_utterance=inp['user_message'],
                                voice_input_id='planner-source:'+str(state.task_id),question=question[:500],missing_slot='reference'),
                                'planner-clarification:'+str(state.task_id)+':'+str(state.version))
                    return
                self.decision=out
                # Controller-only guard; never supplied as an Oracle plan.
                self.monitor.select(dict(out['remaining_plan'][0],_final=len(out['remaining_plan'])==1))
                state.agent_execution=dict(backend=self.backend,phase='executing',generation=self.epoch,
                                           operation=out['remaining_plan'][0]['operation'],subgoal=out['current_subgoal_template'])
                state.event('agent_subgoal',dict(operation=out['remaining_plan'][0]['operation'],subgoal=out['current_subgoal_template'],planner_backend=self.backend))
            else:
                self.log('policy_result',identity=list(current),prompt=result['prompt'],marker=result['marker'],frame=result['frame'],tokens=result['tokens'])
                state.accept_actions(current[2],result['actions'],result['seconds']*1000,time.monotonic())
        if self.future or state.queue:return
        if self.decision is None:
            if len(self.orphans)>=2:return
            self.plan_input=self._input(state,packet)
            state.agent_execution=dict(backend=self.backend,phase='planning',generation=self.epoch)
            self.work_kind='plan';self.future=self.pool.submit(self._plan,self.plan_input)
        else:
            # Resolve latest prediction/cache every chunk. Agent only chose reference.
            self.work_kind='policy'
            key=current[0]+':'+current[1]+':'+str(current[2])+':'+str(self.epoch)
            self.future=self.policy_pool.submit(self._infer,copy.deepcopy(self.decision),packet,key,self.call)
            self.call+=1
        self.work_owner=(current,self.epoch)

    def close(self):
        self.pool.shutdown(wait=False,cancel_futures=True)
        self.policy_pool.shutdown(wait=False,cancel_futures=True)
