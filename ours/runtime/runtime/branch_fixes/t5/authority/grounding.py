"""Closed-scene entity guard, not visual recognition or general language parsing.

Inventory comes from the actual LIBERO instance. Never replace an unsupported
noun with the nearest training template. Ambiguous parsed slots fail closed.
"""

import re

ENTITIES = {
    "bowl": ("akita_black_bowl_1", "碗", ("碗", "bowl")),
    "plate": ("plate_1", "盘子", ("盘子", "盘", "碟子", "plate")),
    "cheese": ("cream_cheese_1", "奶酪", ("奶油奶酪", "奶酪", "芝士", "cream cheese", "cheese")),
    "bottle": ("wine_bottle_1", "酒瓶", ("酒瓶", "葡萄酒瓶", "wine bottle", "bottle")),
    "cabinet": (
        "wooden_cabinet_1",
        "柜子／抽屉",
        ("抽屉", "柜子", "柜顶", "柜", "drawer", "cabinet"),
    ),
    "stove": ("flat_stove_1", "炉灶", ("炉灶", "炉子", "炉台", "灶台", "炉", "stove")),
    "rack": ("wine_rack_1", "酒架", ("酒架", "wine rack", "rack")),
    "table": ("main_table", "桌面", ("桌面", "桌子", "桌", "table")),
}
# Known nouns outside this scene also catch unparsed phrasings. General unknown
# nouns are handled by extraction below rather than mapping to a familiar noun.
ABSENT = (
    "葡萄",
    "苹果",
    "香蕉",
    "橙子",
    "杯子",
    "grapes",
    "grape",
    "apple",
    "banana",
    "orange",
    "cup",
)
ALIASES = {a: key for key, (_, _, names) in ENTITIES.items() for a in names}
PATTERN = re.compile(
    "|".join(
        re.escape(a) if not a.isascii() else r"(?<![A-Za-z0-9_])" + re.escape(a) + r"(?![A-Za-z0-9_])"
        for a in sorted([*ALIASES, *ABSENT], key=len, reverse=True)
    ),
    re.I,
)


def inventory_from_names(names):
    names = set(names)
    return {
        "source": "libero_scene_inventory",
        "scope": "scene_membership_not_current_visibility_or_pose",
        "entities": [
            {"id": key, "name": label, "instance": instance}
            for key, (instance, label, _) in ENTITIES.items()
            if instance in names
        ],
    }


def mentions(text):
    return [(m.group(), ALIASES.get(m.group().lower())) for m in PATTERN.finditer(text)]


def explicit_object_correction(text):
    """Read a noun-level rejection followed by a literal positive answer.

    'Not the bottle. Put the bowl ...' selects the bowl; 'Do not move the
    bottle' is an action prohibition and must never enter this parser.
    Returned spans are user evidence, not a generated robot instruction.
    """
    noun = r'(?:the\s+)?(?:cream cheese|wine bottle|cheese|bottle|bowl|plate)'
    match = re.match(rf'^\s*not\s+(?P<rejected>{noun})\s*[.,;!]\s*(?P<positive>.+)$', text, re.I | re.S)
    if not match:
        return None
    positive = match.group('positive').strip()
    obj = re.match(rf'^(?:(?:please\s+)?(?:put|place|move)\s+)?(?P<object>{noun})(?=\s+(?:on|onto|in|into|inside|to)\b|[.!\s]*$)', positive, re.I)
    if not obj:
        return None
    rejected = {entity for _, entity in mentions(match.group('rejected')) if entity}
    selected = {entity for _, entity in mentions(obj.group('object')) if entity}
    if len(rejected) != 1 or len(selected) != 1 or rejected == selected:
        return None
    return dict(positive_text=positive, object_text=obj.group('object'),
                object_entity=next(iter(selected)), rejected_entity=next(iter(rejected)))

