// Evaluator-side dialogue selection only. Nothing here is passed to the Agent.
import {placementAlias} from './t5_goal_alias.mjs';
export function questionKind(text) {
 const s=String(text||'').trim();
 // Error receipts are not questions or requests for confirmation.
 if(/没有取得有效操作回执|本次请求尚未确认下发|这次操作没有成功受理|不会自动重发/.test(s)&&!/[?？]|哪(?:里|儿|个)|\b(?:which|where)\b/i.test(s))return null;
 // A location interrogative is not a second question about the object.
 const objectText=s.replace(/哪(?:一个|个|件)(?:具体(?:的)?|确切(?:的)?)?(?:位置|地方|地点|目的地)|\b(?:which|what)\s+(?:(?:specific|exact)\s+)?(?:place|location|destination|spot)\b/gi,'<location-query>');
 const obj=/(?:which|what)\s+(?:object|item|one)|what.{0,35}(?:move|pick up|put)|哪(?:个|件)(?:物体|物品|东西|对象)|什么(?:物体|物品|东西)|哪一个|指的是(?:哪个|什么)|(?:指|移动|操作|拿|放).{0,12}哪(?:个|件)/i.test(objectText);
 const dest=/\bwhere\b|\bdestination\b|\b(?:which|what)\s+(?:(?:specific|exact)\s+)?(?:place|location|destination|spot)\b|放(?:到|在|进)?(?:哪|什么地方)|哪里|哪儿|目的地|哪(?:一个|个)(?:具体(?:的)?|确切(?:的)?)?(?:位置|地方|地点)/i.test(s);
 if(obj&&dest)return 'both';
 if(dest)return 'destination';
 if(obj)return 'object';
 if(/what (?:would|do) you (?:like|want) me to do|what.{0,12}(?:complete|full) (?:task|request)|具体.{0,12}(?:做什么|任务)|完整.{0,8}(?:指令|任务)/i.test(s))return 'both';
 if(/确认|是否.{0,12}(?:执行|开始)|可以.{0,15}(?:执行|开始).{0,5}[吗？?]|\bconfirm|\b(?:shall|should|may|can) I\b|\b(?:do|would) you (?:want|like) me to|\b(?:approve|approval)\b/i.test(s))return 'confirmation';
 return null;
}

export function instructionGoal(text) {
 const original=String(text||'');
 const s=(placementAlias(original)||original).toLowerCase().replaceAll('cream cheese','cheese');
 if(/\b(?:close|return)\b|关上|关闭|归位|放回/.test(s))return null;
 if(/(?:open|pull).{0,25}(?:top|upper).{0,15}drawer/.test(s)&&/bowl.{0,40}(?:inside|into|in it|in the)/.test(s))return 3;
 if(/打开.{0,8}(?:顶层|上层|顶部).{0,6}抽屉/.test(s)&&/碗.{0,15}(?:放|里|内)|(?:放|装).{0,8}碗/.test(s))return 3;
 if(/(?:open|pull).{0,25}middle.{0,15}drawer|打开.{0,8}(?:中间|中层).{0,6}抽屉/.test(s))return 0;
 if(/(?:turn|switch).{0,8}on.{0,15}stove|(?:turn|switch).{0,15}stove.{0,8}on|(?:打开|开启).{0,5}(?:炉灶|炉子)/.test(s))return 7;
 if(/(?:push|slide).{0,20}plate.{0,30}front.{0,15}stove|推.{0,8}盘子.{0,15}(?:炉灶|炉子).{0,5}前/.test(s))return 5;
 if(/cheese.{0,35}(?:in|into|inside).{0,15}bowl|奶酪.{0,15}(?:放|进|入).{0,10}碗/.test(s))return 6;
 if(/(?:wine )?bottle.{0,35}(?:on|onto).{0,20}cabinet|酒瓶.{0,15}(?:柜顶|柜子顶部|柜子上|柜子的顶)/.test(s))return 2;
 if(/(?:wine )?bottle.{0,35}(?:on|onto).{0,20}rack|酒瓶.{0,15}酒架/.test(s))return 9;
 if(/bowl.{0,35}(?:on|onto).{0,20}stove|碗.{0,15}(?:炉灶|炉子)/.test(s))return 1;
 if(/bowl.{0,35}(?:on|onto).{0,20}cabinet|碗.{0,15}(?:柜顶|柜子顶部|柜子上)/.test(s))return 4;
 if(/bowl.{0,35}(?:on|onto).{0,20}plate|碗.{0,15}盘子/.test(s))return 8;
 return null;
}

