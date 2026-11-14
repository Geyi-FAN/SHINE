"""Local HTTP gateway; simulator owns physics, status lock excludes media I/O."""

import concurrent.futures
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from project_config import load_runtime

RUNTIME = load_runtime(ROOT)
EVAL = RUNTIME["evaluation_root"]
sys.path[:0] = [str(EVAL), str(EVAL / "vendor/LIBERO"), str(EVAL / "vendor")]
os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
os.environ.setdefault("NUMPY_MADVISE_HUGEPAGE", "0")
from core import RobotState, TaskError
from priority_stop import PriorityStop
from evaluation_budget import EvaluationActionBudget
from completion import LiberoEvidence
from grounding import inventory_from_names
from http_transport import GatewayHTTPServer,ResponsiveHandler,bounded_snapshot,deferred_rejection_context,RequestDiagnostics
from readiness import StageTimings, wait_episode_memory

state = RobotState(Path(os.environ.get("VOICE_ROBOT_DATA_DIR", str(ROOT / "data/episodes"))))
agent_executor = None
priority_stop = PriorityStop()
priority_stop_enabled = os.environ.get("VOICE_PRIORITY_STOP") == "1"
token = Path(os.environ["HARNESS_ROBOT_TOKEN_FILE"]).read_text().strip()
request_log_lock = threading.Lock()
request_diagnostics=RequestDiagnostics(os.environ.get('VOICE_EVAL_RECORD_DIR') or os.environ.get('VOICE_HTTP_DIAGNOSTICS_DIR'))


