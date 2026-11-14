"""C3r original verifier/recovery through the credential04-only proxy; lossless original image atlases."""
import base64
import copy
import hashlib
import io
import json
import math
import os
import shlex
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def settings():
    return json.loads(Path(os.environ.get('R34_LOCAL_ROLES', ROOT / 'local_roles.json')).read_text())


def connection(role):
    # Bound aliases also resolve through the one frozen primary configuration.
    from unified.transport import connection as registered
    return registered(role)


def image_bytes(item):
    url = item['image_url']['url']
    if not url.startswith('data:image/') or ';base64,' not in url:
        raise ValueError('Replay only accepts embedded local images')
    return base64.b64decode(url.split(';base64,', 1)[1], validate=True)


def pack_messages(messages):
    """Keep all original text. Put decoded original pixels into labelled PNG sheets."""
    result = copy.deepcopy(messages)
    audit = []
    for message in result:
        content = message.get('content')
        if not isinstance(content, list):
            continue
        originals = []
        last_text = ''
        for item in content:
            if item.get('type') == 'text':
                last_text = item['text']
            elif item.get('type') == 'image_url':
                data = image_bytes(item)
                im = Image.open(io.BytesIO(data)).convert('RGB')
                originals.append((last_text, data, im))
        if len(originals) <= 2:
            audit.extend(dict(source_image_sha256=hashlib.sha256(data).hexdigest(), original_size=list(im.size), packed=False) for _, data, im in originals)
            continue
        if len(originals) > 6:
            raise ValueError('R34 atlas supports at most six original images; no truncation')
        n_sheets = math.ceil(len(originals) / 3)
        per_sheet = math.ceil(len(originals) / n_sheets)
        bands = 32
        sheets = []
        mappings = []
        for sheet_index in range(n_sheets):
            group = originals[sheet_index * per_sheet:(sheet_index + 1) * per_sheet]
            width = max(im.width for _, _, im in group)
            height = sum(im.height + bands for _, _, im in group)
            if width * height > 1048576:
                raise ValueError('Atlas exceeds deployed pixel cap; refusing silent resize')
            sheet = Image.new('RGB', (width, height), (235, 235, 235))
            draw = ImageDraw.Draw(sheet)
            y = 0
            for panel, (label, data, im) in enumerate(group):
                original_index = sheet_index * per_sheet + panel
                caption = 'Image %d | %s' % (original_index + 1, label)
                draw.text((4, y + 8), caption, fill=(0, 0, 0))
                sheet.paste(im, (0, y + bands))
                # Verify exact RGB pixels after placement, before encoding losslessly.
                assert sheet.crop((0, y + bands, im.width, y + bands + im.height)).tobytes() == im.tobytes()
                info = dict(original_index=original_index + 1, source_image_sha256=hashlib.sha256(data).hexdigest(),
                            original_size=list(im.size), label=label, sheet=sheet_index + 1, panel=panel + 1,
                            pixel_box=[0, y + bands, im.width, y + bands + im.height], packed=True)
                mappings.append(info)
                audit.append(info)
                y += im.height + bands
            buffer = io.BytesIO()
            sheet.save(buffer, format='PNG')
            encoded = buffer.getvalue()
            # The written PNG, rather than only the in-memory canvas, is checked too.
            reopened = Image.open(io.BytesIO(encoded)).convert('RGB')
            assert reopened.tobytes() == sheet.tobytes()
            sheets.append(dict(type='image_url', image_url=dict(url='data:image/png;base64,' + base64.b64encode(encoded).decode())))
        new_content = []
        image_index = 0
        for item in content:
            if item.get('type') != 'image_url':
                new_content.append(item)
            else:
                m = mappings[image_index]
                new_content.append(dict(type='text', text='Image %d appears in sheet %d, panel %d from top; image coordinates refer to the ORIGINAL MAIN view, not the atlas canvas.' % (m['original_index'], m['sheet'], m['panel'])))
                image_index += 1
        new_content.append(dict(type='text', text='The following sheets contain all the preceding observations in order. Each panel retains its original pixels and labelled frame/view; bands are labels, not scene evidence.'))
        new_content.extend(sheets)
        message['content'] = new_content
    return result, audit


