"""Branch-local planning affinity; preserve the Agent request and lifecycle."""
from urllib.parse import urlparse

ENDPOINT = 'http://127.0.0.1:18184/v1/chat/completions'


def install(module=None):
    if module is None:
        import text_transport as module
    original = module.connection
    if getattr(original, '_t02_planning_affinity', False):
        return

    def connection(role):
        # Retain the original model, private credential and endpoint checks.
        config, key = original(role)
        if role != 'planning':
            return config, key
        if config.get('chat_url') != 'http://127.0.0.1:18084/v1/chat/completions':
            raise ValueError('Unexpected parent planning transport')
        if config.get('model') != 'Qwen3.8-27B-FP8':
            raise ValueError('Planning model changed')
        parsed = urlparse(ENDPOINT)
        if (parsed.scheme, parsed.hostname, parsed.port, parsed.path) != (
            'http', '127.0.0.1', 18184, '/v1/chat/completions'):
            raise ValueError('Unexpected branch-only route')
        return dict(config, chat_url=ENDPOINT), key

    connection._t02_planning_affinity = True
    module.connection = connection
