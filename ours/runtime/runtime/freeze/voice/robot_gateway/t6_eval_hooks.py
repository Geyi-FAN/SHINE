"""Evaluator-only scene checkpoints; imported only by an isolated T6 gateway.

Not a voice tool. Ground truth and checkpoint paths never enter QA tool results.
The simulator thread owns every state capture/restore and reference action.
"""
from collections import deque
import base64
import concurrent.futures
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import pickle
import queue
import sqlite3
import time

import numpy as np


STATE_FIELDS = (
    'episode','version','mode','instruction','task_id','step','action_steps',
    'last_error','failure_detail','last_gripper','hold_pose','ready','last_infer_ms',
    'stale_results_dropped','reset_count','completion_monitor','completion_status',
    'normalization','verification_misses','inference_requests','task_record',
    'hold_reason','latest_evidence','last_interaction','scene_memory_status',
    'execution_backend','policy_metadata','agent_execution','task_intent_revision',
    'pending_proposal','pending_clarification','deferred_task','queue',
)
POINT_FIELDS=('memory','current','frame','episode_id','episode_frame_at_takeover',
              'instruction_version','camera_id','history_camera')
EXEC_FIELDS=('owner','epoch','decision','call','stale_plan_replans','initial','initial_episode','memory_wait_since')


def control_state(obj):
    result={}
    for k,v in vars(obj).items():
        if k in ('sim','model','robot_model','gripper_model'):continue
        if isinstance(v,(int,float,str,bool,type(None),np.ndarray,list,tuple,dict)):
            try:pickle.dumps(v);result[k]=copy.deepcopy(v)
            except Exception:pass
    return result


def monitor_state(monitor):
    return None if monitor is None else copy.deepcopy({k:v for k,v in vars(monitor).items() if k not in ('env','rt','mon')})


