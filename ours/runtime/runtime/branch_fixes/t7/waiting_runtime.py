"""T7 English admission only; existing IDs, versions, pending transaction checks stay."""
import sys

def install(core):
    import task_contract
    import waiting_contract as fixed
    holder={}
    original_init=core.RobotState.__init__
    def initialize(state,*a,**kw):
        original_init(state,*a,**kw)
        holder['state']=state
    core.RobotState.__init__=initialize
    if hasattr(core.RobotState,'record_interaction'):
        original_record=core.RobotState.record_interaction
        def record(state,body):
            # Original recording owns episode/input/duplicate checks and the
            # atomic handoff fence. Supply THIS input's evidence only in scope.
            with state.lock:
                holder['recording_body']=body
                try:
                    # Validate and record raw text FIRST; stale/conflicting input
                    # cannot install a fence. Only a new authenticated input may
                    # ask this question. No cancellation is authorized here.
                    result=original_record(state,body)
                    if (not result.get('duplicate') and type(body.get('task_version')) is int
                            and body['task_version']==state.version):
                        from cancel_clarification import ambiguous_question
                        question=ambiguous_question(state,body.get('text'),body.get('input_id'))
                        from cancel_audio_evidence import verified_cancel
                        if verified_cancel(body.get('text'),body.get('asr_evidence'),
                                           (state.deferred_task or {}).get('instruction')):
                            question=None
                        if question:
                            state._block_deferred_update(body['input_id'],body['text'])
                            state.deferred_task['cancel_clarification']=question
                            state.event('pending_cancel_clarification_required',question)
                            state.db.commit()
                    return result
                finally:holder.pop('recording_body',None)
        core.RobotState.record_interaction=record
    def update(text,pending=None):
        if pending is None:
            state=holder.get('state')
            slot=getattr(state,'deferred_task',None)or{}
            pending=slot.get('instruction')
        state=holder.get('state')
        from cancel_clarification import direct_named_cancel
        if direct_named_cancel(text,pending,getattr(state,'instruction','')):return True
        if fixed.deferred_update_request(text,pending):return True
        state=holder.get('state');body=holder.get('recording_body')
        evidence=body if body is not None else getattr(state,'last_interaction',None)
        if not isinstance(evidence,dict)or evidence.get('text')!=text:return False
        from cancel_audio_evidence import verified_cancel
        return bool(verified_cancel(text,evidence.get('asr_evidence'),pending))
    for name,replacement in [('deferred_request',fixed.deferred_request),('deferred_validation_text',fixed.deferred_validation_text),('deferred_update_request',update)]:
        original=getattr(task_contract,name)
        for module in list(sys.modules.values()):
            if module is not None and getattr(module,name,None)is original:setattr(module,name,replacement)
