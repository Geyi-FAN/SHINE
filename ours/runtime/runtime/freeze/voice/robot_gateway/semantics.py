"""Conservative, auditable pre-dispatch checks for the fixed LIBERO task language.

Unsupported language is uncertainty, never a license to discard a constraint.
This checks both languages without using model-provided semantic labels as truth.
"""
import re
from grounding import mentions, slots, validate_grounding, command_content, explicit_object_selection
YES = {'好', '好的', '对', '是', '是的', '确认', '确认执行', '就这样', '可以', 'yes', 'confirm', 'okay', 'ok'}
NO = {'不', '不是', '不对', '不要', '不用', '算了', '取消确认', '拒绝', 'no', 'reject'}

def compact(text):
    return re.sub('[\\s，。！？、,.!?；;]+', '', text.lower())

def matching_task_confirmation(text, expected_instruction):
    """A full affirmative confirms only the identical live bounded operation.

    No live proposal, extra actions/constraints, or a different source/target
    means no match. This function cannot invent a plan or authorize by itself.
    """
    if not isinstance(expected_instruction, str):
        return False
    answer = re.fullmatch(r'\s*yes\s*[,.!:;，。；：]?\s+(?P<task>.+)', text, re.I)
    if not answer:
        return False
    source = r'(?:the\s+)?(?:cream cheese|wine bottle|cheese|bottle|bowl|plate)'
    target = r'(?:the\s+)?(?:wine rack|rack|cabinet|stove|plate|bowl)'
    # A proposal may repeat the unchanged object after an object/destination
    # correction. Only this identity tautology is removable; a physical keep
    # constraint, another action, or a different repeated object is not.
    pattern = rf'\s*(?:please\s+)?(?:put|place|move)\s+(?P<source>{source})\s+(?P<relation>on top of|onto|on|into|inside|in|to)\s+(?P<target>{target})(?:\s*,\s*keeping\s+(?P<kept_source>{source})\s+as\s+the\s+object)?[.!\s]*'
    def signature(value):
        drawer = re.fullmatch(
            r'\s*(?:please\s+)?(?P<action>open|close)\s+(?:the\s+)?'
            r'(?P<level>middle|top|upper|bottom|lower)\s+drawer'
            r'(?:\s+(?:of|in)\s+(?:the\s+)?cabinet)?[.!\s]*', value, re.I,
        )
        if drawer:
            level = {'upper': 'top', 'lower': 'bottom'}.get(
                drawer.group('level').lower(), drawer.group('level').lower(),
            )
            return 'drawer', drawer.group('action').lower(), level
        match = re.fullmatch(pattern, value, re.I)
        if not match:
            return None
        entity = lambda name: tuple(sorted({e for _, e in mentions(match.group(name)) if e}))
        if match.group('kept_source') and entity('kept_source') != entity('source'):
            return None
        relation = match.group('relation').lower()
        family = 'surface' if relation in ('on', 'onto', 'on top of') else 'containment' if relation in ('in', 'into', 'inside') else relation
        return entity('source'), family, entity('target')
    actual, expected = signature(answer.group('task')), signature(expected_instruction)
    return actual is not None and actual == expected

def confirmation_answer(text, expected_instruction=None):
    if re.fullmatch("\\s*(?:no[\\s,.;!，。；：]*)?(?:do\\s+not|don['’]t)\\s+(?:start|begin|execute|proceed)(?:\\s+(?:it|that(?:\\s+task)?|this(?:\\s+task)?|the\\s+task))?(?:\\s+(?:yet|now))?\\s*[.!。！]?\\s*", text, re.I):
        return 'reject'
    if re.search('[?？“”「」"\\\']', text):
        return None
    if matching_task_confirmation(text, expected_instruction):
        return 'confirm'
    value = compact(text)
    value = re.sub('^(?:嗯+|呃+|啊+)', '', value)
    value = re.sub('(?:吧|啊|呀)$', '', value)
    if re.fullmatch('(?:yes)?(?:execute(?:that|this|the)task|do(?:the)?(?:corrected|latest)task|goahead)', value):
        return 'confirm'
    if value in {'cancelthatproposal', 'cancelthisproposal', 'canceltheproposal', 'cancelthatrequest', 'cancelthisrequest', 'canceltherequest'}:
        return 'reject'
    if value in {'开始执行', '执行吧', '执行', '可以执行', '可以开始', '可以开始执行', '同意执行', '确认这条任务', '确认这个任务', '就按这个执行', '按这个执行', '好的开始执行', '好的可以执行', '好开始执行'}:
        return 'confirm'
    if value in {'不执行', '不要执行', '先不执行', '暂时不执行', '先不要执行', '取消这条提议', '取消这个提议', '拒绝执行', '不用执行', '不确认'}:
        return 'reject'
    if value in YES or re.fullmatch('(?:好的|好|是的|对|确认执行|确认|可以|就这样)+', value):
        return 'confirm'
    if value in NO or re.fullmatch('(?:不对|不是|不用|算了|取消确认|拒绝|不要|不)+', value):
        return 'reject'
    return None

