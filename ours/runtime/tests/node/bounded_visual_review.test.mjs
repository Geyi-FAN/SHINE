import test,{after}from'node:test';import assert from'node:assert/strict';
import {requestBoundedReview}from'../../voice/dist/realtime/bounded-visual-review.js';
const oldFetch=globalThis.fetch;after(()=>globalThis.fetch=oldFetch);
const response=()=>new Response(JSON.stringify({answer:'verified'}));
const options=()=>({deadline:Date.now()+1000,timeoutMs:5});
function blocked(signal){return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true}));}
test('first successful review returns once',async()=>{let n=0;globalThis.fetch=async()=>{n++;return response()};assert.deepEqual(await requestBoundedReview('https://example.invalid',{body:'same'},options()),{answer:'verified'});assert.equal(n,1)});
test('a submitted review is not duplicated after timeout',async()=>{let n=0;let events=[];globalThis.fetch=async(u,o)=>{n++;return blocked(o.signal)};await assert.rejects(requestBoundedReview('https://example.invalid',{method:'POST',body:'same-image-and-prompt'},{...options(),onRetry:e=>events.push(e)}));assert.equal(n,1);assert.equal(events.length,0)});
test('default review uses remaining total budget instead of an unrelated short limit',async()=>{let n=0;globalThis.fetch=async()=>{n++;await new Promise(r=>setTimeout(r,30));return response()};assert.deepEqual(await requestBoundedReview('https://example.invalid',{},{deadline:Date.now()+500}),{answer:'verified'});assert.equal(n,1)});
test('HTTP authorization errors are not retried',async()=>{let n=0;globalThis.fetch=async()=>{n++;return new Response('',{status:403})};await assert.rejects(requestBoundedReview('https://example.invalid',{},options()),/403/);assert.equal(n,1)});
test('parent cancellation never triggers retry',async()=>{let n=0;const c=new AbortController();globalThis.fetch=async(u,o)=>{n++;queueMicrotask(()=>c.abort());return blocked(o.signal)};await assert.rejects(requestBoundedReview('https://example.invalid',{},{...options(),signal:c.signal}));assert.equal(n,1)});
test('already aborted parent makes no request',async()=>{let n=0;const c=new AbortController();c.abort();globalThis.fetch=async()=>{n++;return response()};await assert.rejects(requestBoundedReview('https://example.invalid',{},{...options(),signal:c.signal}));assert.equal(n,0)});
test('expired total budget makes no request',async()=>{let n=0;globalThis.fetch=async()=>{n++;return response()};await assert.rejects(requestBoundedReview('https://example.invalid',{},{deadline:Date.now()-1}));assert.equal(n,0)});
test('malformed review JSON is not retried or returned as a candidate',async()=>{let n=0;globalThis.fetch=async()=>{n++;return new Response('not JSON')};await assert.rejects(requestBoundedReview('https://example.invalid',{},options()));assert.equal(n,1)});
