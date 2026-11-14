"""Reproducible, fail-closed merge of reviewed branch source deltas.

Only the independent candidate is written. No source run or shared service is
modified. Compiled readable JS is treated as the actual input source artifact.
"""
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

W = Path(__file__).resolve().parents[1]
# FROZEN_BUILD_GUARD: a new revision requires a separate checkout.
if (W/'FREEZE.json').exists():
    raise RuntimeError('Refuse to rebuild an already frozen runtime; create a new revision')
B = W / 'runtime'
ROOTS = json.loads((W / 'provenance/BRANCH_SOURCE_ROOTS.json').read_text())
VOICE = json.loads((W / 'provenance/VOICE_SOURCE_INVENTORY.json').read_text())
RECORDS = []


def record(dst, sources, reason):
    RECORDS.append(dict(destination=str(dst.relative_to(W)), sources=[str(x) for x in sources],
                        reason=reason, sha256=hashlib.sha256(dst.read_bytes()).hexdigest()))


def replace_defs(dst, source, names, class_name=None):
    tree = ast.parse(dst.read_text())
    other = ast.parse(source.read_text())
    source_defs = {n.name: n for n in other.body if isinstance(n, ast.FunctionDef)}
    owner = tree if class_name is None else next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    for name in names:
        replacement = source_defs[name]
        matches = [i for i, n in enumerate(owner.body) if getattr(n, 'name', None) == name]
        if len(matches) == 1:
            owner.body[matches[0]] = replacement
        elif not matches and class_name is None:
            owner.body.append(replacement)
        else:
            raise ValueError((dst, name, matches))
    dst.write_text(ast.unparse(ast.fix_missing_locations(tree)) + '\n')
    record(dst, [source], 'AST definition merge preserving unrelated methods: ' + ','.join(names))


def merge_python_authority():
    authority = B / 'freeze/voice/robot_gateway'
    t4 = Path(ROOTS['t4']) / 't4_adapter/python'
    t5 = Path(ROOTS['t5']) / 'authority'
    replace_defs(authority / 'grounding.py', t4 / 'grounding.py',
                 ['action_clauses', 'slots', 'validate_pronoun_source'])
    replace_defs(authority / 'grounding.py', t5 / 'grounding.py',
                 ['command_content', 'explicit_object_correction', 'explicit_object_selection', 'validate_grounding'])
    semantics = authority / 'semantics.py'
    shutil.copy2(t5 / 'semantics.py', semantics)
    # Both branches changed this function. Normalize formatting, then perform a
    # true three-way merge of the independent permission and pronoun additions.
    ancestor = Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102/freeze/voice/robot_gateway/semantics.py')
    def function(path):
        return ast.unparse(next(n for n in ast.parse(path.read_text()).body
                                if isinstance(n, ast.FunctionDef) and n.name == 'inspect_semantics')) + '\n'
    with tempfile.TemporaryDirectory() as folder:
        paths = [Path(folder)/name for name in ['t5.py', 'base.py', 't4.py']]
        for p, s in zip(paths, [t5/'semantics.py', ancestor, t4/'semantics.py']):
            p.write_text(function(s))
        q = subprocess.run(['git', 'merge-file', '--stdout', *map(str, paths)], capture_output=True, text=True)
        if q.returncode:
            raise RuntimeError('Unresolved Python semantic conflict: ' + q.stdout)
        merged = Path(folder)/'merged.py'
        merged.write_text(q.stdout)
        replace_defs(semantics, merged, ['inspect_semantics'])
    record(semantics, [ancestor, t4/'semantics.py', t5/'semantics.py'], 'Clean three-way AST-normalized merge')
    shutil.copy2(t5/'clarification.py', authority/'clarification.py')
    record(authority/'clarification.py', [t5/'clarification.py'], 'Cumulative F01-F10 clarification evidence and current proposal')
    replace_defs(authority/'core.py', t5/'core_methods.py',
                 ['record_interaction', '_resolve_proposal', '_command'], class_name='RobotState')
    replace_defs(authority/'native_execution.py', t5/'native_candidate.py', ['native_candidate'])
    shutil.copy2(t4/'speech_relisten.py', authority/'speech_relisten.py')
    record(authority/'speech_relisten.py', [t4/'speech_relisten.py'], 'Object identity correction retains actual action and source evidence')


