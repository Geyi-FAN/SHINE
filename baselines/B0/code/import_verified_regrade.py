"""Reuse cross-branch shared v4 regrades only after source hash verification."""
import concurrent.futures,collections,datetime,hashlib,json,shutil
from pathlib import Path
N=Path(__file__).resolve().parents[1]
B=Path('/mnt/disk_4/geyi/audio_switch_benchmark/experiments/asr_agent_oracle_20261108/revisions/cloud01_20261109_r3')
OUT=N/'reports/original840_v4'
def read(p):return json.loads(Path(p).read_text())
def work(row):
 assert row['method']=='B0'
 for p,sha in row['source_sha256'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha,('source changed',p)
 case=Path(row['case']);old=read(case/'score.json')if row['branch']=='T1'else read(case/'SCORE.json');old=old['rows'][0]if'rows'in old else old
 v=read(row['score']);branch=row['branch'];uid=read(case/'result.json').get('trial_uid',case.name);uid=case.name if uid is None else uid
 assert v['scoring_version']=='audio-logical-goal-attribution-v4-20261109';assert v['interaction']==old['interaction'],'Physical attribution must not silently fix interaction'
 folder=OUT/branch/uid;folder.mkdir(parents=True,exist_ok=True);dest=folder/'SCORE_V4.json'
 if not dest.exists():shutil.copy2(row['score'],dest)
 else:assert dest.read_bytes()==Path(row['score']).read_bytes()
 provenance=dict(row,verified_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),imported_score=str(dest),old_instruction=old.get('instruction'),new_instruction=v.get('instruction'),source_score_sha256=hashlib.sha256(Path(row['score']).read_bytes()).hexdigest());(folder/'PROVENANCE.json').write_text(json.dumps(provenance,indent=2))
 return provenance
def main():
 rows=[r for r in read(B/'reports/adjudication_v4/CASES.json')if r['method']=='B0'];assert len(rows)==840
 OUT.mkdir(exist_ok=True)
 with concurrent.futures.ThreadPoolExecutor(8)as pool:results=list(pool.map(work,rows))
 by={}
 for branch in ['T1','T2','T3','T4','T5','T7','T8']:
  xs=[r for r in results if r['branch']==branch];assert len(xs)==120
  denominator=108 if branch=='T5' else 84 if branch=='T8' else 120
  by[branch]=dict(instances=120,legacy_target=sum(x['legacy_target']=='pass'for x in xs),v4_target=sum(x['v4_target']=='pass'for x in xs),legacy_instruction=sum(x['old_instruction']=='pass'for x in xs),v4_instruction=sum(x['new_instruction']=='pass'for x in xs),interaction=sum(x['interaction']=='pass'for x in xs),target_denominator=denominator)
 report=dict(verified_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),instances=840,new_model_calls=0,new_robot_actions=0,source_hashes_verified=1680,all_originals_unchanged=True,shared_scoring_version='audio-logical-goal-attribution-v4-20261109',shared_scoring_source=str(B/'scoring_v4'),by_branch=by,T8='Legacy client invalid; no valid target-success estimate until applicable cases rerun; overlap-only cases unsupported in pure ASR.')
 (OUT/'SUMMARY.json').write_text(json.dumps(report,indent=2));(OUT/'CASES.json').write_text(json.dumps(results,indent=2));print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
