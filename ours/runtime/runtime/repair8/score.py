"""v1.9: exact waveform/output binding and equivalent bowl-location queries."""
from pathlib import Path
from repair8.audible_binding import bound_output
B=Path(__file__).resolve().parents[1]
def patch_judge(judge):
 judge=judge.replace('def audible_records(voice,messages):','def audible_records(voice,messages,directory=None):')
 judge=judge.replace('audible_records(voice,messages)','audible_records(voice,messages,directory)')
 old="        if not p.get('audioSuppressed'):"
 new="""        if p.get('source')=='isolated_result' and p.get('receipt_key'):
            bound=bound_output(p,messages,directory)
            if len(bound)!=1:continue
            chosen=bound[0];kind='exact_result_receipt_received_PCM_and_completed_playback'
        elif not p.get('audioSuppressed'):"""
 assert judge.count(old)==1;judge=judge.replace(old,new)
 old="        texts={e['payload'].get('text','').strip() for e,_ in matches}"
 new="""        exact=[m for m in matches if m[1].get('binding_method')]
        if exact:matches=exact  # Authoritative binding outranks timestamp guesses, regardless of answer correctness.
"""+old
 assert judge.count(old)==1;return judge.replace(old,new)

source=(B/'continuation/audited_score.py').read_text()
source=source.replace("'v1.8_wait'","'v1.9_wait'").replace("audit_revision='v1.8-exact-snapshot-qa-and-bound-control-receipts'","audit_revision='v1.9-exact-isolated-output-and-PCM-binding'").replace('from continuation.qa_snapshot_audit import score as snapshot_score','from repair8.qa_snapshot import score as snapshot_score')
old="judge=(B/'repair6/reference/score_dev96.py').read_text()";assert source.count(old)==1
source=source.replace(old,old+"\n    judge=patch_judge(judge)\n    score_dev96.__dict__['bound_output']=bound_output")
old="source=(B/'repair6/score.py').read_text()";assert source.count(old)==1
source=source.replace(old,old+"\n    source=source.replace(\"score_dev96.audible_records(voice,r.get('messages',[]))\",\"score_dev96.audible_records(voice,r.get('messages',[]),directory)\")\n    source=source.replace(\"code_base='R6-compound-pause-same-execution-core'\",\"code_base='R8-output-binding-with-R7-physical-core'\")")
if __name__=='__main__':exec(compile(source,str(B/'repair8/generated_score.py'),'exec'),dict(__name__='__main__',__file__=str(B/'repair8/score.py'),patch_judge=patch_judge,bound_output=bound_output))
