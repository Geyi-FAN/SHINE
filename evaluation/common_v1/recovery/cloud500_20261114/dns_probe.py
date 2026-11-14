"""Compare DNS servers without changing host/container configuration."""
import concurrent.futures
import json
import socket
import struct
import time
from pathlib import Path

R = Path(__file__).resolve().parent

def skip_name(raw, pos):
    while raw[pos]:
        if raw[pos] & 0xC0 == 0xC0:
            return pos + 2
        pos += raw[pos] + 1
    return pos + 1

def probe(item):
    server, host, trial = item
    query = b''.join(bytes([len(p)]) + p.encode() for p in host.split('.')) + b'\0'
    packet = struct.pack('!6H', 14231 + trial, 0x100, 1, 0, 0, 0) + query + struct.pack('!HH', 1, 1)
    start = time.monotonic()
    result = dict(server=server, host=host, trial=trial)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(2)
            s.sendto(packet, (server, 53))
            raw, _ = s.recvfrom(4096)
        ident, flags, nq, na, _, _ = struct.unpack('!6H', raw[:12])
        assert ident == 14231 + trial
        pos = 12
        for _ in range(nq):
            pos = skip_name(raw, pos) + 4
        ips = []
        for _ in range(na):
            pos = skip_name(raw, pos)
            kind, cls, ttl, size = struct.unpack('!HHIH', raw[pos:pos + 10])
            pos += 10
            if kind == 1 and cls == 1 and size == 4:
                ips.append(socket.inet_ntoa(raw[pos:pos + size]))
            pos += size
        result.update(passed=bool(ips) and (flags & 15) == 0, rcode=flags & 15, addresses=ips)
    except Exception as e:
        result.update(passed=False, error=type(e).__name__ + ': ' + str(e))
    result['elapsed_s'] = time.monotonic() - start
    return result

if __name__ == '__main__':
    servers = ['1.1.1.1', '8.8.8.8', '8.8.4.4', '127.0.0.53', '223.5.5.5', '119.29.29.29', '114.114.114.114']
    tasks = [(s, h, i) for s in servers for h in ['llmapi.paratera.com', 'dashscope.aliyuncs.com'] for i in range(3)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as pool:
        results = list(pool.map(probe, tasks))
    value = dict(probes=results, before_resolv_conf=Path('/etc/resolv.conf').read_text(), at=time.time())
    (R / 'DNS_PROBE.json').write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({s: dict(passed=sum(x['passed'] for x in results if x['server'] == s),
                              planned=6, addresses=sorted({a for x in results if x['server'] == s for a in x.get('addresses', [])}))
                      for s in servers}), flush=True)
