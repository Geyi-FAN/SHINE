"""Extract explicit completion-relative English. Never generate the next task."""
import re

ACTION = r'(?:then\s+)?(?:please\s+)?(?:put|place|move|push|open|close|return|turn|pick|grab)\b'
DONE = re.compile(r"(?:(?:this|the current|current|the|that)\s+task\s+(?:is\s+)?(?:finishes|completes|finished|completed|done)|(?:this|that)(?:'s| is| has been)\s+(?:done|finished|completed)|you(?:'re| are)\s+(?:done|finished)|you\s+(?:finish|complete)\s+(?:this|the current)\s+task|(?:the\s+)?(?:bowl|cheese|wine bottle|drawer)\s+task\s+(?:is\s+)?(?:finished|completed|done))",re.I)

def english_waiting_candidate(raw):
    text=raw.strip().replace('’',"'").replace('‘',"'")
    if re.search(r'''[?？"“”「」]|\b(?:if|suppose|unless|not|never|don't|do not|right now|immediately)\b''',text,re.I):return None
    prefix=re.match(r'^(?:after|once|when)\s+(.+?)[,;.!]\s*(.+)$',text,re.I)
    if prefix:
        condition,candidate=(s.strip()for s in prefix.groups())
        physical=(re.fullmatch(r'(?:the\s+)?(?:bowl|cheese|(?:wine\s+)?bottle|drawer|stove|plate)\s+(?:is|are|has been|have been)\s+.{0,100}',condition,re.I)
                  and re.search(r'\b(?:down|on|in|inside|released|placed|open|opened|closed|shut|stable)\b',condition,re.I))
        if (DONE.fullmatch(condition)or physical)and re.match(ACTION,candidate,re.I):return re.sub(r'^then\s+','',candidate,flags=re.I)
    suffix=re.match(r'^(.+?)\s+(?:when|once|after)\s+(.+?)[.!]*$',text,re.I)
    if suffix and DONE.fullmatch(suffix[2].strip())and re.match(ACTION,suffix[1],re.I):return suffix[1].strip()
    task=re.match(r'^(?:after|once|when)\s+((?:this|the current|current) task\s+(?:is\s+)?(?:finishes|completes|finished|completed|done))\s+(.+)$',text,re.I)
    if task and DONE.fullmatch(task[1])and re.match(ACTION,task[2],re.I):return task[2].strip()

def pending_update_candidate(text):
    """Only called with an existing pending slot by deferred_request."""
    text=text.strip()
    if re.search(r'''[?？"“”「」]|\b(?:if|suppose|not|never|don't|do not|now|immediately)\b''',text,re.I):return None
    prefix=re.fullmatch(r'for later[,;.!]?\s+(.+?)\s+instead[.!]*',text,re.I)
    suffix=re.fullmatch(r'(.+?)\s+(?:afterward|afterwards|next)[,;.!]?\s+instead[.!]*',text,re.I)
    match=prefix or suffix
    return match[1].strip()if match and re.match(ACTION,match[1],re.I)else None

def named_pending_cancel(text,pending):
    """A named skip/cancel is bound to the real pending goal, not the active one."""
    if not pending or re.search(r'''[?？"“”「」]|\b(?:if|suppose|not|never|don't|do not)\b''',text,re.I):return False
    match=re.fullmatch(r'(?:please\s+)?(?:cancel|skip)\s+(?:the\s+)?(.+?)(?:\s+task)?[.!](?:\s*(?:keep going|carry on|keep working(?: on the (?:bottle|bowl))?|keep going with the bottle|finish what you(?:\x27re| are) doing)[.!]*)?',text.strip(),re.I)
    if not match:return False
    from grounding import mentions
    requested={e for _,e in mentions(match[1])if e};known={e for _,e in mentions(pending)if e}
    return bool(requested and requested<=known)
