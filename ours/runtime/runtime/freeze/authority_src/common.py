"""Isolated LIBERO runtime and atomic dataset metadata."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT
PORTABLE = ROOT / 'runtime'
LIBERO = PORTABLE / 'vendor/LIBERO/libero/libero'
TRAIN_MANIFEST = WORK / 'omnivla-interaction-revision-1070/manifest.portable.json'
TRAIN_DATA = WORK / 'omnivla_revision/omnivla_e1_e4/training_data'
P0_CHECKPOINT = WORK / '.cache/openpi/openpi-assets/checkpoints/pi05_libero'


def setup():
    sys.path[:0] = [str(PORTABLE / 'vendor/LIBERO'), str(PORTABLE / 'vendor'), str(PORTABLE)]
    os.environ.setdefault('MUJOCO_GL', 'egl')
    os.environ.setdefault('PYOPENGL_PLATFORM', 'egl')
    os.environ['LIBERO_CONFIG_PATH'] = str(ROOT / '.runtime/libero')
    os.environ.setdefault('NUMBA_CACHE_DIR', str(ROOT / '.runtime/numba'))
    os.environ.setdefault('XDG_CACHE_HOME', str(ROOT / '.runtime/cache'))
    import yaml
    path = ROOT / '.runtime/libero'; path.mkdir(parents=True, exist_ok=True)
    atomic(path / 'config.yaml', yaml.safe_dump(dict(benchmark_root=str(LIBERO),
        bddl_files=str(LIBERO / 'bddl_files'), init_states=str(LIBERO / 'init_files'),
        datasets=str(ROOT), assets=str(LIBERO / 'assets'))))


def atomic(path, text):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    tmp.write_text(text); tmp.replace(path)


def write(path, obj):
    atomic(path, json.dumps(obj, ensure_ascii=False, indent=2, default=json_default) + '\n')


def json_default(value):
    if hasattr(value, 'tolist'): return value.tolist()
    if isinstance(value, Path): return str(value)
    raise TypeError(type(value))


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''): h.update(b)
    return h.hexdigest()


def suite_runtime():
    import contextlib
    import io
    from libero.libero import benchmark
    from revision_eval.runtime import Runtime
    rt = Runtime()
    with contextlib.redirect_stdout(io.StringIO()):
        rt.suite = benchmark.get_benchmark_dict()['libero_goal']()
    rt.goal_cache = {}
    return rt


def make_pi05_policy(host, port, previous_context=False):
    # First inference compiles JAX. Eight concurrent compilations can exceed
    # websocket's default heartbeat timeout without an inference failure.
    from functools import partial
    from unittest.mock import patch
    import websockets.sync.client
    from revision_eval.policies import Pi05Policy
    connect = websockets.sync.client.connect
    with patch('websockets.sync.client.connect', partial(connect, ping_interval=None, ping_timeout=None)):
        return Pi05Policy(host, port, previous_context=previous_context)
