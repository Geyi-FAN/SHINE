import hashlib,json,shutil,time
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102')
def main():
 out=ROOT/'R8/qa3';out.mkdir(parents=True,exist_ok=False);shutil.copytree(ROOT/'R7/qa3/dataset',out/'dataset')
 p=out/'dataset/PROTOCOL.json';protocol=json.loads(p.read_text());protocol['speech_evidence_revision']='R8 individual output start, transcript receipt key, generated vs received PCM SHA256; legacy aggregate callback preserved; equivalent bowl-location query permitted with unique episode/image provenance';p.write_text(json.dumps(protocol,indent=2))
 manifest=json.loads((ROOT/'R7/qa3/FREEZE.json').read_text())
 for p,h in manifest['files'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
 files=list((B/'repair8').glob('*.py'))+list((B/'repair8').glob('*.mjs'))+list((B/'artifacts/repair8_audio_daemon/dist').rglob('*.js'))+list((out/'dataset').glob('*.json'))
 for p in files:manifest['files'][str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
 manifest.update(revision='R8-individual-speech-binding',time=time.time(),changes='R7 physical service, weights, YOLO, four execution-role prompts unchanged; each isolated speech owns outputId and receipt key, received PCM hash audited; individual start callback supplements unchanged legacy aggregate callbacks; no external timing/geometry budget relaxation; repeat all3 QA states without pooling R7 successes')
 (out/'FREEZE.json').write_text(json.dumps(manifest,indent=2));print(out)
if __name__=='__main__':main()
