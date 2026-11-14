"""T4-only planning pool. Same model, exact bytes, no retries or fallback.

Observe the existing services' actual running/waiting load. Do not restart
models or alter the shared18084 pool. Both upstream replicas use32K context.
"""
import importlib.util
import json
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer

DEPLOY = Path('/mnt/disk_4/geyi/F1_switch308_20261031/evolution/fp8_deployment_20261031')
ROOT = Path('/mnt/disk_4/geyi/t4_audio50_c3r_unified_v2_20261104')
spec = importlib.util.spec_from_file_location('t02_original_pool', DEPLOY / 'fp8_pool.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)


def backend_specs(key):
    return [dict(id='fp8-174-' + str(index), base='http://127.0.0.1:' + str(port) + '/v1',
                 key=key, max_active=2, max_backend_load=2, roles=['planning'])
            for index, port in enumerate((28174, 28175))]


def main():
    compatibility = json.loads((DEPLOY / 'MODEL_COMPATIBILITY.json').read_text())
    assert compatibility['critical_files_equal'] and compatibility['quantizations_equal']
    assert compatibility['weight_mapping_equal']
    key = (DEPLOY / 'private/client.key').read_text().strip()
    upstream_key = (DEPLOY / 'private/174_api.key').read_text().strip()
    pool = original.Pool(backend_specs(upstream_key), key, ROOT / 'logs/planning_pool_requests.jsonl')
    pool.queue_timeout = 75       # Same queue deadline as the shared capacity pool.
    pool.upstream_timeout = 180  # Same transport deadline; not a scoring change.
    threading.Thread(target=pool.monitor, daemon=True).start()
    server = ThreadingHTTPServer(('127.0.0.1', 18184), original.handler(pool))
    server.daemon_threads = True
    print(json.dumps(dict(port=18184, model=original.MODEL, planning_only=True,
                          body_rewrite=False, generation_retries=0, public_service_changed=False)), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
