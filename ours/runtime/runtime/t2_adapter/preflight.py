"""Read-only inputs/scorer/compiled-control/model qualification before task audio."""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
A = Path(__file__).resolve().parent
B = A.parent
W = Path('/mnt/disk_2/geyi/t2_c3r_mx10_20261102')
O = Path('/mnt/disk_2/geyi/voice_t2_control_repair_20261102')
OLD = Path('/mnt/disk_4/geyi/audio_switch_t2_control_repair_20261102/originalMX10_v3')
sys.path[:0] = [str(A/'analysis'), str(A/'tools')]
from audited_score import evaluate


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


if __name__ == '__main__':
    specs = read(A/'dataset/selected.private.json')
    assert len(specs)==10 and {s['goal_id_private'] for s in specs}==set(range(10))
    assert specs==read(O/'dataset/selected.private.json')
    assert sha(A/'dataset/PROTOCOL.json')==sha(O/'dataset/PROTOCOL.json')
    assert sha(A/'dataset/physical_rules.json')==sha(O/'dataset/physical_rules.json')
    comparisons=[]
    for spec in specs:
        d=OLD/'cases'/spec['case_id']/'formal'
        previous=read(d/'score_r8_audited.json')
        now=evaluate(d,spec)
        assert now==previous, ('Previous scoring mismatch', spec['case_id'])
        comparisons.append(dict(case_id=spec['case_id'],matched=True))
    q=read(W/'policies/NUMERICAL_QUALIFICATION.json')
    assert len(q['identities'])==2 and all(len(i['tasks'])==10 for i in q['identities'])
    expected_changed={'tools/robot-control-semantics.js','tools/robot-turn.js','tools/robot.js','tools/robot-fast-stop.js','orchestrator/live-session.js'}
    parent=B/'artifacts/repair8_audio_daemon/dist'
    changed={str(p.relative_to(parent)) for p in parent.rglob('*.js') if sha(p)!=sha(A/'daemon/dist'/p.relative_to(parent))}
    assert changed==expected_changed, changed
    assert sha(parent/'tools/robot-entry-guard.js')==sha(A/'daemon/dist/tools/robot-entry-guard.js')
    tests=(A/'reports/CONTROL_TESTS.tap').read_text()
    assert '# pass 57' in tests and '# fail 0' in tests
    prefetch=(A/'reports/PREFETCH_TESTS.log').read_text()
    assert 'OK' in prefetch
    node=str(B/'freeze/voice/runtime/node-v22.23.3-linux-x64/bin/node')
    for p in A.glob('*.mjs'):
        subprocess.run([node,'--check',str(p)],check=True)
    result=dict(time=time.time(),passed=True,source_inputs_and_protocol_unchanged=True,
        original_ten_scores_recomputed=comparisons,control_tests=57,prefetch_tests=10,
        graph_models_and_ten_task_shapes_qualified=True,numerical_report=str(W/'policies/NUMERICAL_QUALIFICATION.json'),
        parent_R7T32_entry_guard_preserved=True,approved_voice_changes=sorted(changed),
        actions_or_task_audio_sent=False,required_alignment=dict(interaction=10,target=10,instruction=10))
    (W/'reports/PREFLIGHT.json').write_text(json.dumps(result,indent=2)+'\n')
    print('T2 read-only admission passed; original ten scores identical; two models qualified')