export function playedReplies(messages,voice,after) {
 const starts=messages.filter(m=>m.direction==='sent'&&m.type==='host.playback_started'&&m.time>=after);
 const replies=[];
 for(const play of starts) {
  const end=messages.find(m=>m.direction==='sent'&&m.type==='host.playback_completed'&&m.epoch===play.epoch&&m.outputId===play.outputId);
  if(!end)continue;
  // A nearby second notification is not the audio that actually played here.
  // Prefer the existing immutable receipt key + epoch/output identity over a
  // +/-2s transcript search; keep the old fallback for legacy unkeyed streams.
  const receipt=messages.find(m=>m.type==='host.output_audio_receipt'&&m.epoch===play.epoch&&m.outputId===play.outputId&&m.receiptKey);
  if(receipt){
   const bound=voice.filter(e=>e.type==='transcript.assistant'&&!e.payload?.audioSuppressed&&
      e.payload?.receipt_key===receipt.receiptKey&&e.payload?.text===receipt.text);
   if(bound.length)replies.push({text:receipt.text,source:'exact_receipt_key_and_completed_playback',time:play.time,
      completed_time:end.time,output_id:play.outputId,epoch:play.epoch});
   continue;
  }
  const direct=voice.filter(e=>e.type==='transcript.assistant'&&!e.payload?.audioSuppressed&&Math.abs(e.ts/1000-play.time)<=2);
  let candidates=direct.map(e=>({text:e.payload.text,source:'direct_transcript_and_completed_playback'}));
  for(const e of voice.filter(e=>e.type==='transcript.assistant'&&e.payload?.audioSuppressed&&e.payload?.responseId)) {
   const done=voice.find(d=>d.type==='response.done'&&d.payload?.responseId===e.payload.responseId&&d.ts>=e.ts);
   if(!done)continue;
   const next=Math.min(...voice.filter(d=>d.ts>done.ts&&['response.created','transcript.assistant'].includes(d.type)&&d.payload?.responseId!==e.payload.responseId).map(d=>d.ts),Infinity);
   const released=voice.filter(d=>d.type==='realtime.protocol'&&d.payload?.type==='robot.reply_verified'&&['original','matched_receipt_audio'].includes(d.payload.decision)&&d.ts>=done.ts&&d.ts<next&&play.time-d.ts/1000>=-.1&&play.time-d.ts/1000<=2);
   if(released.length===1)candidates.push({text:e.payload.text,source:'buffered_transcript_verified_and_completed_playback'});
  }
  if(!candidates.length) {
   const caption=messages.filter(m=>m.type==='host.state'&&m.status?.caption&&m.time<=play.time&&play.time-m.time<=1).at(-1)?.status.caption;
   if(caption)candidates=[{text:caption,source:'caption_at_bound_playback_onset_and_completion'}];
  }
  const texts=[...new Set(candidates.map(c=>c.text?.trim()).filter(Boolean))];
  if(texts.length===1)replies.push({...candidates.find(c=>c.text?.trim()===texts[0]),text:texts[0],time:play.time,completed_time:end.time,output_id:play.outputId,epoch:play.epoch});
 }
 return replies;
}

export function validProposal(reply,pending,expected) {
 if(!reply||questionKind(reply.text)!=='confirmation'||!pending)return false;
 if(instructionGoal(pending.instruction)!==expected)return false;
 const spoken=instructionGoal(reply.text);
 if(spoken!==null)return spoken===expected;
 // Short deictic confirmation is legitimate only when it contradicts no entity.
 const allowed={0:['drawer'],1:['bowl','stove'],2:['wine','cabinet'],3:['drawer','bowl'],4:['bowl','cabinet'],5:['plate','stove'],6:['cheese','bowl'],7:['stove'],8:['bowl','plate'],9:['wine','rack']}[expected]||[];
 const entities=[['wine',/wine|bottle|酒瓶/i],['cheese',/cheese|奶酪/i],['bowl',/bowl|碗/i],['plate',/plate|盘子/i],['stove',/stove|炉灶|炉子/i],['cabinet',/cabinet|柜顶/i],['rack',/rack|酒架/i],['drawer',/drawer|抽屉/i]];
 return entities.every(([id,re])=>!re.test(reply.text)||allowed.includes(id));
}
