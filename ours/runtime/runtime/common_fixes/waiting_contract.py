"""Pre-dispatch candidate contract. Structure is evidence, not model authority."""

import re
from grounding import mentions, slots
from waiting_language import english_waiting_candidate, pending_update_candidate, named_pending_cancel


def deferred_validation_text(raw, candidate, predecessor, instruction):
    """Bind an explicit completion condition to the actual predecessor.

    This is validation-only coreference, never a generated plan or GT answer.
    The original raw utterance remains in the queue's provenance.
    """
    match=re.match(r'^\s*(?:after|once|when)\s+(.+?)[,;.!]',raw,re.I)
    if not match:return candidate
    condition=match.group(1)
    subject=re.match(r'(?:the\s+)?(.+?)\s+(?:is|are|has been|have been)\b',condition,re.I)
    if not subject:return candidate
    required={e for _,e in mentions(condition) if e}
    if not required:return candidate
    previous={e for _,e in mentions(predecessor) if e}
    if not required<=previous:
        raise ValueError('deferred_precondition_mismatch: 等待条件与当前任务不一致，请明确等待哪个操作。')
    subjects={e for _,e in mentions(subject.group(1)) if e}
    if len(subjects)!=1:return candidate
    entity=next(iter(subjects))
    label={'bowl':'bowl','cheese':'cream cheese','bottle':'wine bottle','plate':'plate','cabinet':'drawer','stove':'stove','rack':'wine rack'}.get(entity)
    if label and re.search(r'\b(?:in|into|on|onto|to)\s+it\b',candidate,re.I):
        targets=[{e for _,e in mentions(n) if e} for role,n in slots(instruction) if role=='target']
        if not targets or entity not in targets[0]:
            raise ValueError('deferred_pronoun_target_mismatch: 后续任务目的地没有保留等待条件中的明确对象。')
        return re.sub(r'\b(in|into|on|onto|to)\s+it\b',lambda m:m.group(1)+' the '+label,candidate,flags=re.I)
    return candidate


