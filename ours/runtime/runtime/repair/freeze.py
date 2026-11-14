"""Snapshot this candidate and referenced files, excluding credentials/runtime data."""
import hashlib,json,os,subprocess,time
from pathlib import Path
B=Path(__file__).resolve().parents[1];OUT=Path(os.environ.get('AUDIO_REPAIR_OUT','/mnt/disk_4/geyi/voice_audio_unified_repair_20261102'))
paths=[B/p for p in subprocess.check_output(['git','ls-files'],cwd=B,text=True).splitlines()]
paths+=list((B/'repair').rglob('*'));paths+=list((B/'artifacts/repair_audio_daemon/dist').rglob('*.js'));paths+=[B/'artifacts/G22_audio_client.mjs'];paths+=list((OUT/'dataset').glob('*.json'))
files={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths if p.is_file()and '__pycache__'not in p.parts and p.suffix not in('.pyc',)}
old=OUT/'FREEZE.json'
if old.exists():
 history=OUT/'freezes';history.mkdir(exist_ok=True);(history/('FREEZE_'+str(time.time_ns())+'.json')).write_bytes(old.read_bytes())
old.write_text(json.dumps(dict(revision='R3',time=time.time(),files=files,changes='dedicated audio clock; launch-feature parity; literal clarification; current terminal and deferred lifecycle; bounded task wording'),indent=2));print(json.dumps(dict(files=len(files),freeze=str(old))))