def explicit_object_selection(text):
    """Bind a literal same-utterance source, never scene/history guesses.

    'Keep the bottle as the object, but put it ...' preserves a dialogue
    slot. It is distinct from 'keep the bottle at its current position'.
    """
    noun = r'(?:the\s+)?(?:cream cheese|wine bottle|cheese|bottle|bowl|plate)'
    match = re.fullmatch(rf'\s*keep\s+(?P<object>{noun})\s+as\s+(?:the\s+)?(?:object|item)\s*[,;.!]\s*(?:but\s+)?(?P<body>(?:please\s+)?(?:put|place|move)\s+(?P<source>it|{noun})\s+(?:on top of|onto|on|into|inside|in|to)\b.+)', text, re.I | re.S)
    if not match:
        return None
    literal = match.group('object')
    def canonical(value):
        value = re.sub(r'^the\s+', '', value.lower())
        return {'wine bottle': 'bottle', 'cream cheese': 'cheese'}.get(value, value)
    if match.group('source').lower() != 'it' and canonical(match.group('source')) != canonical(literal):
        return None
    content = re.sub(r'\b((?:put|place|move)\s+)it\b', lambda m: m.group(1) + literal,
                     match.group('body'), count=1, flags=re.I)
    return dict(object_text=literal, grounding_text=content, source='explicit_current_user_object_slot')

def command_content(text):
    """Resolve only explicit contrast/correction syntax in THIS user text.

    This never infers a noun from a picture, scene prior or phonetic similarity.
    The original utterance remains stored and inventory-checked in full.
    """
    selection = explicit_object_selection(text)
    if selection:
        text = selection['grounding_text']
    correction = explicit_object_correction(text)
    if correction:
        text = correction['positive_text']
    # The infinitive 'to put' in a polite request is not a destination.
    # Remove only this leading permission-neutral wrapper in the parsing copy.
    text = re.sub(r"^\s*I(?: would|'d)\s+like\s+you\s+to\s+(?=(?:put|place|move)\b)", '', text, flags=re.I)
    # 'Ask me to confirm' is a permission clause, not a second destination.
    # Canonicalize only this syntax in the grounding copy; the ORIGINAL text
    # still reaches the confirmation gate and is stored in the proposal.
    text = re.sub(r'\bask\s+me\s+to\s+confirm\b', 'ask me for confirmation', text, flags=re.I)
    text=re.sub(r'^\s*instead of\s+[^,;.]{1,60},\s*(?=(?:please\s+)?(?:put|place|move)\b)','',text,flags=re.I)
    contrast=re.search(r'\s+(?:instead of|rather than)\s+(?:the\s+)?(?:stove|plate|bowl|cabinet|cream cheese|wine bottle)[.!\s]*$',text,re.I)
    if contrast and re.search(r'\b(?:put|place|move)\b.+\b(?:on|onto|in|into|inside|to)\b',text[:contrast.start()],re.I):
        text=text[:contrast.start()]
    correction=re.search(r'\bactually\s*,?\s*i mean\s+(?:the\s+)?(cream cheese|cheese|wine bottle|bottle|bowl|plate)\s*,?\s+not\s+(?:the\s+)?(cream cheese|cheese|wine bottle|bottle|bowl|plate)[.!\s]*$',text,re.I)
    if correction and re.search(r'\b(?:move|put|place)\s+it\b',text[:correction.start()],re.I):
        prefix=text[:correction.start()].rstrip(' ,.!')
        text=re.sub(r'\b((?:move|put|place)\s+)it\b',lambda m:m.group(1)+'the '+correction.group(1),prefix,count=1,flags=re.I)
    return text


def action_clauses(text):
    # Bound noun extraction to one clause. Connectors also occur without commas
    # in final ASR; do not split words such as 酒架 or 原来的位置.
    return [
        part.strip()
        for part in re.split(
            r"[，。！？,.!?；;\n]+|然后|之后|接着|再(?=(?:请|帮我|把|将|拿|抓|放|移|摆|推|开|关|恢复))|\bthen\b|\band\s+(?=(?:put|place|move|open|close|return|release|let go|keep|leave)\b)",
            text,
            flags=re.I,
        )
        if part.strip()
    ]


