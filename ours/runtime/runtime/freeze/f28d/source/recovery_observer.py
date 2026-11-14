"""Bounded image/proprioception inspection; never imports simulator truth or contracts."""
import base64, io, json, os, time, urllib.request
from pathlib import Path
from PIL import Image
from agent_transport import ProviderUnavailable
from local_transport import connection, recovery_request_json as request_json

SYSTEM = '''You are the observation and recovery agent of a robot. Inspect the supplied
MAIN and WRIST RGB images, measured robot proprioception and fallible YOLO points.
No simulator object state or reference answer is available. Judge what is present,
Robot measurement rules: finger width below 0.060 metres is CLOSED, above 0.065 metres is OPEN. A width of 0.011m is 1.1cm and is NOT open. Perspective can make a closed gripper look open. Never override this measured opening with an image impression.
When measured closed fingers are close to a bowl rim on a visible support surface, distinguish contacting/gripping the supported bowl from a clear empty hand. If the next user operation requires handling another object, request release_supported_in_place with release_object=bowl to open the fingers without translating the arm. This request does not assert a completed grasp; it clears possible contact at the present support. If support is not visible, request observe_only instead.

not what the user wants to be true. A closed gripper does not prove it holds anything.
Distinguish bowl, plate and cheese by both views. A bowl visible inside the open top
drawer already satisfies containment; leave/keep means preserve it, not pick it up again.
Only claim support_visible=true when an actual surface directly supports the object;
an object suspended over a surface has support_visible=false. If occluded, use null.
Do not infer exact stable support/contact from one frame. Do not label future phases completed.
Return JSON: {held_object: bowl|cheese|wine_bottle|plate|none|unknown,
 support_visible: {bowl: true|false|null, cheese: ..., wine_bottle: ..., plate: ...},
 relations: {bowl_drawer: true|false|null, cheese_bowl: true|false|null},
 bowl_location: table|cabinet_top|stove|plate|top_drawer|held|unknown,
 evidence_frames: [provided frame numbers], rationale: string,
 recovery_request: observe_only|observe_above|observe_clear_cabinet|clear_supported_object|open_empty_gripper|replan_current_task|release_supported_in_place|none, release_object: bowl|cheese|wine_bottle|plate|null}.
release_supported_in_place is a request to OPEN the fingers at the CURRENT robot pose,
not to transport, return or drop an airborne object. Request it only when another
object occupies the gripper, its existing surface support is clearly visible, and
freeing the hand is necessary to execute the user's task. Also request this when closed fingers are visibly touching/around the rim of a supported NON-target object, even if you cannot distinguish gripping from touching: opening in place avoids accidentally dragging it while reaching for another object. Set release_object to that supported object. Never relocate that object. Do not request releasing the object the user needs transported while it is airborne.
observe_above requests a bounded 3cm WORLD-z upward camera/hand reposition while retaining the CURRENT gripper opening. It is only available during a selected placement (e.g. cheese into bowl) when the target reference is occluded or progress is stalled, and the images show free space above the hand. It does not declare placement complete or change the goal. Do not request it under a drawer roof, while gripping the target container itself, or without overhead clearance. Use this to stop pressing into/occluding a bowl and obtain a fresh target observation before resuming the SAME placement. No guessed point is permitted.
observe_clear_cabinet requests a bounded 4cm hand/camera withdrawal OUTWARD from the cabinet front along the known calibrated drawer opening direction, keeping the gripper OPEN. Use it only after a selected close-drawer stage has a visual completion candidate but the hand occludes the independent closing measurement. It does not claim the drawer is closed. Do not request it with a held object. Empty almost-fully-closed fingers (measured width below .002m with no carried object) are permitted: the tool first opens them in place for16steps and then withdraws. A partially closed possibly occupied hand is not permitted. New images and geometric evidence must still pass the unchanged completion gate after withdrawing.
clear_supported_object requests an OPEN-FINGER 6cm vertical withdrawal immediately AFTER an Agent-requested supported in-place release, before reaching for another object. The observation_request_context will explicitly identify that completed finger-opening tool and remaining near-rim contact. If the hand is still close to the supported old bowl/object and overhead space is free, request clear_supported_object. This avoids the next grasp instruction closing fingers again while still inside the old bowl. It is not a return or transport subgoal. Do not request it inside a drawer or under an overhead obstacle. It is unavailable unless an in-place release was actually executed and measured fingers are now open.
open_empty_gripper requests opening empty fingers IN PLACE and retrying the SAME selected grasp. Only request it during a stalled grasp, when the measured hand is almost fully closed (width below .002m), the target is visible away from the fingers, and the images show no carried object. It does not assert grasp completion.
Exception for lost ownership during a selected cheese_bowl placement: if the almost-fully-closed hand is EMPTY, the cheese visibly rests on another support OUTSIDE the bowl, and recent measured target points stay separate from the hand, request open_empty_gripper to open in place and then let the planning Agent regenerate the remaining plan. Do not endlessly continue placing with an empty closed hand. The script must independently corroborate this with three fresh depth/robot observations; your request is not permission to assume those checks pass. This tool never marks the failed placement complete, and does not itself choose the next subgoal. If support/ownership is unknown, request observe_only.
replan_current_task requests the planning Agent to regenerate the remaining plan from the actual observed state, retaining the original task. Use it during stalled placement if the hand is now empty/open, the object was dropped/released OUTSIDE its requested destination, and the object is supported elsewhere. Do not continue a placement that requires holding an object once ownership is lost. Do not propose the new operation yourself here; the planning Agent will receive the observed facts and choose it. Never mark the failed placement completed.
If the fingers are OPEN and your rationale says an object has been released/falling, do not simultaneously label it held_object=cheese; ownership and airborne state are different. Use none or unknown as justified.
It will require new-frame corroboration and independent robot guards before execution.
If images are insufficient, keep unknown/null and request observe_only.
If observation_request_context.reason is current_target_reference_missing, the controller CANNOT bind the required coordinate. Merely stating that you see a bowl is not a replacement for the missing tool point. Do not request none. If stationary_observation_has_not_reacquired is true, reconsider the viewpoint rather than assuming another identical static image will solve it. During a cheese_bowl placement with the cheese still held and visible free overhead space, observe_above is available to obtain a new view; if clearance or ownership is uncertain, retain observe_only. Never claim completion or supply a guessed point.
Describe bowl_location from the CURRENT images only. cabinet_top means the bowl sits on the cabinet TOP SURFACE, not inside a drawer. plate means it sits on the plate, not that the plate itself is a bowl. held means the bowl is carried without surface support. If obscured or ambiguous, use unknown. This describes a present location, not a new requested destination.
Report image evidence in rationale; never echo a detector label as independent evidence.'''

