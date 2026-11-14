import copy,json,tempfile
from pathlib import Path
from status_identity_audit import audit

valid=dict(episode_id='episode',task_id='task',task_intent_revision=2,task_version=3,
           state='completed',completion='verified',agent_execution=dict(
               phase='completed',completion_current_verified=True,task_id='task',semantic_revision=2))
def check(state):
    with tempfile.TemporaryDirectory()as temp:
        d=Path(temp);(d/'client').mkdir()
        (d/'client/system_events.jsonl').write_text(json.dumps(dict(type='system.status',status=state))+'\n')
        return audit(d)
assert check(valid)['invalid_completion']==0
full=copy.deepcopy(valid);full['agent_execution'].update(episode_id='episode',task_version=3)
assert check(full)['invalid_completion']==0
for field,value in [('episode_id','old'),('task_version',1),('semantic_revision',1),('task_id','old'),('phase','running')]:
    sample=copy.deepcopy(full);sample['agent_execution'][field]=value
    assert check(sample)['invalid_completion']==1,field
for field,value in [('state','running'),('completion','unverified')]:
    sample=copy.deepcopy(valid);sample[field]=value
    assert check(sample)['invalid_completion']==1,field
sample=copy.deepcopy(valid);del sample['agent_execution']['semantic_revision']
assert check(sample)['invalid_completion']==1
print('Public-schema audit: optional missing fields reported, not fabricated stale identities; 8 stale/unverified/missing-mandatory negatives passed')
