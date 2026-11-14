"""Prepare all3 QA repair cases; never pool them into a fictitious new24 SR."""
import hashlib,json,shutil,time
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102')
def main():
 assert (ROOT/'R7_READY_TO_FREEZE.json').exists(),'actual resume engineering acceptance required'
 out=ROOT/'R7/qa3';out.mkdir(exist_ok=False,parents=True);shutil.copytree(ROOT/'R5b/dataset',out/'dataset')
 cases=json.loads((out/'dataset/selected.private.json').read_text());cases=[c for c in cases if c['script_id']=='T6_01'];assert len(cases)==3;(out/'dataset/selected.private.json').write_text(json.dumps(cases,indent=2))
 protocol=json.loads((ROOT/'R6/regression18b/dataset/PROTOCOL.json').read_text());protocol['setup']['predecessor_input']='reviewed_source_audio';protocol['qa_evidence_revision']='current-location QA judged against exact captured image + contemporaneous private physics, not all moving states between user speech and reply; old scores retained';(out/'dataset/PROTOCOL.json').write_text(json.dumps(protocol,indent=2))
 manifest=json.loads((ROOT/'R6/regression18b/FREEZE.json').read_text())
 for p,h in manifest['files'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
 paths=list((B/'artifacts/repair7_audio_daemon/dist').rglob('*.js'))+list((out/'dataset').glob('*.json'))+[B/'continuation'/n for n in ['run_r7.py','service_r7.py','gateway_r7.py','authorized_resume.py','dispatched_policy_index.py','collect_qa_frames.py','audited_score.py','qa_snapshot_audit.py','test_audited_score.py','test_qa_snapshot_audit.py','test-qa-identity.mjs']]
 for p in paths:manifest['files'][str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
 manifest.update(revision='R7-QA-system-consistency-and-explicit-budget-resume',time=time.time(),changes='R6 weights/YOLO/four execution-role prompts unchanged; QA system permits evidence-supported visible grasp; log actual QA image hash, prompt and answer. Authorized budget-exhausted resume extends allowance once, ordinary resume does not. All3 QA states tested, not pooled into a new24 SR; after-result facade idle wait removed,30s cloud cooling retained; both10s/45s waiting and exact-image QA audit reported')
 (out/'FREEZE.json').write_text(json.dumps(manifest,indent=2));print(out)
if __name__=='__main__':main()
