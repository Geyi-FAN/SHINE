"""Keep the full Task as a goal; current perception stays in observations/points."""
import re
ADDENDUM='''\nTASK/OBSERVATION SEPARATION (priority): The execution_task/Task line must preserve the requested goal and may not append the destination bowl's observed support (such as currently on the table/stove/cabinet) unless the user explicitly supplied that descriptor. Current perception may be uncertain or become stale during execution. Keep it in current_image_observation and the typed current-bowl point; do not turn it into a new textual physical claim. This rule supersedes the earlier optional support descriptor example. You still write the complete task and current subgoal yourself; never omit requested return, order, release, keep or leave clauses.'''
def extra_errors(raw,text):
    original=raw.lower();candidate=text.lower()
    descriptor=r'\bbowl\b(?:\s+(?:that|which|is|currently|located|sitting|resting|standing))*\s+(?:on|inside|in)\s+(?:the\s+)?(?:top of (?:the )?)?(table|stove|cabinet|plate|drawer)\b'
    locations=re.findall(descriptor,candidate)
    added=bool(locations)
    original_locations=set(re.findall(descriptor,original))
    original_descriptor=bool(locations)and set(locations)<=original_locations
    return ['Do not add an unrequested support/location descriptor to the destination bowl in Task; use the user goal and current point.']if added and not original_descriptor else[]
def install():
    import task_language
    base=task_language.wording_errors
    task_language.SYSTEM+=ADDENDUM
    task_language.wording_errors=lambda raw,text:base(raw,text)+extra_errors(raw,text)
