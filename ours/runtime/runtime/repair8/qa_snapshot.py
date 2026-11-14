"""QA truth belongs to the exact recorded image, not the entire moving scene.

Only independent scoring reads physical truth. None of this is an Agent input.
An image is admitted only when capture time and the logged visual request bind
it to this episode/question, and a private physics sample is within100ms.
"""
import hashlib,re
from pathlib import Path
B=Path(__file__).resolve().parents[1]

def answer_status(text,held,on_stove,robot_contact):
    held_claim=bool(re.search(r'夹爪中|夹爪里|手中|拿着|夹着|被夹持|仍.{0,4}夹持|holding|held|gripper|尚未释放|还未释放|仍未松手|尚未放置',text,re.I))
    if re.search(r'不在.{0,4}夹爪|未见.{0,6}夹持|没有.{0,6}夹持|not held|not holding|no.{0,8}gripper|已(?:经)?释放|已(?:经)?松手',text,re.I):held_claim=False
    placed_claim=bool(re.search(r'(?:在|位于|放在).*(?:炉灶|炉子)(?:的)?(?:加热盘)?上(?!方|空)|加热盘上(?!方|空)|\bon (?:the )?stove\b',text,re.I))
    if re.search(r'未(?:被)?放置|尚未放置|还没放下|not.{0,8}(?:placed|put down)',text,re.I):placed_claim=False
    if held_claim and held and not placed_claim:return 'pass'
    if placed_claim and on_stove and not robot_contact and not held_claim:return 'pass'
    if (placed_claim and not on_stove)or(held_claim and not held):return 'fail'
    return 'unknown'

def score(directory,result,voice,ticks,turn,text,last_play_time):
    evidence=[e['payload']for e in voice if e.get('type')=='visual.analysis'and e.get('payload',{}).get('event')=='visual.evidence'and turn['audio_started_wall']<=e.get('ts',0)/1000<=last_play_time]
    normalize=lambda t:re.sub(r'[^a-z0-9]','',str(t).lower())
    evidence=[e for e in evidence if bool(re.search(r'\bbowl\b|碗',str(e.get('question','')),re.I))and e.get('episodeId')==result.get('episode_id')]
    if len(evidence)!=1:return 'unknown',dict(reason='unique_matching_visual_evidence_required')
    evidence=evidence[0];at=evidence.get('observationTime');requests=[e['payload']for e in voice if e.get('type')=='visual.analysis'and e.get('payload',{}).get('event')=='robot_visual.request'and e.get('payload',{}).get('taskId')==evidence.get('taskId')]
    if not isinstance(at,(int,float)):return 'unknown',dict(reason='visual_observation_timestamp_missing')
    hashes={e.get('image_sha256')for e in requests};matches=[]
    local=list((Path(directory)/'qa_frames').glob('*.jpg'))
    for p in (local or list((B/'freeze/voice/data/visual_captures').glob('*.jpg'))):
        if abs(p.stat().st_mtime-at)>.25:continue
        h=hashlib.sha256(p.read_bytes()).hexdigest()
        if hashes and h not in hashes:continue
        matches.append((p,h))
    if len(matches)!=1:return 'unknown',dict(reason='unique_saved_image_hash_or_capture_time_required',matches=len(matches))
    image,h=matches[0];at=image.stat().st_mtime
    if not ticks:return 'unknown',dict(reason='private_physics_trace_missing')
    current=min(ticks,key=lambda t:abs(t['time']-at));delta=abs(current['time']-at)
    if delta>.1:return 'unknown',dict(reason='no_matching_physics_sample',delta_s=delta)
    p=current['physical'];held=p['held_object']=='bowl';goal=p['native_goal_relations']['bowl_stove'];contact=p['objects']['bowl']['robot_contact']
    return answer_status(text,held,goal,contact),dict(method='exact_snapshot_time_independent_physics',image=str(image),image_sha256=h,request_hash_verified=bool(hashes),capture_time=at,physics_sample_time=current['time'],delta_s=delta,held_bowl=held,bowl_stove=goal,robot_contact=contact,actual_spoken_text=text)
