"""A previous task's plan/complete badge never describes its successor."""
def bind(snapshot):
 result=dict(snapshot);execution=result.get('agent_execution')
 if not result.get('task_id'):
  result['agent_execution']=None;return result
 if execution and execution.get('task_id')and(execution['task_id']!=result['task_id']or execution.get('semantic_revision',result.get('task_intent_revision'))!=result.get('task_intent_revision')):
  result['agent_execution']=dict(phase='planning',task_id=result['task_id'],semantic_revision=result.get('task_intent_revision'),completion_current_verified=False,source='current_task_pending_activation')
 return result
