"""Readiness is evidence of loaded services, not visibility of every future point."""
import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path


class StageTimings:
    def __init__(self, directory):
        self.path = Path(directory) / 'startup_and_latency.jsonl'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.started = time.monotonic()

    def event(self, stage, **values):
        row = dict(time=time.time(), monotonic=time.monotonic(), stage=stage, **values)
        with self.lock, self.path.open('a') as out:
            out.write(json.dumps(row, ensure_ascii=False) + '\n')
        return row

    @contextmanager
    def measure(self, stage, **values):
        start = time.monotonic()
        try:
            yield
        except BaseException as exc:
            self.event(stage, status='error', seconds=time.monotonic()-start,
                       error=type(exc).__name__, **values)
            raise
        else:
            self.event(stage, status='ready', seconds=time.monotonic()-start, **values)


def memory_is_ready(snapshot, packet, episode, task, version):
    """Do not require non-null points: closed-drawer future targets may be invisible."""
    return bool(snapshot.get('state') == 'ready' and snapshot.get('current_identity') and
                snapshot.get('version_matches') and packet is not None and
                (packet.get('episode'), packet.get('task'), packet.get('version')) ==
                (episode, task, version))


def wait_episode_memory(state, memory, timings, timeout=180):
    start = time.monotonic()
    with state.lock:
        state.ready = False
        state.mode = 'loading'
        episode, task, version = state.episode, state.task_id, state.version
        state.execution_readiness = dict(phase='initializing_episode_memory', ready=False,
                                        episode_id=episode, policy_ready=True)
    while time.monotonic()-start < timeout:
        snapshot = memory.worker.snapshot()
        packet = memory.worker.observation(episode, task, version)
        with state.lock:
            if (state.episode, state.task_id, state.version) != (episode, task, version):
                raise RuntimeError('Episode changed during readiness barrier')
            state.scene_memory_status = snapshot
        if snapshot.get('state') == 'error':
            raise RuntimeError('Scene memory initialization failed: ' + snapshot.get('error', 'unknown'))
        if memory_is_ready(snapshot, packet, episode, task, version):
            timings.event('episode_memory_ready', status='ready', episode_id=episode,
                          seconds=time.monotonic()-start, frame=packet['frame'],
                          detector=snapshot.get('detector_startup'),
                          point_visibility_required=False)
            with state.lock:
                state.execution_readiness = dict(phase='ready', ready=True, episode_id=episode,
                    policy_ready=True, detector_ready=True, episode_memory_ready=True,
                    current_observation_ready=True, startup_seconds=time.monotonic()-timings.started,
                    cold_start_excluded_from_task_latency=True)
            return
        time.sleep(.05)
    timings.event('episode_memory_ready', status='timeout', episode_id=episode,
                  seconds=time.monotonic()-start, memory=snapshot)
    raise TimeoutError('Episode memory not ready; audio and tasks remain disabled')
