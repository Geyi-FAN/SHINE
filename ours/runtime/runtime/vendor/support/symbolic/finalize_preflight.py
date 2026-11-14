"""Bind V3R readiness to full labels, exact rendering checks and real GPU execution."""
import argparse,gzip,json
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from sym_paths import ROOT,DATA,BASE_DATA
from common import sha256,write_json,source_hashes
from summarize_eval import summarize
from symbolic_eval_identity import protocol_id

def read(p):return json.loads(Path(p).read_text())

def main():
    p=argparse.ArgumentParser();p.add_argument('--training-run',required=True);p.add_argument('--eval-dir',type=Path,required=True);a=p.parse_args()
    reports=ROOT/'reports';build=read(reports/'dataset_build.json')
    assert build['complete'] and build['all_causal_prefix_invariance_checked'] and build['shared_labels_equal_E3']
    assert build['total_anchors']==179765 and build['normal_token_parity'] and build['normal_marker_count']==0
    for name,digest in build['source_hashes'].items():assert sha256(BASE_DATA/name)==digest,name
    for name,digest in build['derived_hashes'].items():assert sha256(DATA/name)==digest,name
    for name in ['augmentation_integration','marker_validation','scheduled_prompt_lengths','mini_prompt_lengths','E3_alignment']:
        assert read(reports/(name+'.json'))['passed'],name
    tokens=read(reports/'scheduled_prompt_lengths.json');assert tokens['overflow']==0 and tokens['covered_unique_anchors']==179765
    finish=read(reports/(a.training_run+'_finished.json'));probe=read(reports/(a.training_run+'_parameter_update.json'))
    assert finish['status']=='short_run_completed' and finish['completed_updates']==3
    assert probe['total_parameters']==probe['trainable_parameters']==3353433872 and probe['changed_tensors']>0
    checkpoint=Path(finish['checkpoint']);identity=read(checkpoint.parent/'identity.json')
    assert identity['device_count']==8 and identity['micro_batch']==64 and identity['variant']=='V3R'
    for name in ['trainer.py','dataset.py','model_config.py','sym_augmentation.py','sym_contract.py','v3_markers.py']:
        file=ROOT/'src'/name;assert sha256(file)==identity['source_sha256'][str(file)],name
    assert identity['config_sha256']==sha256(ROOT/'configs/V3R.json')
    assert identity['symbolic_manifest_sha256']==sha256(DATA/'manifest.json')
    metrics=[json.loads(s) for s in (ROOT/'logs'/(a.training_run+'.jsonl')).read_text().splitlines()]
    assert [x['step'] for x in metrics]==[1,2,3]
    assert all(np.isfinite(x[k]) for x in metrics for k in ['loss','grad_norm','normal_loss','revision_loss'])
    summary,rows=summarize(a.eval_dir,smoke=True);assert summary['complete'],summary
    expected_protocol=protocol_id();calls=0;marked=0;transitions=0
    old_dir=Path('/mnt/disk_4/geyi/pi05_symbolic_E1_E3_20261015/evaluations/preflight_v5_E3')
    old={r['case_id']:r for f in old_dir.glob('shard_*/*.json') if 'case_id' in (r:=read(f))}
    paired=0
    for r in rows:
        assert r['protocol_id']==expected_protocol and r['smoke_only']
        assert r['diagnostic_budget_override']==48 and r['policy_actions']>0
        assert r['server_metadata']['weights']=='EMA' and Path(r['server_metadata']['checkpoint'])==checkpoint
        assert r['server_metadata']['visual_marker'] and not r['reset_after_policy_start'] and not r['state_writes_after_policy_start']
        with gzip.open(r['trace_path'],'rt') as f:t=json.load(f)
        assert len(t['actions'])==r['policy_actions']+r['hold_steps'];calls+=len(t['chunks'])
        for i,c in enumerate(t['chunks']):
            assert c['call']==i and 0<c['prompt_token_length']<=200
            arr=np.asarray(c['raw_actions']);assert arr.shape==(10,7) and np.isfinite(arr).all()
        if r['group']!='normal_libero':
            assert len(t['symbolic_calls'])==len(t['chunks'])
            for c in t['symbolic_calls']:
                m=c['marker'];assert m['view']=='MAIN'
                if m['valid']:
                    y,x=m['yx'];assert f'<{y},{x}>' in c['prompt'].split('Current Subgoal:')[1];marked+=1
        transitions+=len(r.get('oracle_events',[]))
        assert Path(r['video_path']).stat().st_size>1000 and Path(r['policy_input_video_path']).stat().st_size>1000
        if r['case_id'] in old:
            base=old[r['case_id']]
            assert r['start_state_identity']==base['start_state_identity']
            assert r['first_common_input_sha256']==base['first_common_input_sha256'];paired+=1
    assert paired==6,'Missing E3 paired smoke records'
    result=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),formal_training_started=False,
        dataset_manifest_sha256=sha256(DATA/'manifest.json'),source_hashes=source_hashes(),
        training_run=a.training_run,checkpoint=str(checkpoint),training_metrics=metrics,parameter_update=probe,
        evaluation_directory=str(a.eval_dir),short_rollout_cases=len(rows),policy_calls=calls,marked_calls=marked,
        online_stage_events=transitions,paired_E3_start_and_unmarked_inputs_equal=paired,
        evaluation_protocol=expected_protocol,preview_directory=str(ROOT/'previews'),
        human_visual_review='Requested by user; previews available, no user judgement inferred.',
        limitations=['Three gradient updates and short rollouts validate execution, not task success.',
          'Oracle perception and Oracle causal subgoals; no learned detector.',
          'Mini includes training scenes; no held-out generalization claim.',
          'Live stage transitions reported separately; full causal replay covers recorded trajectories.'])
    write_json(reports/'PREFLIGHT_COMPLETE.json',result);print(json.dumps({k:result[k] for k in ['passed','checkpoint','short_rollout_cases','policy_calls','marked_calls','online_stage_events']},indent=2))

if __name__=='__main__':main()
