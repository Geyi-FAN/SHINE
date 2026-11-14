"""T5-only, versioned aliases; keep the original T1 contract unchanged."""
import re
from t1_contract import instruction_goal as original_instruction_goal

ALIAS_VERSION = 't5-placement-alias-v2'

def placement_alias(text):
    """One explicit placement only; no inferred object, destination or suffix."""
    m=re.fullmatch(r'\s*(?:please\s+)?move\s+(?:the\s+)?(cream cheese|cheese|wine bottle|bottle|bowl|plate)\s+(on|onto|in|into|inside|to)\s+(?:the\s+)?(top of (?:the )?cabinet|stove|plate|bowl|wine rack|rack)[.!\s]*',text,re.I)
    if not m:return None
    obj,prep,dest=[x.lower() for x in m.groups()]
    obj={'cream cheese':'cheese','bottle':'wine bottle'}.get(obj,obj)
    dest=re.sub(r'^top of (?:the )?cabinet$','top of the cabinet',dest)
    dest='rack' if dest=='wine rack' else dest
    if obj=='cheese' and dest=='bowl' and prep in ('in','into','inside'):
        return 'put the cream cheese in the bowl'
    surfaces={('bowl','stove'),('bowl','plate'),('bowl','top of the cabinet'),('wine bottle','rack'),('wine bottle','top of the cabinet')}
    if prep in ('on','onto','to') and (obj,dest) in surfaces:
        return 'put the '+obj+' on '+('top of the cabinet' if dest=='top of the cabinet' else 'the '+dest)
    return None

def instruction_goal(text):
    original=original_instruction_goal(text)
    if original is not None:return original
    alias=placement_alias(text)
    return original_instruction_goal(alias) if alias else None