def run_robot():
    global agent_executor
    scene_memory = None
    execution = None
    evaluation_recorder = None
    timings = StageTimings(state.directory)
    timings.event("gateway_start", status="loading")
    first_action_identity = None
    budget_marker = os.environ.get("VOICE_EVAL_REQUEST_BUDGET_FILE")
    if budget_marker and not os.environ.get("VOICE_EVAL_RECORD_DIR"):
        raise ValueError("Independent evaluation budget requires evaluator recording")
    evaluation_budget = EvaluationActionBudget(budget_marker) if budget_marker else None
    try:
        # Isolated benchmark override; production retains its existing budget.
        task_wall_seconds = 90.0
        if os.environ.get('VOICE_EVAL_TASK_WALL_SECONDS'):
            if not os.environ.get('VOICE_EVAL_RECORD_DIR'):
                raise ValueError('Evaluation wall budget requires evaluator recording')
            task_wall_seconds = float(os.environ['VOICE_EVAL_TASK_WALL_SECONDS'])
            if not 1 <= task_wall_seconds <= 600:
                raise ValueError('Invalid evaluation wall budget')
        import numpy as np
        from PIL import Image
        import yaml
        from types import SimpleNamespace
        from scipy.spatial.transform import Rotation

        config_dir = ROOT / "data/libero"
        config_dir.mkdir(exist_ok=True, parents=True)
        assets = EVAL / "vendor/LIBERO/libero/libero"
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w',dir=config_dir,prefix='config.',suffix='.yaml',delete=False) as config_file:
            config_file.write(yaml.safe_dump(
                {
                    "benchmark_root": str(assets),
                    "bddl_files": str(assets / "bddl_files"),
                    "init_states": str(assets / "init_files"),
                    "datasets": str(EVAL),
                    "assets": str(assets / "assets"),
                }
            ))
        os.replace(config_file.name,config_dir/'config.yaml')
        os.environ["LIBERO_CONFIG_PATH"] = str(config_dir)
        from libero.libero import benchmark
        from revision_eval.env import make_libero_env, settle_env
        from revision_eval.policies import Pi05Policy

        suite = benchmark.get_benchmark_dict()["libero_goal"]()
        task = suite.get_task(0)
        eval_fixture = os.environ.get('VOICE_EVAL_FIXTURE')
        if eval_fixture:
            import h5py, hashlib
            fixture_path = Path(eval_fixture)
            fixture = json.loads(fixture_path.read_text())
            base = fixture_path.parent
            def asset(key):
                item = fixture['assets'][key]; path = (base / item['path']).resolve()
                if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                    raise ValueError('Evaluation fixture hash mismatch')
                return path
            task = SimpleNamespace(problem_folder='', bddl_file=str(asset('bddl_file')), language='dialogue evaluation scene')
            with h5py.File(asset('source_hdf')) as h:
                reset_state = h['states'][0].copy()
        else:
            reset_state = suite.get_task_init_states(0)[0]
        env, _ = make_libero_env(
            task, SimpleNamespace(env_img_res=256, seed=fixture["scene_seed"] if eval_fixture else 7, control_mode="relative")
        )
        # A live conversation outlives the benchmark's default 1000-step horizon.
        # Keep the same physical environment alive; task budgets are owned above.
        env.env.ignore_done = True
        obs = settle_env(env, reset_state, 10)
        timings.event("simulation_ready", status="ready", seconds=time.monotonic()-timings.started)
        evidence_reader = LiberoEvidence(env, suite)
        if os.environ.get('VOICE_EVAL_RECORD_DIR'):
            from evaluation_recording import EvaluationRecorder
            evaluation_recorder = EvaluationRecorder(os.environ['VOICE_EVAL_RECORD_DIR'], env)
        state.reset_count = 1
        agent_mode = os.environ.get("VOICE_EXECUTION_MODE", "legacy") == "agent"
        if agent_mode:
            sys.path.insert(0, str(ROOT))
            executor_type = os.environ.get('HYBRID_EXECUTOR', 'pi05_v3r')
            if executor_type == 'smolvla_e3_v4':
                from policy_backend import SmolHTTPClient
                client = SmolHTTPClient(port=int(os.environ.get('HYBRID_POLICY_PORT', '19865')))
            else:
                from openpi_client.websocket_client_policy import WebsocketClientPolicy
                client = WebsocketClientPolicy('127.0.0.1', int(os.environ.get('HYBRID_POLICY_PORT', '19865')))
            with timings.measure("policy_health"):
                metadata = client.get_server_metadata()
            expected = os.environ.get('HYBRID_CHECKPOINT')
            from policy_backend import build_smol_inputs, validate_policy_metadata
            if not expected: raise RuntimeError('Agent mode requires a configured checkpoint')
            validate_policy_metadata(metadata, expected, executor_type)
            if executor_type == 'smolvla_e3_v4':
                req = build_smol_inputs(obs, 'Task: open the middle drawer.\nCurrent subgoal: open the middle drawer using its handle and disengage from the cabinet.\nCoordinates: MAIN, 256x256, <y,x> pixels.\n')
            else:
                from eval_inputs import build_inputs
                req = build_inputs(dict(instruction='put the bowl on the plate'), 'A', obs, None)
            req.update(evaluation_case_id='gateway-warmup', evaluation_call_index=0, evaluation_seed=7)
            with timings.measure("policy_warmup"):
                client.infer(req)  # discarded warmup, never enters action queue
        else:
            policy = Pi05Policy("127.0.0.1", 8100, previous_context=False)
            metadata = policy.client.get_server_metadata()
            if (metadata.get("checkpoint_step") != RUNTIME["expected_checkpoint_step"]
                    or metadata.get("experiment") != RUNTIME["expected_experiment"]):
                raise RuntimeError("Unexpected policy checkpoint")
            policy.predict_env_action_chunk_from_obs(obs, "open the middle drawer of the cabinet", 3)
        if agent_mode or os.environ.get("VOICE_SCENE_MEMORY", "0") == "1":
            # Observation-only integration; the live action policy is unchanged.
            # Explicit runtime paths avoid mixing the gateway completion.py with
            # hybrid_planner.completion. Configure dependencies in the launcher.
            sys.path.insert(0, str(ROOT))
            from scene_memory_bridge import GatewaySceneMemory

            scene_memory = GatewaySceneMemory(env, state.directory / "scene_memory")
            scene_memory.update(state, obs)
            wait_episode_memory(state, scene_memory, timings)
        if agent_mode:
            from execution_router import RoutedExecution
            execution = RoutedExecution(env, scene_memory, client, state.directory / 'unified_execution')
            state.execution_backend = os.environ.get('HYBRID_PLANNER_BACKEND', 'qwen')
            agent_executor = execution
        with state.lock:
            state.scene_inventory = inventory_from_names(
                name
                for category in ("objects", "fixtures")
                for names in env.env.parsed_problem[category].values()
                for name in names
            )
            state.obs = obs
            state.observed_at = time.time()
            state.hold_pose = (obs["robot0_eef_pos"].copy(), obs["robot0_eef_quat"].copy())
            state.ready = True
            state.policy_metadata = metadata
            state.mode = "idle"
            state.event(
                "environment_ready",
                {
                    "suite": "libero_goal",
                    "initial_task": 0,
                    "init_index": 0,
                    "policy_metadata": metadata,
                    "reset_count": 1,
                },
            )
        timings.event("execution_ready", status="ready", episode_id=state.episode, seconds=time.monotonic()-timings.started)
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = None
        # Metadata belongs to the single outstanding future, across loop ticks.
        infer_version = observed_at = None
        next_tick = time.monotonic()
        last_image = 0.0

        def predict(snapshot, instruction):
            start = time.monotonic()
            actions = policy.predict_env_action_chunk_from_obs(snapshot, instruction, 3)
            return actions, (time.monotonic() - start) * 1000

        while True:
            if priority_stop_enabled:
                priority_stop.drain(state.command)
            now = time.monotonic()
            record_state = None
            jpeg_inputs = None
            reset_memory_pending = False
            with state.lock:
                if state.reset_pending:
                    obs = settle_env(env, reset_state, 10)
                    evidence_reader = LiberoEvidence(env, suite)
                    state.finish_reset(obs)
                    if scene_memory:
                        scene_memory.update(state, obs)
                        state.ready = False
                        state.mode = "loading"
                        reset_memory_pending = True
                    last_image = 0.0
                    next_tick = time.monotonic()
            if reset_memory_pending:
                wait_episode_memory(state, scene_memory, timings)
                with state.lock:
                    state.ready = True
                    state.mode = "idle"
                    state.event("execution_ready", dict(reason="reset_memory_ready", episode_id=state.episode))
            if future is not None and future.done():
                try:
                    actions, ms = future.result()
                    state.accept_actions(infer_version, actions, ms, observed_at)
                except Exception as exc:
                    with state.lock:
                        if infer_version == state.version and state.mode == "running":
                            state.last_error = type(exc).__name__ + ": policy inference failed"
                            state._hold("error", "policy_failure")
                future = None
            with state.lock:
                if priority_stop_enabled:
                    priority_stop.drain(state.command)
                if evaluation_budget:
                    evaluation_budget.before_action(state)
                if not execution and state.mode in ("running", "verifying") and state.completion_monitor:
                    try:
                        state.observe_completion(
                            evidence_reader.sample(state.completion_monitor.conditions())
                        )
                    except Exception as exc:
                        state.last_error = (
                            type(exc).__name__ + ": completion verifier failed; motion held"
                        )
                        state.completion_status = "verification_error"
                        state._hold("needs_review", "completion_verifier_failed")
                if (
                    state.mode in ("running", "verifying")
                    and state.running_since is not None
                    and (now - state.running_since > task_wall_seconds or state.action_steps >= 1200)
                ):
                    state._hold("budget_exhausted", f"{task_wall_seconds:g}_second_or_1200_action_budget")
                # Completion can promote a waiting task. Capture its takeover
                # after that promotion, but BEFORE its first action/inference.
                # Pause/resume/QA preserve task ID and all episode memory.
                if scene_memory:
                    scene_memory.update(state, obs)
                if execution:
                    execution.tick(state, obs)
                if not execution and future is None and state.mode == "running" and not state.queue:
                    snapshot = {k: v.copy() if hasattr(v, "copy") else v for k, v in obs.items()}
                    infer_version, observed_at = state.version, now
                    state.inference_requests += 1
                    future = pool.submit(predict, snapshot, state.instruction)
                # Explicit user pause freezes simulation time; no hold-action step.
                if state.mode != "paused":
                    action = state.next_action()
                    policy_action = action is not None
                    if action is None:
                        pos, quat = state.hold_pose
                        delta_rot = (
                            Rotation.from_quat(quat) * Rotation.from_quat(obs["robot0_eef_quat"]).inv()
                        ).as_rotvec()
                        action = np.r_[
                            np.clip((pos - obs["robot0_eef_pos"]) / 0.05, -0.5, 0.5),
                            np.clip(delta_rot / 0.5, -0.5, 0.5),
                            state.last_gripper,
                        ]
                    obs, _, _, _ = env.step(action.tolist())
                    state.obs = obs
                    state.observed_at = time.time()
                    state.step += 1
                    if execution:
                        execution.record_applied_action(state, policy_action)
                    action_identity = (state.episode, state.task_id, state.version)
                    if policy_action and action_identity != first_action_identity:
                        first_action_identity = action_identity
                        timings.event("first_applied_action", episode_id=state.episode, task_id=state.task_id, task_version=state.version, frame=state.step)
                    if evaluation_budget:
                        evaluation_budget.after_action(state, policy_action)
                    if evaluation_recorder:
                        record_state = SimpleNamespace(**{k:getattr(state,k) for k in (
                            'episode','step','task_id','version','mode','instruction','completion_status','action_steps')})
                        record_state.policy_action = policy_action
                        record_state.captured_wall_time = time.time()
                        record_state.captured_monotonic = time.monotonic()
                    if state.mode == "running" and policy_action:
                        state.hold_pose = (obs["robot0_eef_pos"].copy(), obs["robot0_eef_quat"].copy())
                if now - last_image >= 0.2:
                    jpeg_inputs = (state.episode, obs['agentview_image'], obs['robot0_eye_in_hand_image'])
                    last_image = now
            if priority_stop_enabled:
                priority_stop.drain(state.command)
            # No env.step occurs until the next iteration. Recorder physics is
            # still measured on this simulator thread at the captured step, but
            # ffmpeg, disk I/O and JPEG encoding no longer block status/control.
            if record_state is not None:
                evaluation_recorder.record(record_state, obs)
            if jpeg_inputs is not None:
                encoded=[]
                for image in jpeg_inputs[1:]:
                    buf=io.BytesIO()
                    Image.fromarray(np.ascontiguousarray(image[::-1, ::-1])).save(buf, format='JPEG', quality=85)
                    encoded.append(buf.getvalue())
                with state.lock:
                    if state.episode==jpeg_inputs[0]:state.jpeg,state.wrist_jpeg=encoded
            next_tick += 0.05
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -0.25:
                next_tick = time.monotonic()
                time.sleep(0)  # Yield to pending status/control threads under load.
    except Exception as exc:
        import traceback

        traceback.print_exc()
        with state.lock:
            state.ready = False
            state.queue.clear()
            state.mode = "error"
            state.last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            state.event("runtime_failed", {"error": state.last_error})
    finally:
        if evaluation_recorder:
            evaluation_recorder.close()
        if execution:
            execution.close()
        if scene_memory:
            scene_memory.close()


