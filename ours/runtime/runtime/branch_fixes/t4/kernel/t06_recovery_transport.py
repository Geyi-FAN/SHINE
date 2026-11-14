"""Same image/recovery request, separate174-only branch transport."""
ENDPOINT = 'http://127.0.0.1:18185/v1/chat/completions'


def install(module=None):
    if module is None:
        import local_transport as module
    original = module.connection
    if getattr(original, '_t06_recovery_affinity', False):
        return

    def connection(role):
        config, key = original(role)
        if role != 'recovery':
            return config, key
        if config.get('chat_url') != 'http://127.0.0.1:18084/v1/chat/completions' or config.get('model') != 'Qwen3.8-27B-FP8':
            raise ValueError('Unexpected parent recovery service')
        if ENDPOINT != 'http://127.0.0.1:18185/v1/chat/completions':
            raise ValueError('Unexpected branch recovery endpoint')
        return dict(config, chat_url=ENDPOINT), key

    connection._t06_recovery_affinity = True
    module.connection = connection
