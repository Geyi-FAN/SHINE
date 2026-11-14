"""Keep four role payloads unchanged; use one explicitly configured local pool."""
import json
import os
from pathlib import Path
import shlex
import urllib.parse
import urllib.request

W = Path(__file__).resolve().parents[2]
_installed = False


def connection(role):
    c = json.loads((W/'config/roles.json').read_text())
    if role not in {'wording', 'planning', 'verifier', 'recovery'}:
        raise ValueError('Unknown C3r role')
    base = c['api_base_url'].rstrip('/')
    parsed = urllib.parse.urlparse(base)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1'
            or parsed.path != '/v1' or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError('Only the explicitly configured local shared pool is allowed')
    file = os.environ.get('HARNESS_AGENT_KEY_FILE')
    if file:
        key = Path(file).read_text().strip()
    else:
        envfile = Path(os.environ.get('HARNESS_AGENT_ENV_FILE', c['service_env_file']))
        values = {}
        for line in envfile.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                name, value = line.split('=', 1)
                if name.strip() == 'VLLM_API_KEY':
                    words = shlex.split(value, comments=True)
                    values[name.strip()] = words[0] if words else ''
        key = values.get('VLLM_API_KEY', '')
    if not key:
        raise ValueError('Provide a private local-model credential file at launch')
    return {'model': c['model'], 'chat_url': base+'/chat/completions'}, key


def install_network_guard():
    if getattr(urllib.request.OpenerDirector.open, '_unified_local_guard', False):
        return
    original = urllib.request.OpenerDirector.open
    c = json.loads((W/'config/roles.json').read_text())
    pool = urllib.parse.urlparse(c['api_base_url'])
    ports = {pool.port, int(os.environ['HYBRID_POLICY_PORT'])}
    def guarded(opener, request, *args, **kwargs):
        url = request.full_url if hasattr(request, 'full_url') else str(request)
        target = urllib.parse.urlparse(url)
        if target.scheme in ('http', 'https'):
            if target.scheme != 'http' or target.hostname not in ('127.0.0.1', 'localhost') or target.port not in ports:
                raise RuntimeError('Unregistered local endpoint; no cloud or legacy model fallback')
        return original(opener, request, *args, **kwargs)
    guarded._unified_local_guard = True
    urllib.request.OpenerDirector.open = guarded


def install():
    global _installed
    if _installed:
        return
    import local_transport, text_transport
    local_transport.connection = connection
    text_transport.connection = connection
    text_transport.install_network_guard = install_network_guard
    _installed = True
