"""Four fixed entry states x two schedulers; retain every first attempt."""
import argparse,concurrent.futures,json,subprocess,time
from pathlib import Path
B=Path(__file__).resolve().parents[1];SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
DATA=Path('/mnt/disk_4/geyi/voice_f28d_G21_20261101')
parser=argparse.ArgumentParser();parser.add_argument('--label',default='close_entry8_v2');opts=parser.parse_args()
OUT=Path('/mnt/disk_4/geyi/voice_f28d_G22_20261101')/opts.label
REPORT=B/'reports/G22'/opts.label;REPORT.mkdir(exist_ok=True)
SELECT=[('middle','G21_fixed32_v1','SW4_T00_D1_T07_CLOSE_MIDDLE_T00_D1_S02'),('top_inside','G21_fixed32_v1','SW4_T03_C6_T09_CLOSE_TOP_T03_C6_S01'),('top_after_return_A','G21_fixed32_v1','SW4_T03_C4_T08_CLOSE_TOP_T03_C4_S03'),('top_after_return_B','G21_close_gate_dev3_v1','SW4_T03_C4_T08_CLOSE_TOP_T03_C4_S03')]
def worker(item):
    index,(name,label,cid)=item;contexts=sorted((DATA/label/cid/'stage_contexts').glob('*.npz'));assert contexts
    context=contexts[0];arms=['original','preflight']if index%2==0 else['preflight','original'];results=[]
    for arm in arms:
        out=OUT/name/arm;out.parent.mkdir(parents=True,exist_ok=True);log=B/'logs'/('G22_'+opts.label+'_'+name+'_'+arm+'.log')
        with log.open('w')as f:p=subprocess.run([SIM,'-u','g22/close_pair.py','--context',str(context),'--arm',arm,'--out',str(out),'--gpu',str(4+index),'--port',str(19866+index),'--budget','400'],cwd=B,stdout=f,stderr=subprocess.STDOUT,timeout=1000)
        r=json.loads((out/'result.json').read_text())if(out/'result.json').exists()else dict(kernel_error='missing_result')
        row=dict(state=name,arm=arm,returncode=p.returncode,complete=r.get('observed_complete'),physical_closed=r.get('private_current_closed_5ticks'),false_completion=r.get('false_completion'),error=r.get('kernel_error'),result=str(out/'result.json'))
        results.append(row)
        with(REPORT/'progress.jsonl').open('a')as f:f.write(json.dumps(row)+'\n')
        print(json.dumps(row),flush=True)
    return results
if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=False)
    (REPORT/'PROTOCOL.json').write_text(json.dumps(dict(states=SELECT,arms=['original','preflight'],replicates=1,budget=400,wall_seconds=600,planned_cases=8,complete_context_and_both_initial_images_verified=True,fixed_original_agent_subgoal=True,active_recovery_tools='off in both arms',acceptance='unchanged observed verifier; private 1cm/5 actual physics ticks for scoring only',physics='one owner, evolves during model HTTP; no state writes after trial start'),indent=2))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:results=sum(list(pool.map(worker,enumerate(SELECT))),[])
    (REPORT/'COMPLETED.json').write_text(json.dumps(dict(completed_unix=time.time(),results=results),indent=2))
