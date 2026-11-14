import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENPI = Path(os.environ.get("OPENPI_ROOT", ROOT.parent / "openpi"))
VARIANT = os.environ.get("MEMORY_VARIANT", "A")
assert VARIANT in ("A", "B", "C", "D")
EVAL_ROOT = ROOT.parent / "pi0.5_test_1001/evaluation_portable"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_config():
    c = json.loads((ROOT / "configs" / f"{VARIANT}.json").read_text())
    work = Path(os.environ.get("MEMORY_WORK_ROOT", ROOT.parent))
    for key, value in list(c.items()):
        if isinstance(value, str) and value.startswith("/mnt/disk_2/geyi/"):
            c[key] = str(work / value.removeprefix("/mnt/disk_2/geyi/"))
    data_root = Path(os.environ.get("MEMORY_DATA_ROOT", work / "pi05_memory_ad_data_20261013"))
    c.update(prepared_dataset=str(data_root), data_root=str(data_root / "cache"),
             manifest=str(data_root / "train/episodes.json"),
             normal_manifest=str(data_root / "train/normal_samples.json"), batch_schedule=str(data_root / "cache/batches.npy"))
    c["initial_checkpoint"] = os.environ.get("INITIAL_CHECKPOINT", c["initial_checkpoint"])
    return c


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def source_hashes():
    paths = list((ROOT / "src").glob("*.py")) + list((ROOT / "configs").glob("*.json"))
    paths += list((ROOT / "scripts").glob("*.sh"))
    paths += list((OPENPI / "src/openpi").rglob("*.py"))
    paths += [OPENPI / "scripts/train.py"]
    return {str(p): sha256(p) for p in sorted(paths)}
