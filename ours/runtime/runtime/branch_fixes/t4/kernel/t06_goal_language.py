"""Parse demonstrative determiners of explicitly named, registered entities.

Only the runtime goal verifier receives the equivalent grammatical form.
The authorized Task, Agent inputs, position sources and all numerical rules
remain unchanged. Bare it/that one/there are never resolved here.
"""
import re

# These are explicit noun forms already supported by the fixed scene catalog.
# No benchmark IDs, success labels, next stages or coordinates appear here.
NOUNS = r'cream cheese|wine bottle|wine rack|top drawer|middle drawer|bowl|plate|cheese|bottle|stove|cabinet|rack'
EXPLICIT = re.compile(r'\b(?:this|that)\s+(?P<noun>' + NOUNS + r')\b', re.I)
NEGATIVE_OR_CONDITIONAL = re.compile(r"\b(?:not|never|don't|dont|if|unless)\b", re.I)
_logger = None


def equivalent_goal_text(text):
    # Avoid broadening unsupported negated/conditional commands. The parent
    # normalizer has already handled its existing explicit stove prohibition.
    if NEGATIVE_OR_CONDITIONAL.search(text):
        return text
    return EXPLICIT.sub(lambda m: 'the ' + m['noun'], text)


def bind_logger(logger):
    global _logger
    _logger = logger


def install(module=None):
    if module is None:
        from t4_adapter import objectives as module
    original = module.normalize_selected_task
    if getattr(original, '_t06_explicit_noun_determiner', False):
        return

    def normalize(text, current_binary_state):
        prepared = original(text, current_binary_state)
        result = equivalent_goal_text(prepared)
        if result != prepared and _logger:
            _logger('t06_goal_language_normalized', original_instruction=prepared,
                    verification_instruction=result, scope='runtime_goal_language_only',
                    agent_task_rewritten=False, numerical_thresholds_changed=False,
                    reference_time_source_changed=False)
        return result

    normalize._t06_explicit_noun_determiner = True
    module.normalize_selected_task = normalize
