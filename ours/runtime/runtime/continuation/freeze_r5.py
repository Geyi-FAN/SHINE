import hashlib,json,subprocess,time,shutil
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102');OUT=ROOT/'R5';OUT.mkdir(exist_ok=True)
def freeze():
 paths=[B/p for p in subprocess.check_output(['git','ls-files'],cwd=B,text=True).splitlines()]
 for part in ['repair','continuation','artifacts/repair_audio_daemon/dist']:paths.extend((B/part).rglob('*'))
 paths.extend((OUT/'dataset').glob('*.json'))
 excluded={'progress.py','engineering_r4.py','service_smoke.py','r5_probe.py'}
 files={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths if p.is_file()and '__pycache__'not in p.parts and p.suffix!='.pyc'and p.name not in excluded}
 path=OUT/'FREEZE.json';assert not path.exists();path.write_text(json.dumps(dict(revision='R5',time=time.time(),files=files,changes='R4 physical and speech modules unchanged; facade accepts bodyless evaluator POST; same owned process facade for web/evaluation; receipt-based resume scoring'),indent=2));print('FROZEN',len(files),flush=True)
if __name__=='__main__':freeze()