class Handler(ResponsiveHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, value, mime="application/json"):
        if os.environ.get('VOICE_EVAL_RECORD_DIR') and hasattr(self, '_eval_request'):
            path = Path(os.environ['VOICE_EVAL_RECORD_DIR'])/'api.jsonl'
            with request_log_lock, path.open('a') as f:
                f.write(json.dumps(dict(time=time.time(), path=self.path, request=self._eval_request, http_status=status, response=value), ensure_ascii=False)+'\n')
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        disconnected=False
        try:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if status == 401:
                self.close_connection=True
                self.send_header('Connection','close')
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError,TimeoutError):
            # A client deadline does not roll back an accepted operation and
            # cannot authorize a replay. Its persisted receipt remains intact.
            disconnected=True;self.close_connection=True
        finally:
            request_diagnostics.record(urlparse(self.path).path,status,
                getattr(self,'request_started',time.monotonic()),
                method=self.command,client_disconnected=disconnected)

    def authenticated(self):
        import hmac

        return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)

    def do_GET(self):
        if not self.authenticated():
            return self.respond(401, {"error": "authentication_required"})
        if self.path == "/status":
            value,waited=bounded_snapshot(state)
            if value is None:
                request_diagnostics.dump_busy_threads()
                return self.respond(503,dict(error='state_lock_busy',state='unavailable',
                    ready=False,state_verified=False,lock_wait_seconds=waited))
            return self.respond(200,value)
        if self.path == '/qa_frame.jpg':
            from qa_image import qa_image
            with state.lock:
                main,wrist=state.jpeg,state.wrist_jpeg
            if not main:return self.respond(503,{'error':'loading'})
            return self.respond(200,qa_image(main,wrist,ROOT/'data/visual_atlas_v2'),'image/jpeg')
        if self.path == "/memory":
            return self.respond(
                200, {"episode_id": state.episode, "events": state.memory(limit=20)}
            )
        if self.path == "/tasks":
            return self.respond(200, {"episode_id": state.episode, "tasks": state.task_history()})
        if urlparse(self.path).path == "/timeline":
            try:
                query = parse_qs(urlparse(self.path).query)
                return self.respond(
                    200,
                    state.timeline(
                        int(query.get("after", ["0"])[0]), query.get("episode", [None])[0]
                    ),
                )
            except ValueError:
                return self.respond(400, {"error": "invalid_cursor"})
        if self.path in ("/frame.jpg", "/wrist.jpg"):
            data = state.jpeg if self.path == "/frame.jpg" else state.wrist_jpeg
            return (
                self.respond(200, data, "image/jpeg")
                if data
                else self.respond(503, {"error": "loading"})
            )
        return self.respond(404, {"error": "not_found"})

    def do_POST(self):
        if not self.authenticated():
            return self.respond(401, {"error": "authentication_required"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16384:
                self.close_connection=True
                raise TaskError("invalid_request_size")
            body = json.loads(self.rfile.read(size))
            self._eval_request = body
            if self.path == '/planner/select':
                with state.lock:
                    if agent_executor is None:raise TaskError('agent_execution_unavailable')
                    result=agent_executor.select_backend(state,body.get('backend'),body.get('episode_id'),body.get('expected_task_version'),ROOT/'configs/unified_execution.local.json')
                    return self.respond(200,result)
            if self.path == "/interaction":
                return self.respond(200, state.record_interaction(body))
            if self.path == '/speech_activity':
                return self.respond(200, state.record_speech_activity(body))
            if self.path == "/interrupt":
                return self.respond(
                    200, state.interrupt(str(body.get("reason", "user_pause"))[:100])
                )
            if self.path == "/reset":
                return self.respond(
                    202, state.request_reset(body.get("args", {}), body.get("request_id", ""))
                )
            if self.path == "/tool":
                if priority_stop_enabled and body.get("name") == "robot_pause":
                    pending = priority_stop.submit(body.get("args", {}), body.get("request_id", ""))
                    return self.respond(200, priority_stop.wait(pending))
                result = state.command(
                    body["name"], body.get("args", {}), body.get("request_id", "")
                )
                return self.respond(200, result)
            return self.respond(404, {"error": "not_found"})
        except (TaskError, ValueError, KeyError, TypeError) as exc:
            detail={"status":"rejected","error":str(exc)[:300],"executed":False}
            update=deferred_rejection_context(state,getattr(self,'_eval_request',None))
            if update:detail['deferred_update']=update
            return self.respond(409,detail)


if __name__ == "__main__":
    server = GatewayHTTPServer(
        ("127.0.0.1", int(os.environ.get("VOICE_ROBOT_PORT", "8801"))), Handler
    )
    threading.Thread(target=run_robot, daemon=True).start()
    server.serve_forever()
