"""Materialize one shared voice profile; never use benchmark answer text."""
import hashlib
import base64
import json
from pathlib import Path
import shutil


def activate(root, output):
    root, output = Path(root), Path(output)
    profile = json.loads((root / 'config/voice_profile.json').read_text())
    prompt = root / profile['instruction_prompt']
    seed = root / profile['receipt_seed']
    if not prompt.is_file() or not list(seed.glob('*.json')):
        raise ValueError('Voice profile prompt or receipt seed is missing')
    verified_texts = set()
    for asset in seed.glob('*.json'):
        row = json.loads(asset.read_text())
        audio = base64.b64decode(row.get('pcm16', ''), validate=True)
        if (row.get('schema') == 1 and row.get('sampleRate') == 24000
                and audio and len(audio) % 2 == 0
                and hashlib.sha256(audio).hexdigest() == row.get('sha256')):
            verified_texts.add(row.get('transcript'))
    missing = set(profile.get('required_receipt_texts', [])) - verified_texts
    if missing:
        raise ValueError('Required verified receipt audio missing: ' + repr(sorted(missing)))
    output.mkdir(parents=True, exist_ok=True)
    cache = output / 'receipt_audio'
    if cache.exists():
        raise FileExistsError('Do not reuse another session receipt cache')
    shutil.copytree(seed, cache)
    env = dict(profile['flags'])
    env.update(ROBOT_INSTRUCTION_PROMPT_FILE=str(prompt),
               ROBOT_RECEIPT_AUDIO_DIR=str(cache),
               ROBOT_AUDIO_RECEIVE_LOG=str(output / 'audio_received.jsonl'),
               VOICE_AUDIO_FRAME_LOG=str(output / 'audio_received.jsonl'))
    identity = dict(profile=profile, activated_environment=env,
                    prompt_sha256=hashlib.sha256(prompt.read_bytes()).hexdigest(),
                    receipt_seed_hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in sorted(seed.glob('*.json'))},
                    asr_reference_text_sent=False, asr_scene_sent=False)
    (output / 'VOICE_PROFILE.json').write_text(json.dumps(identity, indent=2)+'\n')
    return env
