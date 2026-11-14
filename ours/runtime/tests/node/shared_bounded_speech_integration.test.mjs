import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {synthesizeNotificationSpeech} from '../../voice/dist/realtime/notification-speech.js';

const text='当前画面中未看到网球。';
const options=()=>({endpoint:'https://example.invalid',model:'qwen3.8-omni-flash-realtime',
  purpose:'visual_result',summary:text,fixedAnnouncement:text,language:'zh-CN'});

class FakeSocket extends EventEmitter {
  constructor({stall=false,deny=false,onPartial}={}) {
    super();this.OPEN=1;this.readyState=1;this.bufferedAmount=0;
    this.stall=stall;this.onPartial=onPartial;this.closed=false;
    queueMicrotask(()=>deny?this.emit('close',1007,Buffer.from('Access denied')):
      this.message({type:'session.created',session:{id:'mock-session'}}));
  }
  message(x){this.emit('message',Buffer.from(JSON.stringify(x)),false)}
  send(raw){
    const x=JSON.parse(raw);
    queueMicrotask(()=>{
      if(this.closed)return;
      if(x.type==='session.update')this.message({type:'session.updated',session:{id:'mock-session',tools:[],enable_search:false}});
      if(x.type==='conversation.item.create')this.message({type:'conversation.item.created',item:{...x.item,status:'completed'}});
      if(x.type==='response.create'){
        this.message({type:'response.audio.delta',response_id:'mock-response',delta:Buffer.from(this.stall?[1,0]:[2,0,3,0]).toString('base64')});
        this.message({type:'response.audio_transcript.done',response_id:'mock-response',transcript:text});
        this.onPartial?.();
        if(!this.stall)this.message({type:'response.done',response:{id:'mock-response',status:'completed'}});
      }
    });
  }
  close(){this.closed=true;this.readyState=3}
  terminate(){this.close()}
}

async function sharedFlag(fn){
  const previous=process.env.ROBOT_BOUNDED_RESULT_SPEECH,legacy=process.env.ROBOT_T6_BOUNDED_SPEECH;
  process.env.ROBOT_BOUNDED_RESULT_SPEECH='1';delete process.env.ROBOT_T6_BOUNDED_SPEECH;
  try{await fn()}finally{
    if(previous===undefined)delete process.env.ROBOT_BOUNDED_RESULT_SPEECH;else process.env.ROBOT_BOUNDED_RESULT_SPEECH=previous;
    if(legacy===undefined)delete process.env.ROBOT_T6_BOUNDED_SPEECH;else process.env.ROBOT_T6_BOUNDED_SPEECH=legacy;
  }
}

test('shared activation retries a stalled real synthesis facade; first partial PCM is discarded',async()=>sharedFlag(async()=>{
  const sockets=[],events=[];
  const result=await synthesizeNotificationSpeech(options(),{createWebSocket:()=>{
    const socket=new FakeSocket({stall:sockets.length===0});sockets.push(socket);return socket;
  },onRetry:e=>events.push(e)});
  assert.equal(sockets.length,2);assert.ok(sockets[0].closed);
  assert.equal(result.transcript,text);assert.deepEqual([...result.audio],[2,0,3,0]);
  assert.equal(events.length,1);assert.equal(events[0].cause,'notification_speech_timeout');
  assert.equal(events[0].noAudioForwarded,true);assert.equal(events[0].identicalText,true);
}));

test('shared synthesis facade does not retry account refusal',async()=>sharedFlag(async()=>{
  let calls=0;
  await assert.rejects(synthesizeNotificationSpeech(options(),{createWebSocket:()=>{calls++;return new FakeSocket({deny:true})}}),
    e=>e.code==='notification_speech_access_denied');
  assert.equal(calls,1);
}));

test('new input cancellation discards partial generation without retry or returned audio',async()=>sharedFlag(async()=>{
  const controller=new AbortController();let calls=0;
  await assert.rejects(synthesizeNotificationSpeech({...options(),signal:controller.signal},{createWebSocket:()=>{
    calls++;return new FakeSocket({stall:true,onPartial:()=>controller.abort()});
  }}),e=>e.code==='notification_speech_aborted');
  assert.equal(calls,1);
}));