class RecoveryObserver:
    def __init__(self, folder):
        self.folder=Path(folder); self.folder.mkdir(parents=True,exist_ok=True);self.calls=[]
        self.cfg,self.key=connection('recovery')
        self.episode_reference=self.folder.parent/'points/-1_episode_start.png'
    def check(self, user_message, rows, diagnostics):
        selected=rows[-3:];i=len(self.calls)
        payload=dict(schema='recovery_observation_v1',user_message=user_message,
            sensor_frames=[dict(frame=r['frame'],sensor=r.get('sensor'),
                fresh_yolo_points=r.get('image_points',[]),depth_xyz_m=r.get('geometry',{})) for r in selected],
            fallible_holding_estimate=diagnostics.get('holding'),
            observation_request_context=diagnostics.get('observation_request_context'),
            measured_gripper_width_m=selected[-1].get('sensor',{}).get('width'),
            opening_definition=dict(closed_below_m=.060,open_above_m=.065))
        context=payload.get('observation_request_context') or {}
        near=(payload.get('fallible_holding_estimate') or {}).get('near_px',{}).get('bowl')
        width=payload.get('measured_gripper_width_m')
        show_history=not context.get('selected_stage') and width is not None and width<.060 and near is not None and near<=26 and self.episode_reference.exists()
        if show_history:
            payload['historical_visual_reference']=dict(time_source='episode_start',view='MAIN256',purpose='appearance and initial support context only; historical support is NOT current support; judge the current MAIN and WRIST before requesting release')
        contents=[dict(type='text',text=json.dumps(payload))]
        if show_history:
            contents.extend([dict(type='text',text='HISTORICAL EPISODE-START MAIN: appearance/layout reference only. This is not a current frame and cannot be cited as current support or completion evidence.'),
                             dict(type='image_url',image_url=dict(url='data:image/png;base64,'+base64.b64encode(self.episode_reference.read_bytes()).decode()))])
        for r in selected:
            import numpy as np
            im=Image.fromarray(np.concatenate([r['main'],r['wrist']],axis=1));b=io.BytesIO();im.save(b,format='JPEG',quality=90)
            (self.folder/f'{i}_frame{r["frame"]}.jpg').write_bytes(b.getvalue())
            contents.extend([dict(type='text',text=f'frame={r["frame"]}: MAIN left, WRIST right'),
                dict(type='image_url',image_url=dict(url='data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()))])
        (self.folder/f'{i}_input.json').write_text(json.dumps(payload,indent=2))
        start=time.monotonic();item=dict(frame=selected[-1]['frame'],accepted=False)
        system=SYSTEM
        if os.environ.get('CAP_RETURN_RELEASE_REVIEW','0')=='1'and context.get('reason')=='return_in_position_but_fingers_closed':
            from return_release_review import ADDENDUM
            system+='\n'+ADDENDUM
        if context.get('reason')=='drawer_has_not_completed_after_bounded_execution':
            system+='\nCURRENT STALLED-DRAWER CONTEXT EXTENSION: The selected opening OR closing operation has stalled with a measured stationary robot window. In THIS context observe_clear_cabinet is also available without a close-completion candidate. Request it only with an empty hand and a visibly clear outward path; open fingers, or an almost-fully-closed empty hand that will be opened first, remain mandatory. No carried object or uncertain contact is permitted. The script uses the same bounded4cm withdrawal and existing control/inspection limits, then retries the SAME operation. The tool is NOT a success declaration. Prefer observe_only if clearance or ownership is unclear. Never request object-release, placement or grasp tools in this context.'
        if show_history:
            system+='\nHISTORICAL REFERENCE CAUTION: Use the episode image to identify the bowl and compare its support context, then inspect current MAIN and WRIST. Seeing the bowl interior in WRIST alone does not prove it is airborne or held. A closed hand touching a visibly supported bowl rim may need supported in-place release. Conversely, historical table support does not permit release of a currently airborne bowl. If current support is hidden, preserve unknown and request observation.'
        body=dict(model=self.cfg['model'],
            messages=[dict(role='system',content=system),dict(role='user',content=contents)],
            enable_thinking=False,response_format=dict(type='json_object'),temperature=0,max_tokens=1200)
        try:
            from observation_validation import errors as tool_errors
            messages=body['messages'];attempts=[]
            for attempt in range(3):
                body['messages']=messages
                req=urllib.request.Request(self.cfg['chat_url'],
                    data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
                response=request_json(req,timeout=90)
                content=response['choices'][0]['message']['content'];raw_pred=json.loads(content)
                from output_contract import normalize_evidence_frames
                pred=normalize_evidence_frames(raw_pred)
                available={r['frame'] for r in selected};cited=set(pred.get('evidence_frames',[]))
                valid=pred.get('held_object') in ('bowl','cheese','wine_bottle','plate','none','unknown') and bool(cited) and cited<=available
                validation=tool_errors(pred,payload)
                if not valid:validation.append('Use the documented holding enum and only actual supplied evidence frames.')
                attempts.append(dict(output=pred,raw_output=raw_pred,errors=validation,usage=response.get('usage')))
                item.update(response=pred,accepted=valid and not validation,usage=response.get('usage'),attempts=attempts)
                if item['accepted']:break
                messages += [dict(role='assistant',content=content),dict(role='user',content='Regenerate your observation/tool JSON from the SAME supplied evidence. Input-only tool validation: '+json.dumps(validation))]
        except ProviderUnavailable:
            raise
        except Exception as exc:item['infrastructure_error']=type(exc).__name__+': '+str(exc)
        item['seconds']=time.monotonic()-start;self.calls.append(item)
        with (self.folder/'calls.jsonl').open('a') as f:f.write(json.dumps(item)+'\n')
        return item