class T6EvaluationHooks:
    def __init__(self,env,state,memory,execution,recorder,root):
        from hybrid_planner.completion import Completion
        self.env,self.state,self.memory,self.execution,self.recorder=env,state,memory,execution,recorder
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.asset_root=Path(os.environ.get('VOICE_T6_ASSET_ROOT',str(self.root.parent))).resolve()
        self.requests=queue.Queue();self.frozen=False;self.closed=False
        self.initial_positions={name:env.sim.data.body_xpos[env.env.obj_body_id[name]].tolist()
            for name in ('akita_black_bowl_1','cream_cheese_1','wine_bottle_1','plate_1')}
        self.monitor=Completion(env,self.initial_positions,0,'')
        self.latest=None;self.elapsed_at_freeze=0;self.frozen_task_id=None
        self.initial_home=(state.obs['robot0_eef_pos'].copy(),state.obs['robot0_eef_quat'].copy())
        source=Path(__file__).read_bytes();(self.root/'hook_source.py').write_bytes(source)
        self.log('hooks_ready',scope='evaluation_only_not_model_tool',source_sha256=hashlib.sha256(source).hexdigest())

    def log(self,event,**data):
        with (self.root/'hook_events.jsonl').open('a') as f:
            f.write(json.dumps({'time':time.time(),'event':event,'step':self.state.step,**data},ensure_ascii=False)+'\n')

    def submit(self,body):
        future=concurrent.futures.Future();self.requests.put((body,future))
        return future.result(timeout=40)

    def inspect(self):
        self.monitor.observe(self.state.step)
        rows=copy.deepcopy(self.monitor.latest_rows)
        physical=copy.deepcopy(self.monitor.snapshot)
        from benchmark_metrics.predicates import drawer_gap
        gaps={k:float(drawer_gap(rows['bowl']['articulation'][k])) for k in ('top','middle')}
        confirmed=[name for name,window in self.monitor.windows.items() if len(window)>=5 and all(r['bilateral_finger_contact'] and r['target_contact'] and not r['support_contact'] for r in list(window)[-5:])]
        return dict(held_confirmed_5=confirmed,last_error=self.state.last_error,failure_detail=self.state.failure_detail,scene_memory=self.state.scene_memory_status,drawer_gaps=gaps,step=self.state.step,episode_id=self.state.episode,task_id=self.state.task_id,
                    task_version=self.state.version,state=self.state.mode,instruction=self.state.instruction,
                    frozen=self.frozen,observed_at=time.time(),physical=physical,measurements=rows,
                    eef_position=self.state.obs['robot0_eef_pos'].tolist(),
                    gripper_qpos=self.state.obs['robot0_gripper_qpos'].tolist(),
                    initial_positions=self.initial_positions,
                    scene_inventory_names=list(self.env.env.obj_body_id),
                    source='evaluator_only_current_simulator_evidence')

    def images(self,folder,obs):
        from PIL import Image
        folder.mkdir(parents=True,exist_ok=True)
        for name,key in [('MAIN','agentview_image'),('WRIST','robot0_eye_in_hand_image')]:
            Image.fromarray(np.ascontiguousarray(obs[key][::-1,::-1])).save(folder/(name+'.png'))

    def capture(self,folder,obs):
        folder=Path(folder).resolve()
        if not str(folder).startswith(str(self.asset_root)+'/'):
            raise ValueError('Checkpoint must be inside the isolated evaluation root')
        if folder.exists():raise ValueError('Checkpoint already exists; preserve first valid card')
        self.memory.worker.flush(20)
        self.frozen=True
        self.elapsed_at_freeze=0 if self.state.running_since is None else time.monotonic()-self.state.running_since
        self.frozen_task_id=self.state.task_id
        owner=self.memory.worker.owner;points=owner.points
        snapshot=dict(format='T6_checkpoint_v1',physical=self.env.sim.get_state().flatten(),
            simulator_ctrl=self.env.sim.data.ctrl.copy(),qacc_warmstart=self.env.sim.data.qacc_warmstart.copy(),
            hardware=[dict(controller=control_state(r.controller),gripper=control_state(r.gripper)) for r in self.env.env.robots],
            environment_counters={k:copy.deepcopy(getattr(self.env.env,k)) for k in ('timestep','cur_time','done') if hasattr(self.env.env,k)},
            robot_state={k:copy.deepcopy(getattr(self.state,k)) for k in STATE_FIELDS},
            running_elapsed=self.elapsed_at_freeze,
            execution={k:copy.deepcopy(getattr(self.execution,k)) for k in EXEC_FIELDS},
            monitor=monitor_state(self.execution.monitor),evaluator_monitor=monitor_state(self.monitor),initial_positions=copy.deepcopy(self.initial_positions),
            bridge=dict(episode=self.memory.episode,task=self.memory.task,reader=monitor_state(self.memory.reader)),
            worker={k:copy.deepcopy(getattr(self.memory.worker,k)) for k in ('episode','task','last_frame','version','status','published')},
            owner={k:copy.deepcopy(getattr(owner,k)) for k in ('episode','task','failed_episode')},
            points={k:copy.deepcopy(getattr(points,k)) for k in POINT_FIELDS},
            scene=copy.deepcopy({k:v for k,v in vars(points.scene).items() if k!='path'}),
            causal_prefix_directory=str(self.state.directory),
            captured_at=time.time())
        folder.mkdir(parents=True)
        with (folder/'runtime_checkpoint.pkl').open('wb') as f:pickle.dump(snapshot,f,pickle.HIGHEST_PROTOCOL)
        self.state.db.commit()
        with sqlite3.connect(folder/'history.sqlite') as target:self.state.db.backup(target)
        self.images(folder,obs)
        evidence=self.inspect()
        (folder/'physical.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        # Raw causal artifacts remain alongside the checkpoint. Current-method
        # internal M1 state is not an input supplied to another compared method.
        (folder/'provenance.json').write_text(json.dumps(dict(
            captured_before_any_QA=True,physical_state_not_teleported_during_construction=True,
            causal_prefix_directory=str(self.state.directory),
            current_method_state='restored only for the same Harness implementation',
            other_methods_must_rebuild_memory_from_raw_history=True,
            runtime_sha256=hashlib.sha256((folder/'runtime_checkpoint.pkl').read_bytes()).hexdigest()),indent=2)+'\n')
        self.log('card_captured',folder=str(folder),step=self.state.step)
        return dict(captured=True,folder=str(folder),physical=evidence)

    def restore(self,folder):
        folder=Path(folder).resolve()
        if not str(folder).startswith(str(self.asset_root)+'/'):raise ValueError('Invalid card path')
        self.memory.worker.flush(20)
        with (folder/'runtime_checkpoint.pkl').open('rb') as f:data=pickle.load(f)
        if data.get('format')!='T6_checkpoint_v1':raise ValueError('Unknown T6 checkpoint')
        self.execution.invalidate(self.state)
        self.env.sim.set_state_from_flattened(data['physical'])
        if 'simulator_ctrl' in data:self.env.sim.data.ctrl[:]=data['simulator_ctrl']
        if 'qacc_warmstart' in data:self.env.sim.data.qacc_warmstart[:]=data['qacc_warmstart']
        for r,h in zip(self.env.env.robots,data.get('hardware',[])):
            for k,v in h['controller'].items():setattr(r.controller,k,copy.deepcopy(v))
            for k,v in h['gripper'].items():setattr(r.gripper,k,copy.deepcopy(v))
        for k,v in data.get('environment_counters',{}).items():setattr(self.env.env,k,copy.deepcopy(v))
        self.env.sim.forward()
        self.env.env._update_observables(force=True)
        obs=self.env.env._get_observations(force_update=True)
        self.state.db.commit()
        with sqlite3.connect(folder/'history.sqlite') as source:source.backup(self.state.db)
        for k,v in data['robot_state'].items():setattr(self.state,k,copy.deepcopy(v))
        self.state.obs=obs;self.state.observed_at=time.time()
        self.state.reset_pending=None;self.state.request_context={}
        if hasattr(self.state,'execution_readiness'):
            self.state.execution_readiness=dict(self.state.execution_readiness,episode_id=self.state.episode)
        self.state.running_since=time.monotonic()-data['running_elapsed']
        self.elapsed_at_freeze=data['running_elapsed'];self.frozen_task_id=self.state.task_id
        self.initial_positions=copy.deepcopy(data['initial_positions'])
        for k,v in data['execution'].items():setattr(self.execution,k,copy.deepcopy(v))
        from hybrid_planner.completion import Completion
        def restored_monitor(values):
            if values is None:return None
            m=Completion(self.env,self.initial_positions,0,'')
            vars(m).update(copy.deepcopy(values));return m
        self.execution.monitor=restored_monitor(data['monitor'])
        self.execution.future=None
        self.memory.episode=data['bridge']['episode'];self.memory.task=data['bridge']['task']
        self.memory.reader=restored_monitor(data['bridge']['reader'])
        with self.memory.worker.cv:
            self.memory.worker.pending.clear()
            for k,v in data['worker'].items():setattr(self.memory.worker,k,copy.deepcopy(v))
            self.memory.worker.busy=False
            for k,v in data['owner'].items():setattr(self.memory.worker.owner,k,copy.deepcopy(v))
            points=self.memory.worker.owner.points
            for k,v in data['points'].items():setattr(points,k,copy.deepcopy(v))
            vars(points.scene).update(copy.deepcopy(data['scene']))
        self.monitor=restored_monitor(data.get('evaluator_monitor')) or Completion(self.env,self.initial_positions,0,'')
        self.frozen=True
        self.refresh_jpegs(obs)
        self.log('card_restored',folder=str(folder),episode=self.state.episode,task_id=self.state.task_id)
        return obs,dict(restored=True,frozen=True,evidence=self.inspect())

    def refresh_jpegs(self,obs):
        from PIL import Image
        data=[]
        for key in ('agentview_image','robot0_eye_in_hand_image'):
            buf=io.BytesIO();Image.fromarray(np.ascontiguousarray(obs[key][::-1,::-1])).save(buf,format='JPEG',quality=85)
            data.append(buf.getvalue())
        self.state.jpeg,self.state.wrist_jpeg=data
        self.state.obs=obs;self.state.observed_at=time.time()

    def reference_clear(self,obs):
        """Physical, logged open-gripper/retreat prefix; no qpos teleport."""
        if not self.frozen:raise ValueError('Reference clear requires evaluator freeze')
        target=obs['robot0_eef_pos'].copy()+np.array([0.,0.,.08])
        for i in range(32):
            delta=np.zeros(3) if i<8 else np.clip((target-obs['robot0_eef_pos'])/.05,-.35,.35)
            action=np.r_[delta,np.zeros(3),-1.]
            obs,_,_,_=self.env.step(action.tolist());self.state.step+=1
            self.state.obs=obs;self.state.observed_at=time.time();self.state.last_gripper=-1.
            if self.recorder:
                from types import SimpleNamespace
                record=SimpleNamespace(**{k:getattr(self.state,k) for k in ('episode','step','task_id','version','mode','instruction','completion_status','action_steps')})
                record.policy_action=False;record.captured_wall_time=time.time();record.captured_monotonic=time.monotonic()
                self.recorder.record(record,obs)
        self.state.queue.clear()
        self.state.hold_pose=(obs['robot0_eef_pos'].copy(),obs['robot0_eef_quat'].copy())
        self.refresh_jpegs(obs);self.memory.update(self.state,obs);self.memory.worker.flush(20)
        self.log('reference_release_clear',steps=32,source='fixed_reference_actions_no_object_pose_input')
        return obs,self.inspect()

    def reference_home(self,obs):
        """Fixed setup-only physical retraction; no object GT used in control."""
        if not self.frozen:raise ValueError('Reference home requires freeze')
        from scipy.spatial.transform import Rotation
        pos,quat=self.initial_home
        high=min(max(float(pos[2]),float(obs['robot0_eef_pos'][2]))+.04,float(pos[2])+.11)
        current_quat=obs['robot0_eef_quat'].copy()
        targets=[(np.r_[obs['robot0_eef_pos'][:2],high],current_quat,55),
                 (np.r_[pos[:2],high],current_quat,70),(pos,current_quat,60),(pos,quat,65)]
        count=0
        for xyz,q,n in targets:
            for _ in range(n):
                dr=(Rotation.from_quat(q)*Rotation.from_quat(obs['robot0_eef_quat']).inv()).as_rotvec()
                action=np.r_[np.clip((xyz-obs['robot0_eef_pos'])/.05,-.35,.35),np.clip(dr/.5,-.35,.35),-1.]
                obs,_,_,_=self.env.step(action.tolist());self.state.step+=1;count+=1
                self.state.obs=obs;self.state.observed_at=time.time();self.state.last_gripper=-1.
                if self.recorder:
                    from types import SimpleNamespace
                    record=SimpleNamespace(**{k:getattr(self.state,k) for k in ('episode','step','task_id','version','mode','instruction','completion_status','action_steps')})
                    record.policy_action=False;record.captured_wall_time=time.time();record.captured_monotonic=time.monotonic()
                    self.recorder.record(record,obs)
        self.state.queue.clear();self.state.hold_pose=(obs['robot0_eef_pos'].copy(),obs['robot0_eef_quat'].copy())
        self.refresh_jpegs(obs);self.memory.update(self.state,obs);self.memory.worker.flush(20)
        error=float(np.linalg.norm(obs['robot0_eef_pos']-pos))
        self.log('reference_home',version='bounded_height_then_reorient_v2',steps=count,error_m=error,source='fixed_initial_eef_reference_no_object_GT')
        if error>.025:raise RuntimeError('Reference home not reached: '+str(error))
        return obs,self.inspect()

    def boundary(self,obs):
        with self.state.lock:
            self.state.obs=obs
            self.latest=self.inspect()
        while not self.requests.empty():
            body,future=self.requests.get_nowait()
            try:
                with self.state.lock:
                    op=body['op']
                    if op=='inspect':result=self.inspect()
                    elif op=='freeze':
                        self.frozen=True
                        self.elapsed_at_freeze=0 if self.state.running_since is None else time.monotonic()-self.state.running_since
                        self.frozen_task_id=self.state.task_id
                        result=dict(frozen=True,evidence=self.inspect())
                    elif op=='resume':
                        if self.state.task_id==self.frozen_task_id:
                            self.state.running_since=time.monotonic()-self.elapsed_at_freeze if self.state.task_id else None
                        self.frozen=False;result=dict(frozen=False,evidence=self.inspect())
                    elif op=='capture':result=self.capture(body['folder'],obs)
                    elif op=='restore':obs,result=self.restore(body['folder'])
                    elif op=='reference_clear':obs,result=self.reference_clear(obs)
                    elif op=='reference_home':obs,result=self.reference_home(obs)
                    elif op=='gate':
                        import sys
                        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/audio_switch_benchmark'))
                        from t6_gate import gate_errors
                        proof=self.inspect();errors=gate_errors(body['card'],proof)
                        result=dict(passed=not errors,errors=errors,evidence=proof)
                    elif op=='capture_qa':
                        self.refresh_jpegs(obs)
                        from qa_image import qa_image
                        root=Path(__file__).resolve().parents[1]
                        image=qa_image(self.state.jpeg,self.state.wrist_jpeg,root/'data/visual_atlas_v2')
                        result=dict(image=base64.b64encode(image).decode(),main=base64.b64encode(self.state.jpeg).decode(),
                                    wrist=base64.b64encode(self.state.wrist_jpeg).decode(),evidence=self.inspect())
                    elif op=='images':
                        folder=Path(body['folder']).resolve()
                        if not str(folder).startswith(str(self.asset_root)+'/'):raise ValueError('Invalid image path')
                        self.images(folder,obs);result=dict(folder=str(folder),evidence=self.inspect())
                    else:raise ValueError('Unknown evaluator operation')
                future.set_result(result)
            except Exception as e:
                self.log('evaluation_operation_failed',operation=body.get('op'),error_type=type(e).__name__,detail=str(e)[:300])
                future.set_exception(e)
        if self.frozen:
            with self.state.lock:self.refresh_jpegs(obs)
        return obs,self.frozen
