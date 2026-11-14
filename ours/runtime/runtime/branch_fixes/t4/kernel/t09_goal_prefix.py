"""Normalize an explicit leading maintenance noun before clause splitting.

The original Task, plan, points, temporal anchor and physical checks are not
rewritten. Fixes composition: earlier demonstrative support ran AFTER the
parent's 'keep X; action Y' split, so 'leave that bowl ... and put ...' failed.
No bare reference is resolved and no extra operation or condition is removed.
"""
from functools import wraps
import re
from t06_goal_language import NOUNS, NEGATIVE_OR_CONDITIONAL

VERSION = 'keep-prefix-determiner-order-v1'
LEADING = re.compile(r'^(?P<verb>keep(?:ing)?|leave|leaving|maintain(?:ing)?|preserv(?:e|ing))(?P<space>\s+)(?:this|that)(?P<gap>\s+)(?P<noun>'+NOUNS+r')\b',re.I)
_logger = None

def leading_explicit_noun(text):
    if NEGATIVE_OR_CONDITIONAL.search(text):
        return text
    return LEADING.sub(lambda m:m['verb']+m['space']+'the'+m['gap']+m['noun'],text,count=1)

def bind_logger(logger):
    global _logger
    _logger=logger

def install(module=None):
    if module is None:
        from t4_adapter import objectives as module
    original=module.normalize_selected_task
    if getattr(original,'_t09_prefix_determiner',False):
        return
    @wraps(original)
    def normalize(text,current_binary_state):
        prepared=leading_explicit_noun(text)
        result=original(prepared,current_binary_state)
        if prepared!=text and _logger:
            _logger('t09_goal_prefix_normalized',version=VERSION,
                original_instruction=text,verification_instruction=result,
                scope='runtime_verifier_grammar_only',agent_task_rewritten=False,
                position_reference_unchanged=True,numerical_thresholds_changed=False)
        return result
    normalize._t09_prefix_determiner=True
    module.normalize_selected_task=normalize
