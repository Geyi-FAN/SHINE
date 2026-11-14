"""Audit retained first attempts; network probes replay only unscored preflight inputs."""
import collections
import concurrent.futures
import hashlib
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

R = Path(__file__).resolve().parent
Q = R.parents[1]
RUN = Q / 'runs/formal1770_v1'
sys.path.insert(0, str(Q / 'tools'))
import coordinator as frozen

def read(p):
    return json.loads(p.read_text())

def save(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')

def audit():
    frozen.verify()
    rows = [read(p) for p in (RUN / 'outcomes').glob('*.json')]
    uids = {x['trial_uid'] for x in rows}
    assert len(uids) == len(rows) == 256
    assert {p.name for p in (RUN / 'cases').iterdir()} == uids
    expected = {'B1:T2:T2COL1_NS_G01:R02', 'B1:T2:T2COL1_NS_G01:R03',
                'B1:T1:T1COL1_CL_G05_I02:R03', 'B1:T8:T8EN4_CL_N06_I02:R02'}
    errors = [x for x in rows if frozen.defect(x)]
    assert {x['trial_uid'] for x in errors} == expected
    assert all(any(text in x['final_status']['last_error'] for text in
               ['cloud01 HTTP 500', 'Temporary failure in name resolution', 'read operation timed out'])
               for x in errors)
    value = dict(completed=256, planned=1770, unstarted=1514,
                 known_infrastructure_trials=sorted(expected),
                 infrastructure_errors=[dict(trial_uid=x['trial_uid'], error=x['final_status']['last_error']) for x in errors],
                 by_method=dict(collections.Counter(x['method'] for x in rows)),
                 partial_started=[], source_freeze_sha256=hashlib.sha256((Q / 'plans/FROZEN.json').read_bytes()).hexdigest(),
                 registered_sha256=hashlib.sha256((RUN / 'REGISTERED.json').read_bytes()).hexdigest(), at=time.time())
    save(R / 'INCIDENT_AUDIT.json', value)
    save(R / 'RETAINED256_SHA.json', {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (RUN / 'outcomes').glob('*.json')})

def dns_probe(host):
    start = time.monotonic()
    try:
        ips = sorted({x[4][0] for x in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
        return dict(host=host, passed=bool(ips), ips=ips, elapsed_s=time.monotonic() - start)
    except Exception as e:
        return dict(host=host, passed=False, error=repr(e), elapsed_s=time.monotonic() - start)

def api_probe(path):
    body = read(path)
    cfg = read(Q / 'actors/B1/config/MODELS.json')['agent']
    assert body['model'] == cfg['model'] and body['max_tokens'] == cfg['max_tokens']
    key = (Q / 'actors/B1/private/agent.key').read_text().strip()
    request = urllib.request.Request(cfg['endpoint'], data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    result = dict(unscored_preflight_input=str(path), request_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  model=cfg['model'], max_tokens=body['max_tokens'], registered_trial=False,
                  formal_case_replayed=False, requests=1, started=time.time())
    start = time.monotonic()
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=120) as f:
            response = json.load(f)
            result.update(http_status=f.status, actual_model=response.get('model'))
        answer = json.loads(response['choices'][0]['message']['content'])
        result.update(passed=response.get('model') == cfg['model'] and isinstance(answer, dict),
                      finish_reason=response['choices'][0].get('finish_reason'), usage=response.get('usage'),
                      response_keys=sorted(answer))
    except urllib.error.HTTPError as e:
        result.update(passed=False, http_status=e.code, detail=e.read().decode(errors='replace').replace(key, '[REDACTED]')[:1000])
    except Exception as e:
        result.update(passed=False, error=type(e).__name__, detail=str(e).replace(key, '[REDACTED]')[:1000])
    result['elapsed_s'] = time.monotonic() - start
    return result

if __name__ == '__main__':
    audit()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        dns = list(pool.map(dns_probe, ['llmapi.paratera.com', 'dashscope.aliyuncs.com'] * 16))
    save(R / 'DNS_AFTER32.json', dict(probes=dns, passed=all(x['passed'] for x in dns)))
    assert all(x['passed'] for x in dns), 'DNS admission failed'
    inputs = []
    for case in sorted((Q / 'runs/preflight15_r7/cases').iterdir()):
        paths = sorted((case / 'agent_calls').glob('*/request.json'))
        if paths:
            inputs.append(paths[0])
        if len(inputs) == 4:
            break
    assert len(inputs) == 4
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        probes = list(pool.map(api_probe, inputs))
    value = dict(passed=all(x['passed'] for x in probes), probes=probes, max_concurrent=4,
                 source='same frozen model/settings; four distinct unscored preflight inputs',
                 no_formal_cases_replayed=True, at=time.time())
    save(R / 'API_HEALTH.json', value)
    print(json.dumps(dict(dns_passed=sum(x['passed'] for x in dns), dns_planned=32, **value)), flush=True)
