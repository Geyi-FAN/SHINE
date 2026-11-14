"""Freeze three diagnostic cases BEFORE seeing their repaired outcomes."""
import hashlib
import json
import shutil
import time
from pathlib import Path

B = Path(__file__).resolve().parents[1]
SOURCE = Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102/R8/expanded96/dataset')
OUT = B/'reports/mini3'


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    shutil.copytree(SOURCE, OUT/'dataset')
    cases = json.loads((OUT/'dataset/selected.private.json').read_text())
    ids = ['T1_01_S1', 'T3_01_S1', 'T4_01_S1']
    selected = [next(c for c in cases if c['case_id'] == cid) for cid in ids]
    (OUT/'dataset/selected.private.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
    plan = dict(created=time.time(), cases=ids, denominator=3, scope='engineering real-PCM diagnostic, not the old T3 90-case re-evaluation',
                purpose=['placement release/support/40 real settling steps and receipt', 'mid-task change without reset', 'episode-start return reference'],
                actor='SmolVLA E3 v4 raw30000; unchanged', voice='R8 package; unchanged',
                thresholds='original R8 protocol physical v2.5 and interaction deadlines; unchanged',
                ports=[23081,23087,23089,33081], gpu=3, policy_port=19869,
                source_setup='same R8 controlled source window, explicitly diagnostic; each case initializes once')
    (OUT/'PLAN.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    files = {}
    for root in [B/'t3repair', B/'g2', B/'g21', B/'g22', B/'continuation', B/'repair6', B/'repair8', B/'freeze/f28d', B/'artifacts/repair8_audio_daemon/dist', OUT/'dataset']:
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.suffix in ('.py','.mjs','.js','.json','.txt') and '__pycache__' not in str(p):
                files[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    (OUT/'FREEZE.json').write_text(json.dumps(dict(time=time.time(), files=files), indent=2))
    original = Path('/mnt/disk_2/geyi/voice_f28d_audio_repair_20261102/freeze/f28d')
    differences = [str(p.relative_to(B/'freeze/f28d')) for p in (B/'freeze/f28d').rglob('*') if p.is_file() and '__pycache__' not in str(p) and hashlib.sha256(p.read_bytes()).digest() != hashlib.sha256((original/p.relative_to(B/'freeze/f28d')).read_bytes()).digest()]
    assert not differences, differences
    (OUT/'FROZEN_SOURCE_CHECK.json').write_text(json.dumps(dict(differences=differences, source_unchanged=True), indent=2))
    print(json.dumps(plan, ensure_ascii=False))


if __name__ == '__main__': main()
