"""Narrow, full-utterance robot control semantics; no physical task generation."""
import re

def control_intent(text):
    t=str(text).strip().lower().replace('’', "'")
    if not t:return None
    # A quoted/hypothetical/negative command never authorizes immediate control.
    if re.search(r"\b(?:don't|do not|never|must not)\s+(?:stop|pause|cancel|resume)\b|不要停|别停|不要暂停|不能停",t):return 'protected'
    if re.search(r'\b(?:what|why|means?|said|says|suppose|if|unless)\b|如果|假如|是否|什么意思',t) and re.search(r'stop|pause|cancel|暂停|停止|取消',t):return 'protected'
    # A separate leading Stop sentence is immediate; a later keep-until clause
    # belongs to the manipulation, not to the timing of Stop.
    if re.match(r'^(?:please\s+)?(?:stop|pause)(?:\s+(?:the\s+)?(?:robot|arm|task))?[,;:，；：.!。！]+\s*(?:(?:first|then|please|instead)\s*[,，:]?\s+)*(?:put|place|return|open|close|turn|push|move|take)\b',t):return None
    if re.search(r'\b(?:stop|pause)\b.*\b(?:after|once|when|until)\b|\b(?:after|once|when)\b.*\b(?:stop|pause)\b|完成.*(?:后|再).*(?:停|暂停)',t):return 'deferred_stop'
    if re.fullmatch(r'(?:please\s+)?(?:cancel|remove|delete)\s+(?:(?:the|my|this)\s+)?(?:waiting|queued|deferred)\s+task[.!\s]*|(?:请)?取消(?:等待|排队|后续)任务[。！\s]*',t):return 'cancel_waiting'
    if re.fullmatch(r'(?:please\s+)?(?:cancel|abort)\s+(?:(?:the|my|this|current)\s+)*(?:task|job|execution)[.!\s]*|(?:请)?取消(?:当前)?任务[。！\s]*',t):return 'cancel'
    prefix=r'(?:(?:please|hey|okay|ok)\s*[,!.]?\s*)?'
    pause=r'(?:(?:hold\s+on|wait\s+(?:a\s+)?(?:moment|second))\s*[,!.]?\s*)?(?:please\s+)?(?:stop|pause)(?:\s+(?:the\s+)?(?:robot|arm|task|motion|execution))?(?:\s+please)?[.!\s]*'
    if re.fullmatch(prefix+pause,t) or re.fullmatch(r'(?:please\s+)?hold\s+on[.!\s]*',t):return 'pause'
    if re.fullmatch(r'(?:can|could|would)\s+you\s+(?:please\s+)?(?:stop|pause)(?:\s+the\s+(?:robot|arm|task))?[?.!\s]*',t):return 'pause'
    if re.fullmatch(r'(?:请你?|麻烦你)?(?:现在|先)?(?:暂停|停下|停止|停一下|别动)(?:一下|当前任务|机械臂|任务)?[。！\s]*',t):return 'pause'
    if re.fullmatch(r'(?:please\s+)?(?:resume|continue)(?:\s+(?:the\s+)?(?:same|current)\s+task|\s+the\s+task\s+you\s+were\s+doing)?[.!\s]*|go\s+ahead\s+and\s+carry\s+on\s+with\s+the\s+task\s+you\s+paused[.!\s]*|(?:请)?继续(?:刚才的|当前|原来)?任务[。！\s]*',t):return 'resume'
    return None

def allowed_control_tool(intent,name):
    controls={'robot_pause','robot_resume','robot_cancel_task'}
    expected={'pause':'robot_pause','resume':'robot_resume','cancel':'robot_cancel_task','cancel_waiting':'robot_cancel_deferred'}
    if intent in expected:
        return name not in controls|{'robot_cancel_deferred'} or name==expected[intent]
    if intent in ('protected','deferred_stop') and name in controls:return False
    return True
