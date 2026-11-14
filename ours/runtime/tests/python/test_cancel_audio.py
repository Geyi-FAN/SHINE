"""Synthetic control states with actual core/transactions; no robot or model."""
import copy,sys,tempfile
from pathlib import Path
A=Path(__file__).parent;B=A.parent
sys.path[:0]=[str(A),str(B/'freeze/voice/robot_gateway')]
from cancel_audio_evidence import verified_cancel
raw='Cancel the ball task. Keep going.';alternate='Cancel the bowl task. Keep going.';pending='put the bowl on the stove'
proof=dict(kind='audio_only_grounding.v2',primary=raw,transcript=alternate,reference_sent=False,scene_sent=False)
assert verified_cancel(raw,proof,pending)==alternate
for variation in ['absent','wrong_primary','reference','scene','negation','action','known_noun','other_pending','too_many_words']:
    p=copy.deepcopy(proof);text=raw;goal=pending
    if variation=='absent':p=None
    if variation=='wrong_primary':p['primary']='old input'
    if variation=='reference':p['reference_sent']=True
    if variation=='scene':p['scene_sent']=True
    if variation=='negation':p['transcript']='Do not cancel the bowl task. Keep going.'
    if variation=='action':p['transcript']='Open the bowl task. Keep going.'
    if variation=='known_noun':text='Cancel the cheese task. Keep going.';p['primary']=text
    if variation=='other_pending':goal='turn on the stove'
    if variation=='too_many_words':p['transcript']=alternate+' Open the drawer.'
    assert verified_cancel(text,p,goal)is None,variation

import core,waiting_runtime
from grounding import ENTITIES,inventory_from_names
waiting_runtime.install(core)
with tempfile.TemporaryDirectory()as d:
    s=core.RobotState(d);s.ready=True;s.mode='idle'
    s.scene_inventory=inventory_from_names(v[0]for v in ENTITIES.values())
    s.command('robot_start_task',dict(episode_id=s.episode,expected_task_version=s.version,instruction='put the wine bottle on the rack'),'start')
    source=s.task_id;old=s.version
    queued='When you are done, put the bowl on the stove.'
    s.record_interaction(dict(episode_id=s.episode,input_id='voice:queue',text=queued))
    s.command('robot_schedule_task',dict(episode_id=s.episode,expected_task_version=old,instruction=pending,source='qwen_realtime_current_user',user_utterance=queued,voice_input_id='voice:queue'),'schedule')
    assert s.deferred_task
    s.record_interaction(dict(episode_id=s.episode,input_id='voice:cancel',text=raw,asr_evidence=proof))
    assert s.deferred_task['dispatch_blocked_by_input']=='voice:cancel'
    assert s.deferred_task['update_utterance']==raw
    row=s.dialogue_transactions.get(s.deferred_task['deferred_id'])
    # Unit-only completion/version transition; not used as runtime goal evidence.
    s.mode='completed';s.completion_status='verified';s.version=old+1
    args=dict(episode_id=s.episode,expected_task_version=old,deferred_id=s.deferred_task['deferred_id'],
        transaction_id=row['transaction_id'],expected_transaction_revision=row['revision'],
        source='qwen_realtime_current_user',voice_input_id='voice:cancel',user_utterance=raw)
    result=s.command('robot_cancel_deferred',args,'cancel')
    assert result['status']=='deferred_cancelled'and result['executed']is False
    assert s.task_id==source and s.mode=='completed'and s.deferred_task is None
    assert s.db.execute('SELECT text FROM utterances WHERE id=?',('voice:cancel',)).fetchone()[0]==raw
    assert s.command('robot_cancel_deferred',args,'cancel')==result
    assert s.db.execute("SELECT COUNT(*) FROM events WHERE kind='deferred_update_execution_revalidated'").fetchone()[0]==1
    s.db.close()
print('Cancellation audio proof: 9 negatives; real core input fence + same-pending completion-version reconciliation + duplicate receipt; raw ASR unchanged; zero robot actions')
