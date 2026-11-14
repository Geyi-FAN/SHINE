from pathlib import Path
import shutil,json,hashlib,os
Q=Path(__file__).resolve().parents[1];B=Q.parents[1];P=B/'deployments/asr_agent_oracle_formal840_240_20261109';N=B/'deployments/ours_full930_readiness_20261114'
A=Q/'actors/B1'
assert not A.exists(),'Do not overwrite method snapshot'
shutil.copytree(P/'reference_r6',A,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','runs','logs','cache','asr_service','reports'))
old='/mnt/disk_4/geyi/audio_switch_benchmark/experiments/asr_agent_oracle_20261108/revisions/cloud01_20261109_r6'
for p in A.rglob('*'):
 if p.is_file()and not p.is_symlink()and 'node_modules'not in p.parts and p.suffix in ['.py','.mjs','.js','.json','.txt']and'private'not in p.relative_to(A).parts:
  try:s=p.read_text()
  except UnicodeDecodeError:continue
  if old in s:p.write_text(s.replace(old,str(A)))
for method in ['B0','B1']:
 d=Q/'actors'/method/'private';d.mkdir(exist_ok=True);d.chmod(0o700)
 for f in ['robot.token','browser.token']:
  shutil.copy2(P/'reference_r6/private'/f,d/f);(d/f).chmod(0o600)
 d=Q/'actors'/method/'cache/tmp';d.mkdir(parents=True,exist_ok=True)
# No key values enter logs or public provenance.
priv=Q/'private';priv.mkdir(exist_ok=True);priv.chmod(0o700)
keys=[]
for lane in range(4):
 cfg=json.loads((N/('private/voice_lane%d.json'%lane)).read_text());key=cfg.get('realtimeApiKey')
 assert isinstance(key,str)and len(key)>20
 p=priv/('tts_lane%d.key'%lane);p.write_text(key);p.chmod(0o600);keys.append(hashlib.sha256(key.encode()).hexdigest())
 (priv/('agent_lane%d.lock'%lane)).touch()
assert len(set(keys))==4,'Independent configured realtime key routing required'
(Q/'reports/ACCOUNT_ISOLATION.json').write_text(json.dumps(dict(credential_key_hashes=keys,distinct_keys=4,independent_account_ownership='prior user-provided independent-account routing; key distinctness alone not proof',raw_keys_published=False),indent=2))
mods=Q/'node_modules'
if not mods.exists():mods.symlink_to(N/'code/runtime_v8/node_modules',target_is_directory=True)
# T8 alias adapter is purely protocol field translation, no actor logic.
for method in ['B0','B1']:
 p=Q/'actors'/method/'tools/t8_client_compat.mjs';p.parent.mkdir(exist_ok=True)
 if not p.exists():
  shutil.copy2(A/'tools/t8_client_compat.mjs',p)
import subprocess,sys
subprocess.run([sys.executable,'-B',str(Q/'tools/patch_actors.py')],check=True)
print('remote snapshots prepared, methods unchanged except declared common measurement/source/client transport')
