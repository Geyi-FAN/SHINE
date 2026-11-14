"""Frozen R6 physical core and received-PCM path, R7 QA-only voice artifact."""
from pathlib import Path
B=Path(__file__).resolve().parents[1]
source=(B/'repair6/run.py').read_text()
old="B/'artifacts/repair6_audio_daemon/dist/index.js'"
assert source.count(old)==1
source=source.replace(old,"B/'artifacts/repair7_audio_daemon/dist/index.js'")
old="B/'repair6/service.py'";assert source.count(old)==1
source=source.replace(old,"B/'continuation/service_r7.py'")
old="spec['source_audio_setup']=spec['protocol'].get('setup',{}).get('predecessor_input')=='reviewed_source_audio'"
assert source.count(old)==1
source=source.replace(old,old+" or authored['case_id'] in spec['protocol'].get('setup',{}).get('source_audio_case_ids',[])")
old="   if not probe:\n    try:processes[1].wait(30)\n    except subprocess.TimeoutExpired:pass"
assert source.count(old)==1
source=source.replace(old,"   # Client already captured results and flushed PCM; finally closes the persistent facade.\n   from continuation.collect_qa_frames import collect\n   collect(directory)")
if __name__=='__main__':exec(compile(source,str(B/'continuation/generated_run_r7.py'),'exec'),dict(__name__='__main__',__file__=str(B/'repair6/run.py')))
