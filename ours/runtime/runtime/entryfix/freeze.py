import hashlib,json,time
from pathlib import Path
B=Path(__file__).resolve().parents[1];D=B/'run_data'
p=json.loads((D/'PROTOCOL.json').read_text());p.update(version='T3-entryfix-v1.7',runtime='R7-T3.2 entry guards; scoped task lifecycle; authorized English verbatim; release goal guidance; canonical sentence ending; actual new-task VLA timing',support='native task6 On(cheese,bowl), not In; measured current nonrobot upward resultant contact force; existing minimum support force, release and stability windows; original geometric proxy retained',legacy_scoring='each rollout additionally scored with original geometric support proxy',preflight='same reviewed waveforms and causal trigger reused from original; new engineering probe3 separately retained')
(D/'PROTOCOL.json').write_text(json.dumps(p,ensure_ascii=False,indent=2))
files=[]
for name in('entryfix','selected_eval','g2','g21','g22','audio24','repair','repair6','repair8','continuation','t3repair','freeze','artifacts/repair8_audio_daemon/dist','voice_source/src'):
 for f in(B/name).rglob('*'):
  if f.is_file()and f.suffix in('.py','.js','.mjs','.ts','.json','.txt')and not any(x in f.parts for x in('private','__pycache__','node_modules')):files.append(f)
files+=[D/x for x in('cases.private.json','audio.json','physical_rules.json','initial_states.json','PROTOCOL.json')]
for a in json.loads((D/'audio.json').read_text()):
 f=Path(a['file']);assert hashlib.sha256(f.read_bytes()).hexdigest()==a['sha256'];files.append(f)
data=dict(time=time.time(),baseline='/mnt/disk_2/geyi/audio_t3_selected10_20261102',cases=10,initial='I00',attempt_policy='development probes separate; freeze complete new formal10 first attempts; no best-case pooling',files={str(f):hashlib.sha256(f.read_bytes()).hexdigest()for f in files})
(D/'FREEZE.json').write_text(json.dumps(data,indent=2));print('frozen',len(data['files']))
