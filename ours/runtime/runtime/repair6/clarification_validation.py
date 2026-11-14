"""Reject an unfinished transport goal; never invent a destination or plan."""
import re
BARE_TRANSPORT=re.compile(r'\s*(?:please\s+)?(?:move|put|place)\s+(?:the\s+)?(?:cream cheese|wine bottle|cheese|bottle|bowl|plate|object|it)[.!\s]*',re.I)
def destination_missing(instruction):
    return isinstance(instruction,str) and bool(BARE_TRANSPORT.fullmatch(instruction))
