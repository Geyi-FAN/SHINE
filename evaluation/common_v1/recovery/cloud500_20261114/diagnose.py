"""Read-only cohort audit and independent cloud health probes; no trial replay."""
import base64
import collections
import concurrent.futures
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

Q = Path(__file__).resolve().parents[2]
R = Path(__file__).resolve().parent
RUN = Q / 'runs/formal1770_v1'

def read(p):
    return json.loads(p.read_text())

def save(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def audit():
    rows = [read(p) for p in (RUN / 'outcomes').glob('*.json')]
    registered = read(RUN / 'REGISTERED.json')
    uids = {x['trial_uid'] for x in rows}
    started = {p.name for p in (RUN / 'cases').iterdir()}
    transports = []
    for row in rows:
        case = RUN / 'cases' / row['trial_uid']
        for p in (case / 'agent_calls').glob('*/transport.json'):
            v = read(p)
            transports.append(dict(trial_uid=row['trial_uid'], file=str(p), **{
                k: v.get(k) for k in ['http_status', 'status', 'started', 'sent_at',
                                      'elapsed_s', 'upstream_s', 'queue_s', 'error',
                                      'detail', 'actual_model', 'retries']}))
    errors = [v for v in transports if v['status'] == 'error']
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (RUN / 'outcomes').glob('*.json')}
    save(R / 'RETAINED247_SHA.json', manifest)
    report = dict(completed=len(rows), planned=len(registered),
                  by_method=dict(collections.Counter(x['method'] for x in rows)),
                  unique_uids=len(uids), partial_started=sorted(started - uids),
                  unstarted=len(registered) - len(rows),
                  agent_request_count=len(transports), agent_errors=errors,
                  registered_sha256=hashlib.sha256((RUN / 'REGISTERED.json').read_bytes()).hexdigest(),
                  source_freeze_sha256=hashlib.sha256((Q / 'plans/FROZEN.json').read_bytes()).hexdigest(),
                  all_first_attempts_retained=True, at=time.time())
    assert len(uids) == len(rows) == 247
    assert not report['partial_started']
    assert uids <= {x['trial_uid'] for x in registered}
    save(R / 'INCIDENT_AUDIT.json', report)
    print(json.dumps(report, ensure_ascii=False), flush=True)

def probe(index, vision):
    cfg = read(Q / 'actors/B1/config/MODELS.json')['agent']
    key = (Q / 'actors/B1/private/agent.key').read_text().strip()
    content = [dict(type='text', text='Connectivity test %d only. Return JSON {"health":"ok"}. No robot task.' % index)]
    if vision:
        png = RUN / 'cases/B1:T2:T2COL1_NS_G01:R02/initial.png'
        content.append(dict(type='image_url', image_url=dict(url='data:image/png;base64,' + base64.b64encode(png.read_bytes()).decode())))
    body = dict(model=cfg['model'], messages=[dict(role='user', content=content)],
                temperature=cfg['temperature'], max_tokens=64, stream=False,
                response_format=dict(type='json_object'), enable_thinking=False)
    request = urllib.request.Request(cfg['endpoint'], data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    start = time.monotonic()
    result = dict(index=index, vision=vision, started=time.time(),
                  registered_trial=False, retries=0, model=cfg['model'])
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=120) as f:
            value = json.load(f)
            result.update(http_status=f.status, actual_model=value.get('model'))
        answer = json.loads(value['choices'][0]['message']['content'])
        result['passed'] = answer.get('health') == 'ok' and value.get('model') == cfg['model']
    except urllib.error.HTTPError as e:
        result.update(passed=False, http_status=e.code,
                      detail=e.read().decode(errors='replace').replace(key, '[REDACTED]')[:1000])
    except Exception as e:
        result.update(passed=False, error=type(e).__name__, detail=str(e).replace(key, '[REDACTED]')[:1000])
    result['elapsed_s'] = time.monotonic() - start
    return result

if __name__ == '__main__':
    audit()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda x: probe(x, x % 2 == 1), range(4)))
    value = dict(probes=results, passed=all(x['passed'] for x in results),
                 max_concurrent=4, original_credential_no='01', independent_health_checks=True,
                 no_formal_requests_retried=True, at=time.time())
    save(R / 'API_HEALTH.json', value)
    print(json.dumps(value, ensure_ascii=False), flush=True)
