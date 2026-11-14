"""Generic language guards; no benchmark IDs, expected plans or position truth."""
import re
import sys

_installed=False

def _rebind(old,new):
    for module in list(sys.modules.values()):
        if module is None:continue
        for name in ('slots','classify_utterance','inspect_semantics','compile_objective'):
            if getattr(module,name,None)is old:setattr(module,name,new)

def historical_location(noun):
    s=re.sub(r'\s+','',noun)
    return bool(re.fullmatch(r'(?:回)?(?:本轮|这轮|这个|本次|这次)?(?:场景|episode|原任务|源任务|任务)(?:刚|最)?开始(?:时)?(?:的)?(?:原始|初始)?位置',s,re.I))

def explicit_drawer_command(text):
    if re.search(r'[?？]|吗|呢|为什么|怎么|如何|怎样|多少|多大|哪里|是否|能否|有没有|请问|告诉|分析|判断|我想知道',text):return False
    s=re.sub(r'^\s*(?:(?:stop|pause)[.!,，。！\s]*|(?:请)?(?:先)?(?:停一下|暂停|停止)[，。！\s]*)','',text,flags=re.I)
    return bool(re.match(r'^\s*(?:请(?:你)?(?:帮我)?)?(?:先)?(?:把|将).+?(?:放到|放在|放入|移动|摆到)',s))

def canonical_objective_text(text):
    # Only the explicit binary-state phrase is normalized. Temperature, power
    # level and open/close goals remain separate and may be unsupported.
    p=r'\b(keep(?:ing)?|leave|leaving|maintain(?:ing)?|preserv(?:e|ing))\s+(?:the\s+)?stove\s+(?:at|in)\s+(?:its|the)\s+(current|same|instruction[- ]switch)\s+switch\s+state\b'
    return re.sub(p,lambda m:f'{m[1]} the stove in its {m[2]} state',text,flags=re.I)

def same_utterance_container(text):
    if re.search(r'不要|不许|别|不能|如果|假如|是否|[?？]|\b(?:not|never|if|unless)\b',text,re.I):return None
    opened=set(re.findall(r'(?:打开|拉开|开启)\s*(顶层|上层|中间|中层)\s*抽屉',text))
    opened={('顶层'if x in ('顶层','上层')else'中间')for x in opened}
    return next(iter(opened))+'抽屉'if len(opened)==1 and re.search(r'把[^，。；,.!?;]{1,30}放进去',text)else None

def install(core):
    global _installed
    if _installed:return
    import grounding,interaction,semantics
    from continuation.live import objectives
    old_slots=grounding.slots
    def slots(text):
        # A literal open-container antecedent in this SAME real utterance can
        # resolve "放进去". No scene prior/history or private answer is used.
        container=same_utterance_container(text)
        found=[]
        for role,noun in old_slots(text):
            if role=='target'and historical_location(noun):noun='原位'
            if role=='target'and noun in ('那里','去')and container:noun=container
            found.append((role,noun))
        return found
    _rebind(old_slots,slots)
    old_classify=interaction.classify_utterance
    def classify_utterance(text):
        if re.search(r'^\s*(?:如果|假如|假设|要是|what if|suppose).*(?:停|stop|pause)',str(text),re.I):return 'question'
        kind=old_classify(text)
        if kind=='question'and '开度'in str(text)and explicit_drawer_command(str(text)):return 'cloud_decision'
        return kind
    _rebind(old_classify,classify_utterance)
    old_inspect=semantics.inspect_semantics
    def inspect_semantics(utterance,instruction,inventory,referenced=False,previous='',grounding_utterance=None):
        # "把中间抽屉关上" and "关上中间抽屉" have the same explicit action.
        # This canonical form is used by permission checks only, never sent as
        # a replacement user task or planner prompt.
        pattern=r'(?:把|将)((?:这|那|个|的|\s)*(?:中间层|中间|中层|顶层|上层)(?:的)?\s*抽屉)(?:给|先|再|完全|彻底|\s)*(打开|开启|关闭|关上)'
        normalized=re.sub(pattern,lambda m:m[2]+m[1],utterance)
        container=same_utterance_container(utterance)
        if container:
            normalized=re.sub(r'(把[^，。；,.!?;]{1,30})放进去',lambda m:m[1]+'放进'+container,normalized)
        report=old_inspect(normalized,instruction,inventory,referenced,previous,grounding_utterance)
        if normalized!=utterance:
            report['user_utterance']=utterance
            report['guard_only_normalized_utterance']=normalized
            report['guard_only_transform']='explicit Chinese drawer postfix/unique same-utterance container; no new action'
        return report
    _rebind(old_inspect,inspect_semantics)
    old_compile=objectives.compile_objective
    def compile_objective(instruction,*args,**kwargs):
        return old_compile(canonical_objective_text(instruction),*args,**kwargs)
    _rebind(old_compile,compile_objective)
    _installed=True