def wire_body(body, role):
    cfg, _ = connection(role)
    from observation_features import augment
    output = augment(body, role)
    from output_contract import constrain
    output = constrain(output, role)
    output['model'] = cfg['model']
    thinking = output.pop('enable_thinking', False)
    output['chat_template_kwargs'] = dict(enable_thinking=thinking)
    output['messages'], atlas = pack_messages(output['messages'])
    return output, atlas


def send_body(body, role, folder, timeout=300):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    cfg, key = connection(role)
    wire, atlas = wire_body(body, role)
    (folder / 'request_original.json').write_text(json.dumps(body, ensure_ascii=False))
    (folder / 'request_wire.json').write_text(json.dumps(wire, ensure_ascii=False))
    (folder / 'atlas.json').write_text(json.dumps(atlas, ensure_ascii=False, indent=2))
    record = dict(role=role, api_url=cfg['chat_url'], model=cfg['model'], request_sha256=digest(wire),
                  original_messages_sha256=digest(body['messages']), started_unix=time.time(),
                  target_provider='paratera', credential_no='04', local_proxy_requests=1, actual_cloud_dispatch='see dedicated gateway journal', transport_retries=0)
    start = time.monotonic()
    try:
        # Ignore HTTP(S)_PROXY for same-server traffic; never redirect to another host.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(cfg['chat_url'], data=json.dumps(wire).encode(),
                                         headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'X-Agent-Role': role, 'X-Eval-Request-ID': folder.name, 'X-Eval-Case-ID': Path(os.environ['R34_LOCAL_REQUEST_LOG']).parent.name, 'X-Eval-Run-ID': os.environ.get('C3R_EVAL_RUN_ID', 'cloud04_preflight')})
        with opener.open(request, timeout=timeout) as response:
            raw = json.load(response)
            record.update(proxy_upstream=response.headers.get('X-Local-Upstream-Id'), proxy_request_id=response.headers.get('X-Local-Pool-Request-Id'), proxy_queue_seconds=response.headers.get('X-Local-Queue-Seconds'), proxy_inference_seconds=response.headers.get('X-Local-Inference-Seconds'), transport_retries=int(response.headers.get('X-Local-Transport-Retries','0')), transport_epoch=response.headers.get('X-Local-Transport-Epoch'))
        (folder / 'response.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2))
        record.update(status='response_received', actual_model=raw.get('model'), usage=raw.get('usage'))
        return raw
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors='replace')
        record.update(status='http_error', http_status=exc.code, detail=detail[:3000], proxy_request_id=exc.headers.get('X-Local-Pool-Request-Id'), transport_retries=int(exc.headers.get('X-Local-Transport-Retries','0')))
        raise RuntimeError('Local model HTTP %s: %s' % (exc.code, detail[:1000])) from None
    except Exception as exc:
        record.update(status='transport_error', error_type=type(exc).__name__, detail=str(exc))
        raise
    finally:
        record['seconds'] = time.monotonic() - start
        (folder / 'transport.json').write_text(json.dumps(record, ensure_ascii=False, indent=2))


def _runtime_request(request, role, timeout):
    root = Path(os.environ['R34_LOCAL_REQUEST_LOG']) / role
    root.mkdir(parents=True, exist_ok=True)
    import uuid
    folder = root / (str(time.time_ns()) + '_' + uuid.uuid4().hex[:8])
    return send_body(json.loads(request.data), role, folder, timeout=max(timeout, 600))


def verifier_request_json(request, timeout=300):
    return _runtime_request(request, 'verifier', timeout)


def recovery_request_json(request, timeout=300):
    return _runtime_request(request, 'recovery', timeout)
