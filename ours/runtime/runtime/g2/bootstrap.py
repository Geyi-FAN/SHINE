"""Frozen shared imports. No simulator, detector or model starts on import."""
import importlib.util
import json
import os
import sys
from pathlib import Path

B = Path(__file__).resolve().parents[1]
F = B/'freeze/f28d'
V = B/'freeze/voice'


def configure(out, gpu):
    from c3r.profile import configure as configure_c3r
    os.environ['C3R_PROFILE'] = 'recovery'
    configure_c3r()
    c = json.loads((B.parent/'config/model.json').read_text())
    small = Path(c['legacy_support_root'])
    os.environ.update(json.loads((B/'freeze/handoff/ENVIRONMENT_REFERENCE.json').read_text())['values'])
    os.environ.update(HYBRID_EXECUTOR='pi05_e3_v4', MEMORY_VARIANT='E3',
        SMALL_ROOT=str(small), HYBRID_CASES_ROOT=str(small),
        SYMBOLIC_ROOT=str(small/'models/V3R'), MEMORY_WORK_ROOT=str(small/'work'),
        MEMORY_DATA_ROOT=str(small/'work/pi05_small722_data_v1'),
        MEMORY_ASSET_CONFIG=str(small/'local_assets.json'),
        MUJOCO_GL='egl', PYOPENGL_PLATFORM='egl', MUJOCO_EGL_DEVICE_ID=str(gpu),
        HYBRID_YOLO_DEVICE='0', HYBRID_YOLO_PYTHON=c['yolo_python'],
        HYBRID_YOLO_CHECKPOINT=c['yolo_checkpoint'],
        R34_LOCAL_ROLES=str(B.parent/'config/local_roles.json'),
        R34_TEXT_ROLES=str(B.parent/'config/text_roles.json'),
        R34_LOCAL_REQUEST_LOG=str(Path(out)/'local_requests'),
        P012_ROOT=str(out), P012_ARM='P2', HYBRID_COMPLETION='S1',
        HYBRID_FINAL_PROTOCOL='D1', S1_OBSERVE_ARM='B', HYBRID_ORACLE_REVIEW='0',
        HYBRID_M2_CURRENT_ONLY='0', HYBRID_CONTRACT_FILE=str(B/'freeze/study/data/contracts_private.json'),
        P012_DRAWER_CALIBRATION=c['drawer_calibration'],
        PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
        MKL_NUM_THREADS='1', NUMPY_MADVISE_HUGEPAGE='0')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(V/'robot_gateway'))
    import core
    sys.modules['gateway_core'] = core
    sys.modules['gateway_completion'] = sys.modules.pop('completion')
    sys.path[:0] = [str(F/'source'), str(B/'freeze/simulation/adapters'),
        str(B/'freeze/simulation/geometry'), str(B/'freeze/study/scripts'),
        str(B/'freeze'), str(B/'vendor/support/symbolic'),
        str(B/'vendor/support/memory'),
        str(B/'vendor/openpi/packages/openpi-client/src'), str(B/'vendor/support/metrics')]
    import text_transport, agent_transport
    from unified.transport import install as install_before_consumer_imports
    install_before_consumer_imports()
    agent_transport.request_json = text_transport.request_json
    spec = importlib.util.spec_from_file_location('frozen_g2_runner', B/'freeze/study/compat_source/run.py')
    runner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = runner
    spec.loader.exec_module(runner)
    import authority_bridge
    from unified.hooks import install_authority
    install_authority(core)
    return core, runner, authority_bridge
