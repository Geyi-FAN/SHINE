"""Independent admission probes. Never regenerate a registered trial's answer."""
import concurrent.futures
import hashlib
import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

R = Path(__file__).resolve().parent
Q = R.parents[1]

def probe(path):
    body = json.loads(path.read_text())
    cfg = json.loads((Q / 'actors/B1/config/MODELS.json').read_text())['agent']
    assert body['model'] == cfg['model'] and body['max_tokens'] == cfg['max_tokens']
    key = (Q / 'actors/B1/private/agent.key').read_text().strip()
    result = dict(preflight_input=str(path), input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  formal_trial=False, requests=1, started=time.time())
    start = time.monotonic()
    try:
        request = urllib.request.Request(cfg['endpoint'], data=json.dumps(body).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=120) as f:
            value = json.load(f)
            result.update(http_status=f.status, actual_model=value.get('model'))
        answer = json.loads(value['choices'][0]['message']['content'])
        result['passed'] = value.get('model') == cfg['model'] and isinstance(answer, dict)
        result['fatal'] = value.get('model') != cfg['model']
    except urllib.error.HTTPError as e:
        result.update(passed=False, fatal=e.code in [401, 403], http_status=e.code,
                      detail=e.read().decode(errors='replace').replace(key, '[REDACTED]')[:1000])
    except Exception as e:
        result.update(passed=False, fatal=False, error=type(e).__name__, detail=str(e).replace(key, '[REDACTED]')[:1000])
    result['elapsed_s'] = time.monotonic() - start
    return result

def check():
    dns = []
    for host in ['llmapi.paratera.com', 'dashscope.aliyuncs.com']:
        try:
            ips = sorted({v[4][0] for v in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
            dns.append(dict(host=host, passed=bool(ips), addresses=ips))
        except OSError as e:
            dns.append(dict(host=host, passed=False, error=repr(e)))
    if not all(x['passed'] for x in dns):
        return dict(passed=False, fatal=False, dns=dns, at=time.time())
    inputs = []
    for branch in ['T1', 'T5', 'T6', 'T7']:
        cases = sorted(p for p in (Q / 'runs/preflight15_r7/cases').iterdir() if ':' + branch + ':' in p.name)
        paths = [p for case in cases for p in sorted((case / 'agent_calls').glob('*/request.json'))]
        assert paths, 'No original engineering input for ' + branch
        inputs.append(paths[0])
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        probes = list(pool.map(probe, inputs))
    return dict(passed=all(x['passed'] for x in probes), fatal=any(x.get('fatal') for x in probes),
                dns=dns, probes=probes, max_concurrent=4, no_formal_trial_retries=True, at=time.time())
