"""Episode-scoped M1 observer. Does not plan, score or command the robot.

Simulator facts are captured on the simulation thread. A single worker owns
Points/YOLO. Ordinary frames may coalesce; initialization and takeover frames
are ordered, immutable barriers. No simulator object crosses the worker boundary.
"""
import copy
import json
import threading
import time
from collections import deque
from pathlib import Path


class MemoryLifecycle:
    """Synchronous owner, also used by the asynchronous gateway adapter."""

    def __init__(self, root, points_factory):
        self.root = Path(root)
        self.factory = points_factory
        self.points = None
        self.episode = None
        self.task = None
        self.failed_episode = None

    def apply(self, packet):
        episode, frame = packet['episode'], packet['frame']
        if packet['kind'] == 'initialize':
            if episode == self.episode:
                raise ValueError('duplicate episode initialization')
            self.close()
            self.failed_episode = None
            self.points = self.factory(self.root / episode / 'points', episode_id=episode,
                                       episode_frame_at_takeover=0)
            self.episode, self.task = episode, None
            self.points.initialize_episode(packet['image'], packet['facts'], packet['camera'])
        else:
            if episode != self.episode or self.points is None:
                raise ValueError('stale or uninitialized episode')
            if self.failed_episode == episode:
                raise RuntimeError('episode memory failed; reset/reinitialize before reuse')
            self.points.update_evidence(frame, packet['facts'], packet['camera'])
            if packet['kind'] == 'takeover':
                if not packet['task'] or packet['task'] == self.task:
                    raise ValueError('duplicate/empty task takeover')
                self.points.begin_instruction(packet['image'], frame)
                self.task = packet['task']
            self.points.observe(packet['image'], frame)
        return dict(episode_id=episode, task_id=self.task, frame=frame,
                    detector_startup=getattr(self.points, 'detector_startup', None),
                    instruction_version=self.points.instruction_version,
                    historical_slots=len(self.points.memory),
                    static_slots=len(self.points.scene.cache),
                    fixed_slots=len(self.points.scene.anchors))

    def close(self):
        if self.points is not None:
            self.points.close()
            self.points = None


