import re
def question_kind(text):
    object_text=re.sub('哪(?:一个|个|件)(?:具体(?:的)?|确切(?:的)?)?(?:位置|地方|地点|目的地)|\\b(?:which|what)\\s+(?:(?:specific|exact)\\s+)?(?:place|location|destination|spot)\\b','<location-query>',text,flags=re.I)
    obj=bool(re.search('(?:which|what)\\s+(?:object|item|one)|what.{0,35}(?:move|pick up|put)|哪(?:个|件)(?:物体|物品|东西|对象)|什么(?:物体|物品|东西)|哪一个|指的是(?:哪个|什么)|(?:指|移动|操作|拿|放).{0,12}哪(?:个|件)',object_text,re.I))
    dest=bool(re.search('\\bwhere\\b|\\bdestination\\b|\\b(?:which|what)\\s+(?:(?:specific|exact)\\s+)?(?:place|location|destination|spot)\\b|放(?:到|在|进)?(?:哪|什么地方)|哪里|哪儿|目的地|哪(?:一个|个)(?:具体(?:的)?|确切(?:的)?)?(?:位置|地方|地点)',text,re.I))
    if obj and dest:return 'both'
    if dest:return 'destination'
    if obj:return 'object'
    if re.search(r'what (?:would|do) you (?:like|want) me to do|what.{0,12}(?:complete|full) (?:task|request)|具体.{0,12}(?:做什么|任务)|完整.{0,8}(?:指令|任务)',text,re.I):return 'both'
    if re.search(r'确认|是否.{0,12}(?:执行|开始)|可以.{0,15}(?:执行|开始).{0,5}[吗？?]|\bconfirm|\b(?:shall|should|may|can) I\b|\b(?:do|would) you (?:want|like) me to|\b(?:approve|approval)\b',text,re.I):return 'confirmation'
    return None