def slots(text):
    """Only simple explicit manipulation noun slots; preserve uncertainty."""
    found = []
    text=command_content(text)
    # Source-location modifiers are not a placement verb. Entity preservation
    # still checks the ORIGINAL text in validate_grounding, including the rack.
    text = re.sub(r'(?:目前|现在)?放在[^，。！？,!?]+?的(?=酒瓶|碗|奶酪|盘子)', '', text)
    for clause in action_clauses(text):
        maintenance = re.match(r"^\s*(?:please\s+)?(?:keep(?:ing)?|maintain(?:ing)?|leave|leaving)\s+(.+?)(?=\s+(?:at|in|on|unchanged|unmoved|where|still)\b|[,.!?]|$)", clause, re.I)
        if maintenance:
            # The object remains mandatory evidence. State/location modifiers
            # are not a second manipulated destination (e.g. 'in its on/off state').
            noun = re.sub(r"^(?:the |a |an )", "", maintenance.group(1).strip(), flags=re.I)
            found.append(("preserved", noun))
            continue
        for pattern, role in [
            (r"把\s*(.+?)\s*(?:拿|抓|放|移|摆|推|归位|取出)", "source"),
            (r"(?:拿起|抓起|取出)\s*(.+?)(?=[，。！？,!?]|$)", "source"),
            (r"(?:放到|放在|放进|放入|摆到|移到|推到|放)\s*(.+?)(?=[，。！？,!?]|$)", "target"),
            (
                r"\b(?:put|putting|place|placing|move|moving|pick up|picking up|grab|grabbing|return|returning)\s+(.+?)(?=\s+(?:on|onto|in|into|inside|to)\b|[,.!?]|$)",
                "source",
            ),
            (r"\b(?:on|onto|in|into|inside|to)\s+(?!(?:putting|placing|moving|opening|closing)\b)(.+?)(?=[,.!?]|$)", "target"),
        ]:
            for m in re.finditer(pattern, clause, re.I):
                noun = m.group(1).strip(" ，,")
                if role == 'source':
                    noun = re.split(r'\s+from\s+', noun, flags=re.I)[0]
                    # "put it back where it was ..." has one object slot.
                    # Historical-location wording is a modifier, not its name.
                    noun = re.split(r'\s+back\b', noun, maxsplit=1, flags=re.I)[0]
                    noun = re.sub(r'\s+(?:first|now|stably)$', '', noun, flags=re.I)
                if role == 'target' and re.fullmatch(
                    r"(?:(?:its|their|the)\s+)?(?:(?:episode[- ]start|initial|original|starting)\s+(?:position|location|place|spot)(?:\s+(?:in|of|for)\s+(?:this|the)\s+episode)?|(?:position|location|place|spot)\s+at\s+the\s+(?:beginning|start)\s+of\s+(?:(?:the|its)\s+source\s+task|this\s+episode|the\s+episode))",
                    noun, re.I):
                    noun = '原位'
                if role == 'target' and re.fullmatch(
                    r"(?:(?:its|their|the)\s+)?(?:position|location|place)\s+at\s+(?:the\s+)?(?:beginning|start)\s+of\s+(?:(?:the|this)\s+)?(?:source task|episode)", noun, re.I):
                    noun = '原位'
                if noun == "去":
                    noun = "那里"
                if noun == "回原位":
                    noun = "原位"
                noun = re.sub(
                    r"^(?:(?:桌面|桌子|桌)上(?:的)?|(?:the |a |an ))", "", noun, flags=re.I
                )
                noun = re.sub(
                    r"(?:上面|里面|里边|上边|中间|内|上|一下|去|吧|边)$", "", noun
                ).strip()
                found.append((role, noun))
    return found