def resolve_js(source, rel, branch):
    pattern = r'^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*\n'
    def choose(match):
        left, right = match.group(1), match.group(2)
        if not right.strip():
            return left
        if not left.strip():
            return right
        if all(not s.strip() or s.lstrip().startswith('import ') for s in (left + right).splitlines()):
            return ''.join(dict.fromkeys((left + right).splitlines(keepends=True)))
        # T7 already generalized F07's callback and additionally preserves QA,
        # current-task evidence and explicit pending cancellation.
        if branch == 't5' and rel == 'orchestrator/live-session.js' and 'recordRobotTurnObservation(context, turn, observed)' in left:
            current = (W/'voice/dist'/rel).read_text()
            start = current.index('recordRobotTurnObservation(context, turn, observed) {')
            body = current[start:current.index('\n    }', start)]
            assert 'turn.status' in body and 'acknowledgeNoChange' in body
            return left
        if branch == 't4' and rel == 'tools/robot-turn.js' and 'explicitObjectSelection(text)' in left and '(?:keep|maintain|leave)' in right:
            return left + right
        raise RuntimeError(f'Unresolved {branch} JS conflict in {rel}:\n{match.group()}')
    result = re.sub(pattern, choose, source, flags=re.M | re.S)
    assert not re.search(r'^<<<<<<<|^=======|^>>>>>>>', result, re.M), rel
    return result


def merge_voice():
    ancestor = Path(VOICE['common']['root'])
    dstroot = W/'voice/dist'
    for rel in VOICE['t7']['files']:
        dst = dstroot/rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(VOICE['t7']['root'])/rel, dst)
    for branch in ['t5', 't4']:
        other = Path(VOICE[branch]['root'])
        for rel, meta in VOICE[branch]['files'].items():
            if not rel.endswith('.js') or meta['sha256'] == VOICE['common']['files'].get(rel, {}).get('sha256'):
                continue
            dst = dstroot/rel
            if not (ancestor/rel).exists():
                if dst.exists() and dst.read_bytes() != (other/rel).read_bytes():
                    raise RuntimeError('Conflicting new JS module: ' + rel)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(other/rel, dst)
            else:
                q = subprocess.run(['git', 'merge-file', '--stdout', str(dst), str(ancestor/rel), str(other/rel)], capture_output=True, text=True)
                if q.returncode < 0 or q.returncode > 127:
                    raise RuntimeError(q.stderr)
                dst.write_text(resolve_js(q.stdout, rel, branch))
            record(dst, [ancestor/rel, other/rel], 'Three-way actual-JS merge over T7/T6 base; preserve all reviewed inputs')


def install_pi05_kernel():
    source = Path('/mnt/disk_4/geyi/pi05_744_30k_c3r_eval1540_20261104/c3r_pi05_8gpu')
    for p in (source/'source').rglob('*'):
        if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts or p.suffix not in ['.py', '.json', '.txt']:
            continue
        dst = B/'freeze/f28d/source'/p.relative_to(source/'source')
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        record(dst, [p], 'Use actual full C3r/pi05 E3 kernel, not Raw History ablation')
    dst = B/'freeze/study/compat_source/run.py'
    shutil.copy2(source/'compat_run.py', dst)
    record(dst, [source/'compat_run.py'], 'Actual pi05 runner: current 224 views, E3 templates, predict10 execute3')


def main():
    merge_python_authority()
    merge_voice()
    install_pi05_kernel()
    (W/'reports/MERGED_DEFINITIONS.json').write_text(json.dumps(RECORDS, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(merged_entries=len(RECORDS), runtime_started=False)))


if __name__ == '__main__':
    main()
