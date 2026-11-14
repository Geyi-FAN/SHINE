"""Deployment paths only; does not change task, prompt or policy semantics.

Relative paths are resolved against the project root, never the caller's cwd.
An optional configs/runtime.local.json overrides the original neighboring layout.
"""

import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def load_runtime(root=ROOT, environ=None):
    """Return validated local paths/settings without creating files or services."""
    env = os.environ if environ is None else environ
    root = Path(root).resolve()
    defaults = {
        "evaluation_root": "../pi0.5_test_1001/evaluation_portable",
        "pi05_project": "../pi05_revision_p1",
        "pi05_python": "../openpi/.venv/bin/python",
        "node": "runtime/node/bin/node",
        "checkpoint": "../pi05_revision_p1/checkpoints/pi05_revision_p1/p1_full_20261003/11050",
        "openpi_data_home": "../.cache/openpi",
        "pi05_gpu": "2",
        "robot_gpu": "3",
        "xla_memory_fraction": ".65",
        "expected_experiment": "p1_full_20261003",
        "expected_checkpoint_step": "11050",
    }
    config_path = Path(env.get("VOICE_HARNESS_RUNTIME_CONFIG", "configs/runtime.local.json"))
    if not config_path.is_absolute():
        config_path = root / config_path
    overrides = json.loads(config_path.read_text()) if config_path.exists() else {}
    unknown = overrides.keys() - defaults.keys() - {"robot_python"}
    if unknown:
        raise ValueError("Unknown runtime configuration fields: " + ", ".join(sorted(unknown)))
    if not all(
        isinstance(value, (str, int, float)) and not isinstance(value, bool)
        for value in overrides.values()
    ):
        raise ValueError("Runtime settings must be strings or numbers")
    values = {**defaults, **overrides}
    for name in (
        "evaluation_root",
        "pi05_project",
        "pi05_python",
        "node",
        "checkpoint",
        "openpi_data_home",
    ):
        value = Path(values[name]).expanduser()
        values[name] = (value if value.is_absolute() else root / value).resolve()
    robot_python = Path(
        overrides.get("robot_python", values["evaluation_root"] / ".venv/bin/python")
    ).expanduser()
    values["robot_python"] = (
        robot_python if robot_python.is_absolute() else root / robot_python
    ).resolve()
    # Keep bundled Node precedence on the original host; allow a normal Node install.
    if (
        "node" not in overrides
        and not values["node"].exists()
        and shutil.which("node", path=env.get("PATH"))
    ):
        values["node"] = Path(shutil.which("node", path=env.get("PATH"))).resolve()
    values["pi05_gpu"] = env.get("PI05_GPU", str(values["pi05_gpu"]))
    values["robot_gpu"] = env.get("ROBOT_GPU", str(values["robot_gpu"]))
    fraction = float(values["xla_memory_fraction"])
    if not 0 < fraction <= 1:
        raise ValueError("xla_memory_fraction must be in (0, 1]")
    values["expected_checkpoint_step"] = str(values["expected_checkpoint_step"])
    return values
