"""Single authoritative numerical configuration; SI units and control-step windows."""
import hashlib
import json
import math
from pathlib import Path
DEFAULT = Path(__file__).parent / 'configs' / 'v2.5.0-candidate.json'

def load_rules(path=None):
    rules = json.loads(Path(path or DEFAULT).read_text())
    if rules.get('schema_version') != 1:
        raise ValueError('Unsupported metric configuration schema')
    validate(rules)
    return rules

def validate(rules):
    def walk(value, name='config'):
        if isinstance(value, dict):
            for key, item in value.items(): walk(item, name + '.' + key)
        elif isinstance(value, list):
            for item in value: walk(item, name)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value) or value < 0: raise ValueError(name + ': invalid number')
            if name.endswith('_steps') or name.endswith('_min_true') or name.endswith('control_hz'):
                if type(value) is not int or value < 1: raise ValueError(name + ': positive integer required')
    walk(rules)
    r = rules['restore']
    if r['support_min_true'] > r['support_steps']: raise ValueError('Invalid support vote')
    for key in ['preserve_position', 'preserve_joint']:
        if rules[key]['severe_m'] < rules[key]['tolerance_m']: raise ValueError('Severe threshold below tolerance')
    if rules['reopen_diagnostic']['gap_m'] < rules['close']['gap_m']:
        raise ValueError('Reopen threshold conflicts with close tolerance')
    for spec in rules['target_regions'].values():
        if len(spec['margin_m']) != 3 or spec['margin_m'][2] != 0:
            raise ValueError('Region expansion must preserve native Z bounds')

def fingerprint(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()
