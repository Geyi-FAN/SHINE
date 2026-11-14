#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec /mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python "$TASK_ROOT/tools/launch.py" policy "$@"
