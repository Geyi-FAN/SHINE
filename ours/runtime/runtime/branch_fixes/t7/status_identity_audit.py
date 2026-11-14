"""Audit actual public schema; absent optional keys are not stale identities."""
import json
from pathlib import Path

def audit(directory):
    result=dict(samples=0,wrong_task_metadata=0,invalid_completion=0,
                verified_samples=0,verified_without_optional_episode_version=0)
    path=Path(directory)/'client/system_events.jsonl'
    if not path.exists():return result
    for line in path.open():
        event=json.loads(line)
        if event.get('type')!='system.status':continue
        state=event['status'];execution=state.get('agent_execution')or{}
        result['samples']+=1
        if execution.get('task_id')and execution['task_id']!=state.get('task_id'):
            result['wrong_task_metadata']+=1
        if not execution.get('completion_current_verified'):continue
        result['verified_samples']+=1
        if any(key not in execution for key in ['episode_id','task_version']):
            result['verified_without_optional_episode_version']+=1
        valid=(bool(state.get('task_id')) and
               execution.get('task_id')==state['task_id'] and
               'semantic_revision'in execution and
               execution['semantic_revision']==state.get('task_intent_revision') and
               state.get('state')=='completed' and state.get('completion')=='verified' and
               execution.get('phase')=='completed')
        for key in ['episode_id','task_version']:
            if key in execution and execution[key]!=state.get(key):valid=False
        if not valid:result['invalid_completion']+=1
    return result
