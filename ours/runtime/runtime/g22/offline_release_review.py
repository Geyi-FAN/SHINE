"""New recovery-Agent calls on recorded RGB/proprioception; no actions or GT."""
import argparse,json,sys
from pathlib import Path
import numpy as np
from PIL import Image
B=Path(__file__).resolve().parents[1];sys.path[:0]=[str(B),str(B/'g2')]
from bootstrap import configure

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False);(args.out/'logs').mkdir()
    configure(args.out,4)
    from recovery_observer import RecoveryObserver
    import recovery_observer
    from g22.return_release import ADDENDUM
    recovery_observer.SYSTEM+=ADDENDUM
    source=Path('/mnt/disk_4/geyi/voice_f28d_G21_20261101/G21_natural8_v1/SW4_T02_M2_T08_SWITCH_T02_M2_S04/kernels/g001')
    records=[json.loads(l)for l in(source/'completion_observations.jsonl').read_text().splitlines()];dets={r['frame']:r['points']for r in[json.loads(l)for l in(source/'points/detections.jsonl').read_text().splitlines()]if r['time_source']=='current'}
    task=json.loads((source/'agent_calls.json').read_text())[0]['input']['user_message'];out=[]
    for label,selected in [('airborne_early',records[:3]),('occluded_late',records[-3:])]:
        rows=[]
        for record in selected:
            # Deliberately discard oracle_for_scoring_only rather than copy it.
            sensor=record['sensor'];frame=sensor['frame'];rows.append(dict(frame=frame,main=np.asarray(Image.open(source/'points'/f'{frame}_current.png').resize((224,224))),wrist=np.asarray(Image.open(source/'points'/f'{frame}_wrist.png').resize((224,224))),sensor=dict(sensor,width=float(np.abs(sensor['gripper_qpos']).sum())),image_points=dets[frame],geometry=record['diagnostics'].get('observable_geometry',{})))
        observer=RecoveryObserver(args.out/label);diagnostics=dict(holding=selected[-1]['diagnostics']['holding'],observation_request_context=dict(reason='return_has_not_completed_after_bounded_execution',selected_stage=dict(operation='return_wine_bottle',kind='return',object='wine_bottle')))
        result=observer.check(task,rows,diagnostics);out.append(dict(label=label,result=result,interpretation='recorded image-only development diagnostic; no executed action'))
    (args.out/'RESULTS.json').write_text(json.dumps(out,indent=2));print(json.dumps(out),flush=True)
if __name__=='__main__':main()
