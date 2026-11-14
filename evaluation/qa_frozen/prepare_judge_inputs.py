"""Create anonymous fixed-T6 packets from method-neutral collected evidence.

The input can contain audit-only expected prose; it is NEVER copied. Only the
fields explicitly constructed below enter the judge request. This adapter
requires actual answer-model images and independent simulator audit facts.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, data): Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def safe_facts(data):
    return {key: data.get(key) for key in ['time', 'simulation_time', 'mode', 'held',
        'objects', 'drawers', 'relations', 'articulation', 'extra']}


def output_facts(data):
    return {key: data.get(key) for key in ['time', 'mode', 'held', 'objects',
        'drawers', 'relations', 'articulation']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--image-cache-root', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    evidence = read(args.evidence)
    controls = {row['case_id']: row for row in read(args.control)}
    fixture = read(args.fixture)
    bddl = Path(fixture['assets']['bddl_file']['path'])
    if sha(bddl) != fixture['assets']['bddl_file']['sha256']:
        raise ValueError('scene_inventory_asset_hash_mismatch')
    objects = bddl.read_text().split('(:objects', 1)[1].split(')', 1)[0]
    mapping = {'akita_black_bowl': 'bowl', 'cream_cheese': 'cheese',
        'wine_bottle': 'wine_bottle', 'plate': 'plate', 'tennis_ball': 'tennis_ball'}
    inventory = {name: [] for name in mapping.values()}
    for instance, kind in re.findall(r'(\w+)\s+-\s+(\w+)', objects):
        if kind in mapping: inventory[mapping[kind]].append(instance)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'packets').mkdir()
    rows = []
    for row in evidence:
        # IDs must not collide across reconnects. Legacy collectors without
        # epoch on speech facts are accepted only for a single observed epoch.
        outputs = row['outputs']
        epochs = {out['epoch'] for out in outputs}
        if len(epochs) > 1 and any('epoch' not in f for f in row['speech_frames']):
            raise ValueError('legacy_speech_facts_ambiguous_after_reconnect')
        keys = [(o['epoch'], o['output_id']) for o in outputs]
        if len(set(keys)) != len(keys): raise ValueError('duplicate_spoken_output_identity')
        facts = {(f.get('epoch', next(iter(epochs), None)), f['output_id']): f['facts'] for f in row['speech_frames']}
        frames = []
        for frame in row['frames']:
            image = args.image_cache_root / f"{row['index']:02d}.jpg" if args.image_cache_root else Path(frame['image'])
            if sha(image) != frame['sha256']: raise ValueError('actual_QA_input_image_hash_mismatch')
            offset = frame['facts']['offset_seconds']
            if abs(offset) > .1: raise ValueError('reference_alignment_exceeds_registered_100ms')
            frames.append(dict(local_image=str(image), sha256=frame['sha256'],
                request_time=frame['first_request_time'], reference_facts=safe_facts(frame['facts']),
                reference_time_offset_seconds=offset))
        spoken = []
        for output in outputs:
            receipt = output.get('audibility_evidence', {}).get('receipt_key')
            channel = json.loads(receipt)[-1] if receipt else 'legacy_bound_audio'
            spoken.append(dict(output_id=output['output_id'], epoch=output['epoch'], text=output['text'],
                bound_message_channel=channel,
                reference_facts_at_own_spoken_time=output_facts(facts[(output['epoch'], output['output_id'])])))
        packet = dict(original_question=row['question'],
            actual_ASR=[x.get('text', x.get('payload', {}).get('text', '')) for x in row['actual_user_transcripts']],
            spoken_outputs=spoken, current_QA_images=frames,
            reference_at_question_end=safe_facts(row['facts_at_audio_end']),
            reference_facts_at_visual_request=frames[-1]['reference_facts'] if frames else None,
            readonly_task=dict(instruction=row['gate_instruction'], state=row['gate_state']),
            physical_instance_inventory=inventory, inventory_source_sha256=sha(bddl),
            evidence_scope='Current MAIN/WRIST with labeled historical identity panels; independent reference facts for offline grading only',
            reference_alignment_rule='visual claims at QA input time; later asynchronous notices at their own spoken timestamps; never use a later state to correct earlier visual content')
        raw = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        packet_id = hashlib.sha256(raw).hexdigest()[:24]
        file = args.out / 'packets' / (packet_id + '.json')
        file.write_bytes(raw)
        rows.append(dict(case_id=row['case_id'], packet_id=packet_id, packet=str(file),
            packet_sha256=sha(file), delivery_outputs=outputs, control=controls[row['case_id']]))
    if len({r['case_id'] for r in rows}) != len(rows): raise ValueError('duplicate_cases_in_cohort')
    save(args.out / 'SCORING_INDEX.private.json', dict(schema='T6-fixed-judge-scoring-index-v1', cases=rows))
    save(args.out / 'INPUT_PROVENANCE.json', dict(cases=len(rows),
        source_sha256={str(p): sha(p) for p in [args.evidence, args.control, args.fixture, Path(__file__)]},
        expected_answer_prose_and_previous_labels_excluded=True,
        reference_alignment_tolerance_seconds=.1,
        nearest_tick_alignment_not_claimed_strict_past_only=True))
    print(json.dumps(dict(cases=len(rows), with_current_image=sum(bool(read(r['packet'])['current_QA_images']) for r in rows))))


if __name__ == '__main__': main()