def deferred_request(text, replacing=None):
    """Only explicit completion-relative requests authorize a future start."""
    if re.search(r'''["“”「」]|\b(?:unless|not|never|don't|do not|right now|immediately)\b''',text,re.I):return None
    explicit=english_waiting_candidate(text)
    if explicit:return explicit
    if replacing:
        update=pending_update_candidate(text)
        if update:return update
    if re.search(r'[?？“”「」]|如果|假如|假设|不要等|不用等|别等|不必等|\b(?:if|suppose|do not wait|don\x27t wait)\b',text,re.I):
        return None
    match = re.match(
        r"^\s*(?:请)?等(?:你)?(?:当前|这个|现在的)?(?:任务|指令)?(?:做完|完成|结束)(?:以后|之后|后)?[，,\s]*(?:再|然后|改成|去)(.+)$",
        text,
    )
    if not match:
        match = re.match(
            r'^\s*(?:(?:嗯|哦|好|好的|请|你|帮我|先)[，,\s]*)*'
            r'(?:完成|做完|结束)(?:当前|这个|现在的)(?:指令|任务)'
            r'(?:之后|以后|后)[，,\s]*(?:然后|接着|再|去|改成)?\s*(.+)$',text,re.S)
    if not match:
        match = re.match(
            r"^\s*(?:after|once|when)\s+(?:this|the current|current) task\s+(?:is\s+)?(?:finishes|completes|finished|completed|done)[,\s]+(.+)$", text, re.I
        )
    if not match:
        match = re.match(r'^\s*(?:after|once|when)\s+you\s+(?:finish|complete)\s+(?:this|the current)\s+task[,\s]+(.+)$',text,re.I)
    if not match:
        match = re.match(r'^\s*(?:after|once|when)\s+(?:the\s+)?(?:bowl|cheese|wine bottle|drawer)\s+task\s+(?:is\s+)?(?:finished|completed|done)[,\s]+(.+)$',text,re.I)
    if not match:
        # Explicit physical completion condition; no arbitrary time/event queue.
        conditional = re.match(r'^\s*(?:after|once|when)\s+(.+?)[,;]\s*(?:then\s+)?(.+)$',text,re.I)
        if conditional:
            condition=conditional.group(1)
            entities={e for _,e in mentions(condition) if e}
            physical=bool(re.search(r'\b(?:is|are|has been|have been)\b.{0,100}\b(?:on|in|inside|released|placed|open|opened|closed|shut|stable)\b',condition,re.I))
            if entities and physical:
                candidate=conditional.group(2).strip()
                if re.match(r'(?:please\s+)?(?:put|place|move|open|close|return|turn|pick|grab)\b',candidate,re.I):
                    return candidate
    if not match and replacing:
        match = re.match(r'^\s*(?:请)?(?:把)?(?:排队|等待|等会儿?|稍后)(?:的)?(?:那个|这个)?任务(?:替换为|替换成|改为|改成)[，,\s]*(.+)$', text)
    if not match and replacing:
        # "cue/queue task" is a bounded ASR variant, only in an explicit
        # replacement of an already-existing deferred slot. Never rewrite nouns.
        match=re.match(r'^\s*(?:please\s+)?(?:replace|change)\s+(?:the\s+)?(?:queued|queue|cue|waiting|pending)(?:\s+(?:bowl|cheese|wine|bottle)){0,3}\s+(?:task|job)\s+(?:with|to)\s+(.+?)(?:[.!]\s*(?:please\s+)?(?:continue|finish|complete)\s+(?:the\s+)?current\s+task(?:\s+first)?[.!]*)?$',text,re.I)
    if not match and replacing:
        # Context resolution, not spelling correction: an explicit replacement
        # plus "continue CURRENT task FIRST" can only update the single pending
        # slot. An unknown ASR adjective never becomes a new object/location.
        # Explicit current/running/active targets remain ambiguous and rejected.
        match=re.match(r'^\s*(?:please\s+)?(?:replace|change)\s+(?:the\s+)?(?:(?!(?:current|running|active)\b)[a-z]+\s+){0,4}(?:task|job)\s+(?:with|to)\s+(.+?)[.!;]\s*(?:please\s+)?(?:continue|finish|complete)\s+(?:the\s+)?current\s+task(?:\s+first)?[.!\s]*$',text,re.I)
    candidate = match.group(1).strip() if match else None
    if candidate and replacing:
        verbs={'putting':'put','placing':'place','moving':'move','opening':'open','closing':'close'}
        candidate=re.sub(r'^(putting|placing|moving|opening|closing)\b',lambda m:verbs[m.group(1).lower()],candidate,flags=re.I)
    if candidate and replacing:
        # A bounded cancellation of the OLD goal is not a new physical invariant.
        parts = re.fullmatch(r'(.+?)[，,]\s*不(?:再)?(?:放|执行|做)(.+?)了[。.!！]?\s*', candidate)
        if parts:
            cancelled = {e for _,e in mentions(parts.group(2)) if e}
            old = {e for _,e in mentions(replacing) if e}
            new = {e for _,e in mentions(parts.group(1)) if e}
            if cancelled and cancelled <= old and not cancelled & new:
                candidate = parts.group(1).strip()
    return candidate


def deferred_update_request(text, pending=None):
    if pending and (named_pending_cancel(text,pending) or pending_update_candidate(text)):return True
    # A question/quotation/negated cancellation cannot invalidate a queued task.
    if re.search(r'[?？“”「」"\']|如果|假如|是否|不要取消|别取消|不取消|不要替换|别改|不要改|\b(?:if|whether|do not|don\x27t)\b', text, re.I):
        return False
    return bool(re.search(r'取消.{0,20}(?:等会|等待|稍后|排队)|(?:等会|等待|稍后|排队).{0,20}(?:取消|改成|改为|替换)',text)
        or (deferred_request(text) and re.search(r'改成|改为|替换',text))
        or re.search(r'\b(?:cancel|replace|change)\b.{0,45}\b(?:queued|queue|cue|waiting|pending|next)(?:\s+(?:bowl|cheese|wine|bottle)){0,3}\s+(?:task|job)\b',text,re.I)
        or (re.match(r'^\s*(?:please\s+)?(?:replace|change)\b',text,re.I)
            and deferred_request(text,replacing='existing_pending_slot')))

