"""Conservative exact language normalization; never fuzzy-drop a clause."""

import json
from pathlib import Path
import re

CATALOG = json.loads(
    (Path(__file__).resolve().parents[1] / "configs/instruction_catalog.json").read_text()
)


def key(text):
    return re.sub(r"\s+", " ", text.strip().lower().rstrip(".!?"))


BY_KEY = {key(e["instruction"]): e for e in CATALOG["entries"]}
ALIASES = {
    "place the bowl on the plate": "put the bowl on the plate",
    "place the bowl onto the plate": "put the bowl on the plate",
    "put the bowl onto the plate": "put the bowl on the plate",
    "put the bowl in the plate": "put the bowl on the plate",
    "pick up the bowl and place it onto the plate": "put the bowl on the plate",
    "pick up the bowl and place it on the plate": "put the bowl on the plate",
    "open the middle drawer": "open the middle drawer of the cabinet",
}


def normalize_instruction(text, previous=""):
    requested = text.strip()
    candidate = key(requested)
    # Object identity commentary is not a persistent physical-state condition.
    # Remove it only for an exact repeated source and a known complete task;
    # the raw requested text remains in task/proposal provenance.
    identity = re.fullmatch(
        r'(?P<task>(?:put|place|move) (?:the )?'
        r'(?P<object>cream cheese|wine bottle|cheese|bottle|bowl|plate) '
        r'(?:on top of|onto|on|into|inside|in|to) (?:the )?'
        r'(?:wine rack|rack|cabinet|stove|plate|bowl)), '
        r'keeping (?:the )?(?P=object) as the object', candidate,
    )
    if identity:
        physical = ALIASES.get(identity['task'], identity['task'])
        if physical in BY_KEY:
            return BY_KEY[physical]['instruction'], 'same_source_identity_annotation'
    if candidate in BY_KEY:
        return BY_KEY[candidate]["instruction"], "exact_training_template"
    candidate = ALIASES.get(candidate, candidate)
    # Resolve only a uniquely named drawer in the current instruction. Never guess.
    match = re.fullmatch(
        r"(?:close|shut) the (?:(middle|top) )?drawer(?: of the cabinet)?(?: first)?,? then (.+)",
        candidate,
    )
    if match:
        drawer, tail = match.groups()
        if drawer is None:
            refs = set(re.findall(r"\b(middle|top) drawer\b", key(previous)))
            if len(refs) == 1:
                drawer = next(iter(refs))
        if drawer:
            tail = ALIASES.get(tail, tail)
            trial = f"close the {drawer} drawer first, then {tail}"
            if trial in BY_KEY:
                candidate = trial
    if candidate in BY_KEY:
        return BY_KEY[candidate]["instruction"], "equivalent_training_template"
    return requested, "unmatched_preserved_all_constraints"
