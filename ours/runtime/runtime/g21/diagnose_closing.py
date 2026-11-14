"""Read-only diagnosis: physical closure, observed stage gate, subsequent task.

Simulator truth is used only here to label failure sources, never to plan.
"""
import collections,csv,gzip,json,sys
from pathlib import Path

B=Path(__file__).resolve().parents[1]
CASES={c['case_id']:c for c in json.loads((B/'g2/fixed32.json').read_text())}
CONTRACTS={c['case_id']:c for c in json.loads((B/'freeze/study/data/contracts_private.json').read_text())}

def lines(path):
    return [json.loads(x)for x in path.read_text().splitlines()if x.strip()]if path.exists()else[]

def analyze(root,label):
    result=[]
    for p in sorted(root.glob('*/result.json')):
        d=json.loads(p.read_text());cid=d['case_id'];contract=CONTRACTS[cid]
        close=[c for c in contract['clauses']if c['kind']=='close_event']
        if not close:continue
        with gzip.open(p.parent/'gateway_trace.json.gz','rt')as f:trace=json.load(f)['measurements']
        stages=[];gate=[]
        for k in sorted((p.parent/'kernels').glob('*/result.json')):
            kd=json.loads(k.read_text());stages+=kd.get('selected_stages',[])
            gate+=lines(k.parent/'verifier/calls.jsonl')
        for c in close:
            level=c['joint'];op='close_'+level
            close_frame=d['metrics'].get('completion_events',{}).get(c['id'])
            selected=[x for x in stages if x['operation']==op]
            observed=any(x.get('operation')==op for x in d.get('completed_events',[]))
            checks=[x for x in gate if x.get('operation')==op]
            guards=[x.get('independent_drawer_guard',{})for x in checks]
            full=bool(d['metrics'].get('instruction_adjusted',{}).get('success'))
            if full:category='full_task_pass'
            elif close_frame is None:category='physical_close_not_verified'if selected else'close_stage_not_reached'
            elif not observed:category='physical_close_pass_but_observed_stage_not_advanced'
            else:category='close_advanced_but_remaining_task_failed'
            vals=[max(0.,-r['source']['articulation'][level])for r in trace]
            row=dict(batch=label,case_id=cid,group=d['group'],drawer=level,category=category,
                     instruction_success=full,physical_close_event=close_frame,
                     observed_close_event=observed,entered_close=selected[0]['entered_step']if selected else None,
                     min_gap_cm=100*min(vals)if vals else None,last_gap_cm=100*vals[-1]if vals else None,
                     visual_checks=len(checks),geometry_passes=sum(g.get('passed')is True for g in guards),
                     geometry_reasons=dict(collections.Counter(g.get('reason','not_reported')for g in guards)),
                     selected_stages=' -> '.join(x['operation']for x in stages),
                     full_task=CASES[cid]['public_user_instruction'],result=str(p),
                     video=str(p.parent/'gateway_environment.mp4'))
            result.append(row)
    return result

def main():
    out=B/'reports/G21/closing';out.mkdir(exist_ok=True)
    old=Path('/mnt/disk_4/geyi/voice_f28d_G2_20261101')
    rows=[]
    for root,label in [(old/'G2_fixed32_v2','G2_fixed32'),(old/'G2_natural8_v2','G2_natural8'),
                       (B/'runs/G21_fixed32_v1','G21_fixed32'),(B/'runs/G21_natural8_v1','G21_natural8')]:
        rows+=analyze(root,label)
    (out/'cases.json').write_text(json.dumps(rows,indent=2))
    if rows:
        with(out/'cases.csv').open('w')as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    counts={label:dict(collections.Counter(r['category']for r in rows if r['batch']==label))for label in sorted({r['batch']for r in rows})}
    (out/'summary.json').write_text(json.dumps(counts,indent=2))
    plot_examples(out)
    print(json.dumps(counts),flush=True)

def plot_examples(out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    examples=[('G2_fixed32_v2','SW4_T00_D1_T07_CLOSE_MIDDLE_T00_D1_S02','middle'),
              ('G2_natural8_v2','SW4_T03_C4_T08_CLOSE_TOP_T03_C4_S03','top')]
    fig,axes=plt.subplots(2,1,figsize=(11,7))
    for ax,(batch,cid,level)in zip(axes,examples):
        root=Path('/mnt/disk_4/geyi/voice_f28d_G2_20261101')/batch/cid
        with gzip.open(root/'gateway_trace.json.gz','rt')as f:rows=json.load(f)['measurements']
        ax.plot([r['engine_control_step']for r in rows],[100*max(0.,-r['source']['articulation'][level])for r in rows],label='Private physical gap (diagnosis only)')
        for path in(root/'kernels').glob('*/verifier/calls.jsonl'):
            for c in lines(path):
                if c['operation']!='close_'+level:continue
                g=c.get('independent_drawer_guard',{});est=g.get('depth_estimates')or g.get('estimates')or[]
                if est:ax.scatter([x['frame']for x in est],[100*abs(x['gap_m'])for x in est],s=8,c='tab:orange',label='_nolegend_')
        ax.scatter([],[],c='tab:orange',label='Observed RGB-D / ray gap estimates')
        ax.axhline(1.,color='red',linestyle='--',label='1 cm close tolerance')
        ax.set_title(cid,fontsize=9);ax.set_xlabel('Actual authorized control actions');ax.set_ylabel('Drawer gap (cm)');ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(out/'physical_vs_observed_gap.png',dpi=150);plt.close(fig)

if __name__=='__main__':main()
