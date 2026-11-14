"""C3r original wording/planning through the credential04-only hosted proxy."""
import copy
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def connection(role):
    # Bound aliases also resolve through the one frozen primary configuration.
    from unified.transport import connection as registered
    return registered(role)


def classify(body):
    system = body.get('messages', [{}])[0].get('content', '')
    if not isinstance(system, str):
        raise ValueError('Expected original text system prompt')
    if system.startswith("Rewrite the user's robot request"):
        return 'wording'
    if 'GENERIC OPERATORS:' in system:
        return 'planning'
    raise ValueError('This adapter only accepts original planning/wording roles')


def request_json(request, timeout=90):
    original = json.loads(request.data)
    role = classify(original)
    cfg, key = connection(role)
    body = copy.deepcopy(original)
    body['model'] = cfg['model']
    thinking = body.pop('enable_thinking', False)
    body['chat_template_kwargs'] = dict(enable_thinking=thinking)
    assert body['messages'] == original['messages'], 'No prompt compression or rewriting in transport'
    root = Path(os.environ['R34_LOCAL_REQUEST_LOG']) / role
    folder = root / (str(time.time_ns()) + '_' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    for name, data in [('request_original.json', original), ('request_wire.json', body)]:
        (folder / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    transport = dict(role=role, api_url=cfg['chat_url'], model=cfg['model'],
                     started_unix=time.time(), target_provider='paratera', credential_no='04', local_proxy_requests=1, actual_cloud_dispatch='see dedicated gateway journal', transport_retries=0,
                     messages_unchanged=True, cached_answer=False,
                     request_sha256=hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest())
    start = time.monotonic()
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        local_request = urllib.request.Request(cfg['chat_url'], data=json.dumps(body).encode(),
                                              headers={'Authorization': 'Bearer ' + key,
                                                       'Content-Type': 'application/json', 'X-Agent-Role': role, 'X-Eval-Request-ID': folder.name, 'X-Eval-Case-ID': Path(os.environ['R34_LOCAL_REQUEST_LOG']).parent.name, 'X-Eval-Run-ID': os.environ.get('C3R_EVAL_RUN_ID', 'cloud04_preflight')})
        with opener.open(local_request, timeout=max(timeout, 600)) as response:
            raw = json.load(response)
            transport.update(proxy_upstream=response.headers.get('X-Local-Upstream-Id'), proxy_request_id=response.headers.get('X-Local-Pool-Request-Id'), proxy_queue_seconds=response.headers.get('X-Local-Queue-Seconds'), proxy_inference_seconds=response.headers.get('X-Local-Inference-Seconds'), transport_retries=int(response.headers.get('X-Local-Transport-Retries','0')), transport_epoch=response.headers.get('X-Local-Transport-Epoch'))
        (folder / 'response.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2))
        transport.update(status='response_received', actual_model=raw.get('model'), usage=raw.get('usage'),
                         finish_reason=raw['choices'][0].get('finish_reason'))
        return raw
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors='replace')
        transport.update(status='HTTP_error', http_status=error.code, detail=detail[:3000], proxy_request_id=error.headers.get('X-Local-Pool-Request-Id'), transport_retries=int(error.headers.get('X-Local-Transport-Retries','0')))
        raise RuntimeError('Local ' + role + ' HTTP ' + str(error.code) + '; no cloud fallback') from None
    except Exception as error:
        transport.update(status='transport_or_parse_error', error_type=type(error).__name__)
        raise
    finally:
        transport['seconds'] = time.monotonic() - start
        (folder / 'transport.json').write_text(json.dumps(transport, ensure_ascii=False, indent=2))


def install_network_guard():
    """All urllib traffic in this worker is restricted to named local services."""
    original = urllib.request.OpenerDirector.open
    allowed = {('127.0.0.1', 18684), ('127.0.0.1', 19865), ('127.0.0.1', 19866), ('localhost', 19865), ('localhost', 19866)}

    def guarded(opener, request, *args, **kwargs):
        url = request.full_url if hasattr(request, 'full_url') else str(request)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in ('http', 'https') and (parsed.scheme != 'http' or (parsed.hostname, parsed.port) not in allowed):
            raise RuntimeError('Nonlocal API forbidden in all-local worker')
        return original(opener, request, *args, **kwargs)

    urllib.request.OpenerDirector.open = guarded
