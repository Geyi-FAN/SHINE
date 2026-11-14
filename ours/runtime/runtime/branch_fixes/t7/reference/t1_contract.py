"""Private evaluator definitions. Never imported into planner or policy inputs."""
import re

GOALS = [
    ('open_middle','打开中间抽屉',None),('bowl_stove','碗放炉灶','bowl'),
    ('bottle_cabinet','酒瓶放柜顶','wine_bottle'),('bowl_drawer','开顶层抽屉并放碗','bowl'),
    ('bowl_cabinet','碗放柜顶','bowl'),('push_plate','盘子推至炉灶前','plate'),
    ('cheese_bowl','奶酪放入碗','cheese'),('turn_on_stove','打开炉灶',None),
    ('bowl_plate','碗放盘子上','bowl'),('bottle_rack','酒瓶放酒架','wine_bottle'),
]


def instruction_goal(text):
    """Bounded independent semantic check; no call to the model's own parser."""
    s=text.lower().replace('cream cheese','cheese')
    # Unrequested extra physical goals invalidate a complete T1 request.
    if re.search(r'\b(?:close|return)\b|\bput\b.{0,25}\bback\b|关上|关闭|归位|放回',s):return None
    drawer=re.search(r'(?:open|pull open|pull out).{0,25}(?:top|upper).{0,15}drawer',s)
    if drawer and re.search(r'(?:put|place).{0,30}bowl.{0,40}(?:inside|into|in (?:it|the (?:top |upper )?drawer))',s):return 3
    if re.search(r'(?:open|pull open|pull out).{0,25}middle.{0,15}drawer',s) and not re.search(r'\b(?:put|place|push)\b',s):return 0
    if re.search(r'(?:turn|switch).{0,8}on.{0,15}stove|(?:turn|switch).{0,15}stove.{0,8}on',s):return 7
    if re.search(r'(?:push|slide).{0,25}plate.{0,30}front.{0,15}stove',s):return 5
    put=re.search(r'\b(?:put|place|set)\b',s)
    if not put:return None
    s=s[put.start():]
    if re.search(r'cheese.{0,35}(?:in|into|inside).{0,15}bowl',s):return 6
    if re.search(r'(?:wine )?bottle.{0,35}(?:on|onto).{0,20}cabinet',s):return 2
    if re.search(r'(?:wine )?bottle.{0,35}(?:on|onto).{0,20}rack',s):return 9
    if re.search(r'bowl.{0,35}(?:on|onto).{0,20}stove',s):return 1
    if re.search(r'bowl.{0,35}(?:on|onto).{0,20}cabinet',s):return 4
    if re.search(r'bowl.{0,35}(?:on|onto).{0,20}plate',s):return 8
    return None


def goal_flag(tick,task):
    return tick.get('physical',{}).get('native_goal_relations',{}).get(GOALS[task][0])
