"""Engineering cases kept outside the formal 330 first-attempt cohort."""
import concurrent.futures,json,subprocess,time,sys,urllib.request
from pathlib import Path
from service_identity import validate_policy,validate_provider
N=Path(__file__).resolve().parents[1]
B=N.parents[1]
SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
NODE='/mnt/disk_2/geyi/voice_pi05_harness/runtime/node-v22.23.3-linux-x64/bin/node'

def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def one_trial_score(data,case_id):
    if data.get('schema')=='t2_portable_judge_output_v1':
        rows=data.get('rows',[])
        if len(rows)!=1 or rows[0].get('case_id')!=case_id:
            return {'error':'independent T2 judge returned wrong case/count'}
        return rows[0]
    return data
def score(case,branch):
    if branch=='T6':
        from collect_audio_repaired import bind
        result=bind(case);write(case/'QA_AUDIO_EVIDENCE.json',result)
        return {'qa_started':result['qa_started'],'outputs':result.get('outputs'),'factual_review_pending':True}
    subprocess.run([NODE,str(B/'regressions/c3r_pi05_70_serial_20261108/tools/audit_audio.mjs'),str(case)],capture_output=True,text=True)
    p=subprocess.run([SIM,'-B',str(N/'tools/score_case_r4.py'),case.name,str(case),str(case/'SCORE_AUDITED.json')],capture_output=True,text=True)
    write(case/'SCORING_PROCESS.json',dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
    return one_trial_score(json.loads((case/'SCORE_AUDITED.json').read_text()),case.name) if(case/'SCORE_AUDITED.json').exists()else {'error':'no_score'}
