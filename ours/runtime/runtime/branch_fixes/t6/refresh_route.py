"""Validate a private temporary route under the existing shared audio lease."""
import fcntl,json,subprocess,time
from pathlib import Path
A=Path(__file__).resolve().parent
W=Path('/mnt/disk_2/geyi/t6_c3r_20_20261103')
lease=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102/R9/parallel21/single_voice.lock')
with lease.open('r+b')as f:
 fcntl.flock(f,fcntl.LOCK_EX);f.seek(0);last=float(f.read().strip()or b'0');time.sleep(max(0.,30-(time.time()-last)))
 with(W/'reports/ROUTE_REFRESH.log').open('w')as log:
  r=subprocess.run(['/mnt/disk_2/geyi/voice_pi05_harness/runtime/node/bin/node',str(A/'scripts/audio_switch_benchmark/prepare_network_route.mjs'),str(W/'data/network_route.json')],stdout=log,stderr=log,timeout=90)
 f.seek(0);f.truncate();f.write(str(time.time()).encode());f.flush();fcntl.flock(f,fcntl.LOCK_UN)
 assert r.returncode==0,'fresh authenticated network route failed; see ROUTE_REFRESH.log'
route=json.loads((W/'data/network_route.json').read_text());assert route['last_verified_addresses']
print('Temporary route revalidated with official TLS/SNI and authenticated session readiness; no task audio.')