def validate_grounding(utterance, instruction, inventory, referenced=False):
    if not inventory:
        raise ValueError(
            "scene_inventory_unavailable: 暂时无法核实场景物体，请稍后再试；未下发新动作。"
        )
    available = {e["id"] for e in inventory["entities"]}
    source_mentions = mentions(utterance)
    output_mentions = mentions(instruction)
    for noun, entity in source_mentions + output_mentions:
        if entity is None or entity not in available:
            raise ValueError(
                f"object_not_in_scene: 当前仿真场景清单没有“{noun}”，无法执行；不得换成其他物体。"
            )
    # References to the table describe the scene rather than the task target.
    requested = {entity for _, entity in mentions(command_content(utterance))} - {"table"}
    actual = {entity for _, entity in output_mentions} - {"table"}
    correction = explicit_object_correction(utterance)
    if correction and correction['rejected_entity'] in actual - requested:
        raise ValueError('instruction_entity_mismatch: 不得把本轮明确否定的候选对象加入执行任务。')
    if actual and not requested and not referenced:
        raise ValueError(
            "object_reference_unresolved: 原话未能明确对应场景物体，请澄清或查询本轮记忆；不得猜测替代任务。"
        )
    if requested - actual:
        raise ValueError(
            "instruction_entity_mismatch: 下发指令遗漏或替换了用户指定物体；请保留原意，不得换任务。"
        )
    for role, noun in slots(utterance):
        entities = mentions(noun)
        unresolved_code = 'destination_reference_unresolved' if role == 'target' else 'object_reference_unresolved'
        unresolved_label = '目的地' if role == 'target' else '场景物体'
        if not referenced and re.fullmatch(r'(?:它|这个|那个|这里|那里|那个地方|这个地方|it|there)', noun, re.I):
            raise ValueError(unresolved_code + ': 请先明确操作对象或目的地，不得根据场景猜测。')
        if not entities and not re.fullmatch(
            r"(?:它|这个|那个|这里|那里|那个地方|这个地方|原处|原位|原来的位置|刚才的位置|it|there)", noun, re.I
        ):
            raise ValueError(
                f"{unresolved_code}: 无法核实“{noun[:50]}”对应的{unresolved_label}，请澄清；未下发新动作。"
            )
        # For simple requests, check roles as well as object presence. Compound
        # constraints retain their full text and are not flattened here.
        if len(slots(utterance)) == 2 and entities:
            targets = [mentions(n) for r, n in slots(instruction) if r == role]
            if len(targets) == 1 and {e for _, e in entities} != {e for _, e in targets[0]}:
                raise ValueError(
                    "instruction_entity_mismatch: 操作物体或目的地与原话不一致；不得擅自替换。"
                )


def validate_pronoun_source(utterance, instruction, memory_instructions):
    """An actual same-episode task reference must ground the manipulated object."""
    if not any(role=='source' and re.fullmatch(r'它|这个|那个|it',noun,re.I) for role,noun in slots(utterance)):
        return
    actors={e for text in memory_instructions for role,noun in slots(text) if role=='source' for _,e in mentions(noun) if e}
    requested=[noun for role,noun in slots(utterance) if role=='source']
    proposed=[noun for role,noun in slots(instruction) if role=='source']
    # Bind the pronoun's corresponding manipulation, not every subsequent
    # source object in a compound instruction (return bowl THEN move cheese).
    pronouns=[i for i,noun in enumerate(requested) if re.fullmatch(r'它|这个|那个|it',noun,re.I)]
    candidates=[{e for _,e in mentions(proposed[i]) if e} if i<len(proposed) else set() for i in pronouns]
    if len(actors)!=1 or not candidates or any(candidate!=actors for candidate in candidates):
        raise ValueError('object_reference_unresolved: 历史记录不能唯一支持当前操作对象，请先明确指代。')
