from pathlib import Path
from typing import Any
import numpy as np

def try_set_control_mode(env, control_mode: str) -> bool:
    candidates = [
        env,
        getattr(env, "env", None),
        getattr(env, "unwrapped", None),
        getattr(getattr(env, "env", None), "env", None),
    ]
    for obj in candidates:
        if obj is None:
            continue
        if hasattr(obj, "control_mode"):
            try:
                setattr(obj, "control_mode", control_mode)
                return True
            except Exception:
                pass
        if hasattr(obj, "set_control_mode"):
            try:
                obj.set_control_mode(control_mode)
                return True
            except Exception:
                pass
    return False

def make_libero_env(task, config):
    from libero.libero import get_libero_path
    from libero.libero.envs import OffScreenRenderEnv

    task_bddl_file = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
    env = OffScreenRenderEnv(
        bddl_file_name=str(task_bddl_file),
        camera_heights=config.env_img_res,
        camera_widths=config.env_img_res,
    )
    env.seed(config.seed)
    try_set_control_mode(env, config.control_mode)
    return env, task.language

def settle_env(env, initial_state: np.ndarray, wait_steps: int) -> dict[str, Any]:
    env.reset()
    obs = env.set_init_state(initial_state)
    dummy_action = np.asarray(get_libero_dummy_action(), dtype=np.float32)
    for _ in range(wait_steps):
        obs, _, _, _ = env.step(dummy_action.tolist())
    return obs

def rotate_libero_image(image: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(np.asarray(image)[::-1, ::-1])

def get_libero_dummy_action() -> list[float]:
    return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0]

