"""Constrain JSON syntax and reasoning length, never choose semantic answers."""
import copy
import json
import re


def normalize_evidence_frames(pred):
    """Lossless JSON ID coercion only; never invent or replace cited frames.

    Some providers return numeric enum IDs as strings despite json_schema.
    Unknown, fractional, boolean or noncanonical IDs remain invalid below.
    The raw response is retained by transport and the observer audit.
    """
    output=copy.deepcopy(pred)
    frames=output.get('evidence_frames')
    if isinstance(frames,list):
        output['evidence_frames']=[int(value)if isinstance(value,str)and
            re.fullmatch(r'0|[1-9][0-9]*',value)else value for value in frames]
    return output


def constrain(body,role):
    output=copy.deepcopy(body)
    payload=None;frames=set()
    for message in output['messages']:
        if message.get('role')!='user' or not isinstance(message.get('content'),list):continue
        content=message['content']
        for item in content:
            if item.get('type')=='text':frames.update(int(x)for x in re.findall(r'frame=(-?\d+)',item['text']))
        if content and content[0].get('type')=='text':
            try:data=json.loads(content[0]['text'])
            except ValueError:continue
            if data.get('schema')in ('recovery_observation_v1','causal_visual_verifier_v2'):payload=data
    if payload is None:return output
    frames.update(r['frame']for r in payload.get('sensor_frames',payload.get('recent_frames',[])))
    if payload.get('stage_start'):frames.add(payload['stage_start']['frame'])
    evidence=dict(type='array',items=dict(type='integer',enum=sorted(frames)),maxItems=8)
    if role=='recovery':
        def obj(properties):return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)
        nullable_bool=dict(type=['boolean','null'])
        properties=dict(held_object=dict(type='string',enum=['bowl','cheese','wine_bottle','plate','none','unknown']),
                        support_visible=obj({e:nullable_bool for e in ['bowl','cheese','wine_bottle','plate']}),
                        relations=obj({r:nullable_bool for r in ['bowl_drawer','cheese_bowl']}),
                        bowl_location=dict(type='string',enum=['table','cabinet_top','stove','plate','top_drawer','held','unknown']),
                        evidence_frames=dict(evidence,minItems=1),rationale=dict(type='string',maxLength=650),
                        recovery_request=dict(type='string',enum=['observe_only','observe_above','observe_clear_cabinet','clear_supported_object','open_empty_gripper','replan_current_task','release_supported_in_place','none']),
                        release_object=dict(type=['string','null'],enum=['bowl','cheese','wine_bottle','plate',None]))
        schema=obj(properties)
        note='Return the documented JSON only. Keep rationale to at most3 short factual sentences and80 English words; no step-by-step deliberation or lists of alternative tools. All original evidence, ownership and tool preconditions still apply. Unknown/null remain valid when evidence is insufficient.'
    else:
        check_properties=dict(condition=dict(type='string',enum=['object_identity','goal_relation','temporal_stability','release','disengagement']),
                              verdict=dict(type='string',enum=['pass','fail','unknown']),evidence_frames=evidence,
                              evidence=dict(type='string',maxLength=240))
        check=dict(type='object',properties=check_properties,required=list(check_properties),additionalProperties=False)
        properties=dict(status=dict(type='string',enum=['completed','not_completed','uncertain']),
                        checks=dict(type='array',items=check,minItems=1,maxItems=5),reason=dict(type='string',maxLength=400),
                        missing_evidence=dict(type='array',items=dict(type='string',maxLength=180),maxItems=6))
        schema=dict(type='object',properties=properties,required=list(properties),additionalProperties=False)
        note='Return the documented JSON only. Each evidence should be one short factual sentence. A check verdict is pass/fail/unknown; uncertain is a status, not a check verdict. Keep reason under40 words. Do not restate the prompt or reason through hypothetical alternatives. Preserve every required check and unchanged physical acceptance criteria.'
    output['messages'][0]['content']+='\n\nOUTPUT FORMAT DISCIPLINE:\n'+note
    output['response_format']=dict(type='json_schema',json_schema=dict(name=role+'_observation_v1',strict=True,schema=schema))
    return output
