"""Hash all method/adapter code plus external runtime, assets and reviewed audio."""
import hashlib,json,subprocess,time
from pathlib import Path
B=Path(__file__).resolve().parents[1];OUT=Path('/mnt/disk_4/geyi/audio_switch24_F28d_G22_20261102');DATA=OUT/'dataset'
def main():
 assert not(OUT/'FREEZE_v3.json').exists(),'Never replace an existing formal freeze'
 paths=[B/p for p in subprocess.check_output(['git','ls-files'],cwd=B,text=True).splitlines()]
 for root in [B/'audio24',B/'artifacts/G22_audio_daemon/dist',Path('/mnt/disk_2/geyi/voice_pi05_harness/data/receipt_audio')]:paths.extend(p for p in root.rglob('*')if p.is_file()and'__pycache__'not in p.parts)
 paths.extend(DATA.iterdir());paths.extend([B/'artifacts/G22_audio_client.mjs',B/'freeze/voice/configs/runtime.local.json',B/'freeze/voice/data/harness/config.json',B/'freeze/voice/runtime/node-v22.23.3-linux-x64/bin/node'])
 for a in json.loads((DATA/'audio.json').read_text()):paths.append(Path(a['file']))
 for s in json.loads((DATA/'initial_states.json').read_text()):paths.extend(Path(a['path'])for a in s['assets'].values())
 paths.append(Path('/mnt/disk_4/geyi/yolo_v3r_3000_20261024/runs/yolo26s_pose_50ep/weights/best.pt'))
 hashes={str(p.absolute()):hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted(set(paths))if p.is_file()and p.suffix!='.pyc'}
 result=dict(time=time.time(),base_commit='f1f6f69',evaluation_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=B,text=True).strip(),files=hashes,case_count=24,retries=0,first_attempts=True,no_live_method_edits=True)
 (OUT/'FREEZE_v3.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(frozen_files=len(hashes),evaluation_commit=result['evaluation_commit'])))
if __name__=='__main__':main()