class AsyncMemoryLifecycle:
    def __init__(self, root, points_factory):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.owner = MemoryLifecycle(root, points_factory)
        self.cv = threading.Condition()
        self.pending = deque()
        self.episode = None
        self.task = None
        self.last_frame = -1
        self.version = None
        self.busy = False
        self.stopped = False
        self.status = dict(state='uninitialized', coalesced_frames=0)
        self.published = None
        self.thread = threading.Thread(target=self._work, name='m1-scene-memory', daemon=True)
        self.thread.start()

    def submit(self, kind, episode, task, frame, image, facts, camera, version, observation=None):
        # Copy immediately: env observation buffers and facts may be reused.
        packet = dict(kind=kind, episode=episode, task=task, frame=frame,
                      image=image.copy(), facts=copy.deepcopy(facts), camera=camera,
                      task_version=version)
        packet['observation'] = copy.deepcopy(observation)
        packet['submitted_monotonic'] = time.monotonic()
        with self.cv:
            if self.stopped:
                raise RuntimeError('scene memory stopped')
            if kind == 'initialize':
                if episode == self.episode:
                    raise ValueError('duplicate episode')
                self.pending.clear()
                self.episode, self.task, self.last_frame = episode, None, -1
                self.status = dict(state='initializing', coalesced_frames=0)
                self.published = None
            elif episode != self.episode:
                raise ValueError('old episode packet')
            if kind == 'observe' and task != self.task:
                raise ValueError('old task observation')
            if frame < self.last_frame:
                raise ValueError('noncausal frame')
            if kind == 'takeover':
                if not task or task == self.task:
                    raise ValueError('duplicate task takeover')
                self.task = task
            if kind == 'observe' and self.pending and self.pending[-1]['kind'] == 'observe':
                self.pending.pop()
                self.status['coalesced_frames'] += 1
            if len(self.pending) >= 32:
                raise RuntimeError('scene memory boundary backlog; no silent boundary loss')
            self.last_frame = frame
            self.version = version
            self.pending.append(packet)
            self.cv.notify_all()

    def _work(self):
        while True:
            with self.cv:
                self.cv.wait_for(lambda: self.pending or self.stopped)
                if self.stopped and not self.pending:
                    break
                packet = self.pending.popleft()
                self.busy = True
            start = time.monotonic()
            try:
                result = self.owner.apply(packet)
                result.update(state='ready', task_version=packet['task_version'])
                payload = None
                if observation := packet.get('observation'):
                    from hybrid_planner.planner import CATALOG
                    refs = {}
                    for spec in CATALOG.values():
                        ref = spec['reference']
                        if ref:
                            key = (ref['time_source'], ref['entity'], ref['keypoint'])
                            point, resolution = self.owner.points.resolve(*key)
                            refs['.'.join(key)] = dict(reference=ref, point=copy.deepcopy(point), resolution=resolution)
                    payload = dict(episode=packet['episode'], task=packet['task'], version=packet['task_version'],
                                   frame=packet['frame'], observation=observation, references=refs,
                                   camera=packet['camera'])
            except Exception as exc:
                payload = None
                self.owner.failed_episode = packet['episode']
                result = dict(state='error', error=type(exc).__name__ + ': ' + str(exc),
                              episode_id=packet['episode'], task_id=packet['task'], frame=packet['frame'])
            result.update(kind=packet['kind'], seconds=time.monotonic() - start,
                          queue_wait_seconds=start-packet['submitted_monotonic'],
                          completed_at=time.time())
            with self.cv:
                stale = packet['episode'] != self.episode or packet['task'] != self.task
                if not stale:
                    self.status.update(result)
                    self.published = payload
                with (self.root / 'lifecycle.jsonl').open('a') as f:
                    f.write(json.dumps(dict(result, stale_publication_discarded=stale)) + '\n')
                self.busy = False
                self.cv.notify_all()
        self.owner.close()

    def snapshot(self):
        with self.cv:
            return dict(self.status, expected_episode_id=self.episode, expected_task_id=self.task,
                        expected_task_version=self.version,
                        version_matches=self.status.get('task_version') == self.version,
                        pending=len(self.pending), busy=self.busy,
                        current_identity=(self.status.get('episode_id') == self.episode and
                                          self.status.get('task_id') == self.task),
                        mode='M1 memory observer; simulator validity; no action authority')

    def observation(self, episode, task, version):
        with self.cv:
            p = self.published
            if p and (p['episode'],p['task'],p['version']) == (episode,task,version):
                return copy.deepcopy(p)
            return None

    def flush(self, timeout=120):
        with self.cv:
            if not self.cv.wait_for(lambda: not self.pending and not self.busy, timeout):
                raise TimeoutError('scene memory worker did not finish')
            if self.status.get('state') == 'error':
                raise RuntimeError(self.status['error'])

    def close(self):
        with self.cv:
            self.pending.clear()
            self.stopped = True
            self.cv.notify_all()
        self.thread.join(timeout=15)
        if self.thread.is_alive():
            raise TimeoutError('scene memory worker still processing; see lifecycle log')


class GatewaySceneMemory:
    """Called by server.run_robot exclusively on its simulation thread."""

    def __init__(self, env, root):
        from hybrid_planner.points import Points
        from hybrid_planner.completion import Completion
        self.env = env
        self.completion_type = Completion
        self.worker = AsyncMemoryLifecycle(root, Points)
        self.episode = self.task = None
        self.reader = None

    def update(self, state, obs):
        import numpy as np
        if state.episode != self.episode:
            self.episode, self.task = state.episode, None
            # This reader provides cache validity only; no selected operation,
            # no task contract, no Oracle next-stage answer, no GT pixel output.
            self.reader = self.completion_type(self.env, {}, 0, '')
            kind = 'initialize'
        elif state.task_id and state.task_id != self.task:
            kind = 'takeover'
            self.task = state.task_id
        else:
            kind = 'observe'
        self.reader.observe(state.step)
        image = np.ascontiguousarray(obs['agentview_image'][::-1, ::-1])
        self.worker.submit(kind, self.episode, self.task, state.step, image,
                           self.reader.memory_evidence(), self.reader.memory_camera_id(), state.version,
                           observation=obs)
        state.scene_memory_status = self.worker.snapshot()

    def close(self):
        self.worker.close()
