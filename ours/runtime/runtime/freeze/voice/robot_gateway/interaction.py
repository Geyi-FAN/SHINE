"""Conservative final-transcript guard; unknown speech stays with the cloud model.

This is not streaming ASR or a general intent classifier. It never starts motion.
"""

import re
try:
    from .control_semantics import control_intent, allowed_control_tool
except ImportError:
    from control_semantics import control_intent, allowed_control_tool


def classify_utterance(text):
    control=control_intent(text)
    if control in ("pause","resume","cancel","cancel_waiting"):return control
    if control in ("protected","deferred_stop"):return "question" if "?" in str(text) else "non_command"
    text = str(text).strip().lower()
    compact = re.sub(r"[\s，。！？、,.!?；;]+", "", text)
    if not compact:
        return "unknown"
    if re.fullmatch(r'(?:mm-?hmm|mhm|uh-?huh|(?:ok|okay)[,!]?thankyou)',compact):
        return 'backchannel'
    if re.match(r'^(?:where\b|what\b|does the word\b|can you tell\b|tell me\b|explain what\b|look at\b)',text):
        return 'question'
    if re.match(r"^(?:do not|don't) stop(?: the robot)?[.!]",text):
        return 'question' if '?' in text else 'non_command'
    if re.fullmatch(r"(?:嗯|哦|错误|不对|好|好的)*暂停(?:吧|stop)?", compact):
        return "pause"
    if re.fullmatch(r'(?:嗯|哦|好|好的)*暂停(?:不对|错了|等等)',compact):
        return 'pause'
    # A factual correction or a complaint is not permission to restart motion.
    if re.search(r"为什么|怎么回事|你确定|有没有|哪一层|在哪里|相对位置|开度", text) and not re.search(r"请(?:你)?(?:帮我)?(?:重新|继续|暂停|停止|把|将|打开|关闭)|先停", text):
        return "question"
    if compact in {"正确", "不正确", "错误", "thankyou"} or re.fullmatch(r"(?:然后)?(?:现在)?有一定的开度", compact):
        return "non_command"
    if re.fullmatch(
        r"(?:唉|哎|真是)?(?:气死我(?:了|算了)?|烦死了|太烦了|真无语|无语了|这也太离谱了|你好)",
        compact,
    ):
        return "non_command"
    if re.fullmatch(
        r"(?:嗯+|哦+|噢+|对+|好的|好啊|好|明白了|知道了|谢谢你|谢谢)+", compact
    ) or compact in {
        "嗯",
        "嗯嗯",
        "哦",
        "噢",
        "对",
        "对对",
        "对对对",
        "嗯对",
        "好的",
        "好",
        "好啊",
        "明白了",
        "知道了",
        "谢谢",
        "谢谢你",
        "ok",
        "okay",
        "thanks",
        "yes",
    }:
        return "backchannel"
    if re.fullmatch(
        r"(?:请|你|机器人)?(?:现在)?(?:做到哪(?:一步|里)了|进行到哪一步了|在做什么|现在什么状态|什么状态|任务完成了吗|完成了吗|做完了吗|还要多久|能听到我吗)",
        compact,
    ):
        return "question"
    if re.fullmatch(
        r"(?:what are you doing|what is (?:the|your) status|are you done|how long will it take|can you hear me)[?.!]*",
        text,
    ):
        return "question"
    if compact in {
        "停",
        "停下",
        "停一下",
        "暂停",
        "暂停一下",
        "先停一下",
        "请停一下",
        "请暂停",
        "别动",
        "先别动",
        "先不要动",
        "stop",
        "pause",
        "stopplease",
    }:
        return "pause"
    if compact in {"继续", "继续吧", "请继续", "继续当前任务", "resume", "continue"}:
        return "resume"
    if compact in {"取消", "取消任务", "取消当前任务", "cancel", "canceltask"}:
        return "cancel"
    return "cloud_decision"


def allowed_voice_action(kind, name):
    # Bare assent is not authorization to create/resume/cancel physical work.
    if kind in ("backchannel", "question", "non_command", "unknown"):
        return False
    if not allowed_control_tool(kind,name):return False
    controls = {"pause": "robot_pause", "resume": "robot_resume", "cancel": "robot_cancel_task", "cancel_waiting":"robot_cancel_deferred"}
    return kind not in controls or controls[kind] == name
