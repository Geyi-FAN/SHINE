"""Method-independent entry point for the frozen T6 hybrid judge.

The index holds private scoring metadata; only allowlisted anonymous packets
are sent to GLM. Replay mode tests the scorer using archived judgments; it is
never a new semantic API evaluation. No outcome-based retry is implemented.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'v3'))
spec = importlib.util.spec_from_file_location('fixed_t6_engine', ROOT / 'v3/run_judge.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
import client
sys.path.insert(0, str(ROOT))
from reference_guards import check

PACKET_FIELDS = {
    'actual_ASR', 'current_QA_images', 'evidence_scope',
    'inventory_source_sha256', 'original_question', 'physical_instance_inventory',
    'readonly_task', 'reference_alignment_rule', 'reference_at_question_end',
    'reference_facts_at_visual_request', 'spoken_outputs',
}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def validate_packet(packet, delivery):
    if set(packet) != PACKET_FIELDS:
        raise ValueError('packet_fields_do_not_match_frozen_allowlist')
    if not isinstance(packet['original_question'], str) or not packet['original_question'].strip():
        raise ValueError('original_question_required')
    keys = [(o['output_id'], o['epoch']) for o in packet['spoken_outputs']]
    delivery_keys = [(o['output_id'], o['epoch']) for o in delivery]
    if len(keys) != len(set(keys)) or set(keys) != set(delivery_keys) or len(delivery_keys) != len(set(delivery_keys)):
        raise ValueError('output_identity_or_epoch_mismatch')
    if any(o.get('epoch') is None for o in delivery):
        raise ValueError('epoch_required')
    for frame in packet['current_QA_images']:
        if sha(frame['local_image']) != frame['sha256']:
            raise ValueError('image_hash_changed')
    return packet


def validate_registration(indexed, registry, diagnostic_subset=False):
    expected = {row['case_id'] for row in registry['cases']}
    actual = [row['case_id'] for row in indexed]
    if len(expected) != registry['planned'] or len(actual) != len(set(actual)):
        raise ValueError('registered_case_or_input_identity_duplicate')
    if set(actual) - expected or (not diagnostic_subset and set(actual) != expected):
        raise ValueError('index_does_not_match_frozen_registered_case_set')
    return dict(registered_planned=registry['planned'], indexed=len(actual),
        diagnostic_subset=diagnostic_subset, full_registered_cohort=set(actual) == expected)


def credential_reader(directory):
    def load():
        cfg = read(directory / 'agents.json')
        env = {}
        for line in (directory / '.env').read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
        agent = next(a for a in cfg['agents'] if a['agent_id'] == 'agent_04')
        return env[cfg['base_url_env']].rstrip('/'), env[agent['api_key_env']]
    return load


def score(packet, label, delivery, control):
    result = engine.qualify(label, delivery, control)
    guard = check(packet, label)
    result['reference_guard'] = guard
    if guard['status'] == 'fail':
        result.update(status='referent_failure', interaction='fail', qualified_QA='fail')
    elif guard['status'] == 'review_required':
        result.update(status='independent_review_required', interaction='unknown', qualified_QA='unknown')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--credential-dir', type=Path, default=Path('/mnt/disk_4/geyi/paratera_api'))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--replay-labels', type=Path, help='Scorer verification only; no new model calls')
    parser.add_argument('--diagnostic-subset', action='store_true',
        help='Explicitly permit a registered subset; never a full benchmark score')
    args = parser.parse_args()
    if args.dry_run and args.replay_labels:
        parser.error('dry-run and replay-labels are mutually exclusive')
    active = read(ROOT / 'ACTIVE_PROTOCOL.json')
    for relative, expected in active['source_sha256'].items():
        if sha(ROOT / relative) != expected:
            raise ValueError('frozen_judge_source_changed:' + relative)
    protocol = read(ROOT / 'fixed_v4/PROTOCOL.json')['underlying_model_protocol']
    indexed = read(args.index)['cases']
    if not indexed or len({x['packet_id'] for x in indexed}) != len(indexed):
        raise ValueError('nonempty_unique_packet_index_required')
    registration = validate_registration(indexed, read(ROOT / 'REGISTERED_CASES90.json'), args.diagnostic_subset)
    args.out.mkdir(parents=True, exist_ok=False)
    frozen = {str(p): sha(p) for p in [args.index, Path(__file__), ROOT / 'ACTIVE_PROTOCOL.json', ROOT / 'v3/run_judge.py', ROOT / 'FORMAT_REPAIR_PROMPT.txt']}
    # Lock every registered grading dependency across the whole cohort, not
    # only at startup. This packaging guard does not alter any verdict rule.
    frozen.update({str(ROOT / relative): expected
        for relative, expected in active['source_sha256'].items()})
    mode = 'dry_run' if args.dry_run else ('archived_label_replay' if args.replay_labels else 'live_model_judge')
    save(args.out / 'FROZEN_JUDGE.json', dict(version=active['version'], mode=mode,
        frozen_at=time.time(), source_sha256=frozen, planned=len(indexed),
        registration=registration, no_outcome_retry=True, independent_human_calibration_completed=False))
    client.credentials = credential_reader(args.credential_dir)
    rows = []
    for item in indexed:
        assert all(sha(p) == h for p, h in frozen.items()), 'frozen_inputs_changed'
        row = dict(case_id=item['case_id'], packet_id=item['packet_id'], interaction='unknown', qualified_QA='unknown')
        folder = args.out / item['packet_id']
        folder.mkdir()
        try:
            packet_path = Path(item['packet'])
            if sha(packet_path) != item['packet_sha256']:
                raise ValueError('packet_hash_changed')
            packet = validate_packet(read(packet_path), item['delivery_outputs'])
            if type(item['control']['no_qa_control_error']) is not bool:
                raise ValueError('independent_control_audit_boolean_required')
            if args.dry_run:
                row.update(status='inputs_validated', image_count=len(packet['current_QA_images']))
            else:
                if args.replay_labels:
                    label_path = args.replay_labels / item['packet_id'] / 'JUDGMENT.json'
                    label = engine.validate(read(label_path), packet['spoken_outputs'])
                    row['archived_label_sha256'] = sha(label_path)
                    row['format_repair_attempted'] = False
                else:
                    payload = engine.request(packet, protocol)
                    answer = client.call(payload, folder / 'primary', protocol['semantic_judge']['api_timeout_seconds'])
                    if answer.get('model') != protocol['semantic_judge']['model']:
                        raise ValueError('returned_model_mismatch')
                    row['format_repair_attempted'] = False
                    try:
                        label = engine.validate(client.parse_json(client.content(answer)), packet['spoken_outputs'])
                    except ValueError as error:
                        # Exactly one schema-only repair, including an invalid pass.
                        # A valid fail/insufficient verdict is never retried.
                        repaired = copy.deepcopy(payload)
                        repaired['messages'] += [dict(role='assistant', content=client.content(answer)),
                            dict(role='user', content=(ROOT / 'FORMAT_REPAIR_PROMPT.txt').read_text().replace('{error_code}', str(error)))]
                        row['format_repair_attempted'] = True
                        answer = client.call(repaired, folder / 'format_repair', protocol['semantic_judge']['api_timeout_seconds'])
                        if answer.get('model') != protocol['semantic_judge']['model']:
                            raise ValueError('returned_model_mismatch')
                        label = engine.validate(client.parse_json(client.content(answer)), packet['spoken_outputs'])
                save(folder / 'JUDGMENT.json', label)
                row.update(score(packet, label, item['delivery_outputs'], item['control']),
                    verdict=label['verdict'], reason=label['reason'], reason_code=label['reason_code'])
        except Exception as error:
            row.update(status='judge_or_input_error', error_type=type(error).__name__, reason=str(error)[:160])
        save(folder / 'SCORE.json', row)
        rows.append(row)
        result = dict(version=active['version'], mode=mode, planned=len(indexed), completed=len(rows),
            registration=registration,
            confirmed_pass=sum(r['interaction'] == 'pass' for r in rows),
            failed=sum(r['interaction'] == 'fail' for r in rows),
            unknown=sum(r['interaction'] == 'unknown' for r in rows),
            dry_run_validated=sum(r['status'] == 'inputs_validated' for r in rows), rows=rows,
            unknown_retained_in_planned_denominator=True, not_new_robot_rollouts=True)
        save(args.out / 'PROGRESS.json', result)
    save(args.out / 'SUMMARY.json', result)
    save(args.out / 'COMPLETED.json', dict(completed_at=time.time(), mode=mode, completed=len(rows), planned=len(indexed)))
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