def confirmation_filler(text):
    """A hesitation neither approves nor erases a still-live proposal."""
    return bool(re.fullmatch('(?:嗯+|呃+|哦+|噢+|啊+)+', compact(text)))

def inspect_semantics(utterance, instruction, inventory, referenced=False, previous='', grounding_utterance=None):
    observation = bool(re.search('(?:查看|看看|看一下|观察|检查|判断).{0,8}(?:炉灶|炉子|stove)', utterance, re.I))
    if observation and re.search('放|拿|推|put|place', utterance, re.I) and re.search('然后|之后|再去|then', utterance, re.I):
        raise ValueError('mixed_action_observation_unsupported: 暂不支持动作完成后自动串联视觉提问，请分开下达；不能改成打开炉灶。')
    if observation and re.search('\\bturn\\s+(?:on|off)\\b', instruction, re.I):
        raise ValueError('observation_is_not_action: 查看炉灶不等于打开或关闭；请保留只读观察要求。')
    if re.search('扶正|立起来|摆正|stand.*upright', utterance, re.I):
        raise ValueError('unsupported_recovery_goal: 当前执行器未验证倒瓶扶正技能，不能省略扶正后声称已执行完整任务。')
    if re.search('前几天|昨天|明天|后天|下周|yesterday|tomorrow', utterance, re.I):
        raise ValueError('temporal_request_needs_clarification: 时间表达不明确或需要定时，不能当成立即执行。')
    if re.search('推.{0,12}(?:炉灶|炉子)(?:旁边|旁|附近)', utterance) and re.search('front', instruction, re.I) and (not re.search('前方|前面|前边|炉灶前|炉子前', utterance)):
        raise ValueError('spatial_target_needs_clarification: 炉灶旁未明确前后左右，不能擅自指定前方。')
    validate_grounding(grounding_utterance or utterance, instruction, inventory, referenced)
    (raw, target) = (utterance.strip(), instruction.lower())
    report = {'schema': 'task_semantics.v1', 'user_utterance': raw, 'candidate_instruction': instruction, 'entities': sorted({e for (_, e) in mentions(grounding_utterance or raw) if e}), 'slots': [{'role': r, 'text': n} for (r, n) in slots(grounding_utterance or raw)], 'grounding_utterance': grounding_utterance or raw, 'audio_relisten_grounding_used': bool(grounding_utterance), 'checks': [], 'uncertainties': [], 'scope': 'bounded_bilingual_rules_not_general_equivalence'}

    def require(label, present, retained):
        if present:
            report['checks'].append(label)
            if not retained:
                raise ValueError('semantic_constraint_lost: ' + label + '；未下发动作，请保留原话要求。')
    physical_raw = re.sub('^(?:请)?(?:先|暂时)?不要执行[，,；;。]\\s*(?=(?:先|请|需要).{0,8}(?:问我|确认))', '', raw)
    if physical_raw != raw:
        report['checks'].append('执行授权与物理约束分离；仍须确认')
    selection = explicit_object_selection(physical_raw)
    if selection:
        physical_raw = selection['grounding_text']
        report['checks'].append('当前原话明确指定操作对象；不是物理保持要求')
    negative = bool(re.search('不要|不能|不许|别(?:把|放|拿|动|关|开)|禁止|不能|do not|don.t|never', physical_raw, re.I))
    require('禁止事项', negative, bool(re.search('\\b(?:not|never|without)\\b', target)))
    require('归位', bool(re.search('归位|放回|原位|原来(?:的)?位置|return|original (?:place|position)|\\bput\\b.{0,100}\\bback\\b|episode[- ]start', raw, re.I)), bool(re.search('return|back|original|episode[- ]start|initial (?:position|location)', target)))
    require('松手／释放', bool(re.search('松手|松开|释放|release|let go', raw, re.I)), bool(re.search('release|let go|open.*gripper', target)))
    require('保持约束', bool(re.search('保持|保留|不要改变|keep|leave .* (?:open|closed|inside|where|as it is|as they are)', physical_raw, re.I)), bool(re.search('\\b(?:keep(?:ing|s)?|leav(?:e|ing)|remain(?:ing|s)?|maintain(?:ing|s)?|without|preserv(?:e|ing))\\b', target)))
    for (zh, en) in [('关', 'close'), ('开', 'open')]:
        present = bool(re.search(zh + '(?:上|闭|启|着)?(?:中间|中层|上层|顶层|那个|这个|的|柜子)*抽屉', raw) or re.search('\\b' + en + '\\b.*drawer', raw, re.I))
        require(zh + '抽屉', present, bool(re.search(en + '.*drawer', target)))
    for (words, english) in [('中间|中层', 'middle'), ('上层|顶层', 'top')]:
        require(english + '抽屉', bool(re.search('(?:' + words + ').{0,3}抽屉', raw) or re.search('\\b' + ('(?:top|upper)' if english == 'top' else english) + '\\s+(?:layer\\s+)?drawer\\b', raw, re.I)), bool(re.search('\\b' + ('(?:top|upper)' if english == 'top' else english) + '\\s+(?:layer\\s+)?drawer\\b', target)))
    for (zh, en) in [('左边|左侧', 'left'), ('右边|右侧', 'right'), ('红色', 'red'), ('蓝色', 'blue')]:
        require('空间／属性约束 ' + en, bool(re.search(zh, raw)), bool(re.search('\\b' + en + '\\b', target)))
    if negative:
        negative_entities = [{e for (_, e) in mentions(c) if e} for c in re.findall('(?:不要|不能|不许|禁止|别)([^，。；,;]+)', physical_raw)]
        english_negative = [{e for (_, e) in mentions(c) if e} for c in re.findall('(?:do not|don.t|never|without)([^.;,]+)', target)]
        if any((n and (not any((n <= translated for translated in english_negative))) for n in negative_entities)):
            raise ValueError('semantic_negation_mismatch: 禁止事项所针对的物体没有对应保留；未下发动作。')
    if re.search('(?:先|需要|请).{0,8}(?:确认|问我)|等(?:待)?我(?:的)?确认|确认.{0,8}(?:再|后)|confirm.{0,12}before|(?:wait|ask).{0,25}(?:confirm|approval)|(?:confirm|approval).{0,20}before|\\bask\\s+(?:me|us)\\s+(?:first|before\\b.{0,30}(?:start|begin|execut))|\\bafter\\s+(?:(?:I|we)\\s+(?:approve|confirm)|(?:my|our)\\s+(?:approval|confirmation))\\b', raw, re.I):
        report['uncertainties'].append('用户要求先确认再执行')
    en_actions = re.findall('\\b(open|close|shut)\\s+(?:the\\s+)?(?:(middle|top|upper|bottom|lower)\\s+)?drawer\\b', target)
    layers = {'中间层': 'middle', '中间': 'middle', '中层': 'middle', '顶层': 'top', '上层': 'top', '下层': 'bottom', 'upper': 'top', 'lower': 'bottom'}
    prefix = '(打开|开启|开|关闭|关上|关)(?:一下)?(?:这|那|个|的)*\\s*(中间层|中间|中层|顶层|上层|下层)?(?:的)?\\s*抽屉'
    postfix = '(?:把|将)(?:这|那|个|的)*\\s*(中间层|中间|中层|顶层|上层|下层)?(?:的)?\\s*抽屉(?:给|先|再|完全|彻底|\\s)*(打开|开启|关闭|关上)'
    ordered = [(m.start(), m.group(1), m.group(2) or '') for m in re.finditer(prefix, raw)]
    ordered += [(m.start(), m.group(2), m.group(1) or '') for m in re.finditer(postfix, raw)]
    expected = []
    previous_pos = None
    for (pos, a, k) in sorted(ordered):
        action = 'close' if a.startswith('关') else 'open'
        layer = layers.get(k, k)
        bridge = raw[previous_pos:pos] if previous_pos is not None else ''
        if expected and expected[-1][0] == action and (not layer or not expected[-1][1] or expected[-1][1] == layer) and ('\n' in bridge) and (not re.search('然后|之后|接着|再|then|again', bridge, re.I)):
            expected[-1] = (action, layer or expected[-1][1])
        else:
            expected.append((action, layer))
        previous_pos = pos
    actual = [('close' if a == 'shut' else a, layers.get(k, k)) for (a, k) in en_actions]
    raw_drawer_actions = [('close' if a.lower() == 'shut' else a.lower(), layers.get(k.lower(), k.lower())) for (a, k) in re.findall('\\b(open|close|shut)\\s+(?:the\\s+)?(?:(middle|top|upper|bottom|lower)\\s+)?drawer\\b', raw, re.I)]
    requested_drawer_actions = expected + [(a.lower(), k.lower()) for (a, k) in raw_drawer_actions]
    for (action, layer) in actual:
        authorized = any((a == action and (not k or not layer or k == layer) for (a, k) in requested_drawer_actions))
        desired_state = bool(re.search('(?:keep|leave|保持|保留).{0,60}' + ('(?:closed|shut|关)' if action == 'close' else '(?:open|开)'), raw, re.I))
        access = action == 'open' and bool(re.search('put|place|放|摆', raw, re.I)) and bool(re.search('drawer|抽屉', raw, re.I))
        historical = referenced and bool(re.search('(?:恢复|继续|重做).{0,20}(?:之前|上个|刚才|已经完成)|(?:resume|restore|repeat).{0,30}(?:previous|last|completed)', raw, re.I))
        previous_layers = set(re.findall('\\b(middle|top) drawer\\b', previous.lower()))
        anaphoric = bool(re.search('\\b(?:close|shut)\\s+it\\b|把它关|关上它|关闭它' if action == 'close' else '\\bopen\\s+it\\b|把它打开|打开它|开启它', raw, re.I))
        bound_anaphor = anaphoric and (referenced or (len(previous_layers) == 1 and (not layer or layer in previous_layers)))
        explicit_drawer_restore = bool(re.search('抽屉.{0,8}恢复原状|恢复.{0,8}抽屉.{0,8}原状|\\brestore\\b.{0,25}\\bdrawer\\b.{0,25}\\b(?:original|initial)\\b', raw, re.I))
        bound_restore = explicit_drawer_restore and len(previous_layers) == 1 and (not layer or layer in previous_layers)
        if not (authorized or desired_state or access or historical or bound_anaphor or bound_restore):
            raise ValueError('semantic_unrequested_action: 候选增加了用户未要求的抽屉动作；未下发。')
    cursor = 0
    for (action, layer) in expected:
        found = next((i for i in range(cursor, len(actual)) if actual[i][0] == action and (not layer or actual[i][1] == layer)), None)
        if found is None:
            raise ValueError('semantic_action_mismatch: 抽屉动作、层位或先后顺序未保留；未下发动作。')
        cursor = found + 1
    sequence = re.search('先(.+?)(?:然后|再|之后)(.+)', raw) or re.search('((?:return|put|place|close|open|move)\\b.+?)\\bfirst[,.\\s]*\\bthen\\b(.+)', raw, re.I) or re.search('\\bfirst\\b[ ,]*(.+?)\\bthen\\b(.+)', raw, re.I) or re.search('(.+?)\\bbefore\\s+((?:putting|placing|moving|opening|closing|returning)\\b.+)', raw, re.I)
    if sequence:

        def action(clause):
            if re.search('(?:打开|开启|turn on).{0,12}(?:炉灶|炉子|stove)', clause, re.I):
                return 'turn_on_stove'
            if re.search('推|push', clause, re.I):
                return 'push'
            if re.search('关.*抽屉|close.*drawer', clause, re.I):
                return 'close'
            if re.search('开.*抽屉|open.*drawer', clause, re.I):
                return 'open'
            if re.search('放回|归位|return|\\bput\\b.{0,100}\\bback\\b', clause, re.I):
                return 'return'
            if re.search('放|摆|put|place', clause, re.I):
                return 'put'
            return None
        (first, second) = map(action, sequence.groups())
        report['checks'].append('执行顺序')
        if first and second and (first != second):

            def index(a):
                m = re.search({'put': 'put|place', 'return': 'return|put .*?back', 'turn_on_stove': 'turn on.*?stove'}.get(a, a), target)
                return m.start() if m else -1
            (a, b) = (index(first), index(second))
            if a < 0 or b < 0 or a >= b:
                raise ValueError('semantic_order_mismatch: 原话要求的先后顺序未保留；未下发动作。')
        else:
            report['uncertainties'].append('同类动作或复杂执行顺序需要明确确认')
    from task_contract import deferred_request
    if deferred_request(raw):
        raise ValueError('deferred_task_requires_new_request: 这是延迟请求，不能立即切换；请使用 robot_schedule_task 并绑定当前任务。')
    if re.search('如果|假如|要是|假设|\\bif\\b|suppose', raw, re.I):
        raise ValueError('conditional_request_needs_clarification: 条件尚未核实，不执行假设中的动作；请明确当前请求。')
    if re.search('不是.+(?:而是|是)|不对[，, ]|换句话说', raw):
        report['uncertainties'].append('存在改口，需要确认最终完整要求')
    if re.search('抽屉', raw) and (not re.search('中间|中层|上层|顶层', raw)):
        previous_refs = set(re.findall('\\b(middle|top) drawer\\b', previous.lower()))
        if len(previous_refs) != 1 and (not referenced):
            report['uncertainties'].append('尚未明确哪个抽屉')
    if (re.search('放进去|放到那里|放在那里|那个地方|这个地方', command_content(raw), re.I) or any((re.fullmatch('it|there', noun, re.I) for (_, noun) in slots(raw)))) and (not referenced):
        report['uncertainties'].append('目的地或物体指代不明确')
    resolved_grounding = grounding_utterance or raw
    raw_slots = slots(resolved_grounding)
    inside_bindings = list(re.finditer('\\bopen\\s+(?:the\\s+)?(middle|top|upper|bottom|lower)\\s+drawer\\s+and\\s+(?:put|place)\\s+([^.!?;,]+?)\\s+inside(?=\\s*(?:(?:instead|now|please)\\s*)?(?:[.!?;,]|$))', resolved_grounding, re.I))
    same_clause_inside = bool(inside_bindings)
    for binding in inside_bindings:
        expected_layer = layers.get(binding.group(1).lower(), binding.group(1).lower())
        source_entities = {entity for (_, entity) in mentions(binding.group(2)) if entity}
        if not source_entities and referenced and re.fullmatch('it|它', binding.group(2).strip(), re.I):
            candidate_sources = {e for (role, noun) in slots(target) if role == 'source' for (_, e) in mentions(noun) if e}
            if len(candidate_sources) == 1:
                source_entities = candidate_sources
        for clause in re.split('[.!?;,]|\\band\\s+(?=(?:put|place|move)\\b)', target, flags=re.I):
            clause_slots = slots(clause)
            actual_sources = {entity for (role, noun) in clause_slots if role == 'source' for (_, entity) in mentions(noun) if entity}
            if not source_entities.intersection(actual_sources):
                continue
            for (role, noun) in clause_slots:
                if role != 'target':
                    continue
                location = re.search('\\b(middle|top|upper|bottom|lower)\\s+drawer\\b', noun, re.I)
                implicit = bool(re.fullmatch('(?:it|inside|(?:the |that |this )?(?:opened )?drawer)', noun.strip(), re.I))
                if not implicit and (not location or layers.get(location.group(1).lower(), location.group(1).lower()) != expected_layer):
                    raise ValueError('semantic_inside_destination_changed: inside 必须指向同一分句中明确打开的抽屉；未下发。')
    if any((r == 'source' for (r, _) in raw_slots)) and (not any((r == 'target' for (r, _) in raw_slots))) and (not same_clause_inside) and re.search('放|put|place', raw, re.I) and (not re.search('归位|放回|\\breturn\\b|\\bput\\b.*\\bback\\b', raw, re.I)):
        report['uncertainties'].append('目的地需要确认')
    report['decision'] = 'needs_confirmation' if report['uncertainties'] else 'checked'
    return report
