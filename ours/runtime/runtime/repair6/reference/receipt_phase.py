"""Authoritative operation receipts bridge sub-tick physical-sample gaps.

A model's text is not evidence. Require an actual accepted resume for the same
subject, no intervening stop/new task, and real later running-world evidence.
"""
def resume_receipt_consistent(claim_time,task_id,tool_events,public_events,ticks):
    receipts=[e for e in tool_events if e.get('kind')=='voice_tool_receipt'and e.get('tool')=='robot_resume'
              and e['time']<=claim_time and e.get('receipt',{}).get('status')=='accepted'
              and e['receipt'].get('state')=='running'and e['receipt'].get('task_id')==task_id]
    if not receipts:return False
    receipt=receipts[-1]
    forbidden={'task_paused','task_cancelled','task_superseded','task_completed','task_budget_exhausted','task_needs_review','task_instruction'}
    if any(receipt['time']<e['time']<=claim_time and e.get('kind')in forbidden for e in public_events):return False
    if not any(e.get('kind')=='task_resumed'and e['time']<=claim_time for e in public_events):return False
    return any(t.get('task_id')==task_id and t.get('physics_tick')and t['mode']=='running'and t['time']>=receipt['time']for t in ticks)
