/** Retry bounded read-only local observations, never a mutation or audio upload. */
import {performance} from 'node:perf_hooks';
const sleep = ms => new Promise(resolve => setTimeout(resolve,ms));
export class ObservationTransportError extends Error {
 constructor(message, details) { super(message); this.name='ObservationTransportError'; this.details=details; }
}
export async function readOnlyJson(url, {headers={}, budgetMs=7000, maxAttempts=6,
 fetchImpl=fetch, onEvent=()=>{}, now=()=>performance.now(), wait=sleep}={}) {
 const parsed=new URL(url);
 if(parsed.protocol!=='http:' || !['127.0.0.1','localhost'].includes(parsed.hostname))
  throw new Error('observation_endpoint_must_be_loopback');
 const end=now()+budgetMs;
 let last;
 for(let attempt=1; attempt<=maxAttempts && now()<end; attempt++) {
  try {
   const response=await fetchImpl(url,{method:'GET',headers,
    signal:AbortSignal.timeout(Math.max(1,Math.ceil(end-now())))});
   if(!response.ok) {
    const error=new Error('status HTTP '+response.status);error.httpStatus=response.status;
    throw error;
   }
   return await response.json(); // body disconnects must also enter retry handling
  } catch(error) {
   const status=error.httpStatus;
   const transient=status ? [502,503,504].includes(status) :
    ['TypeError','TimeoutError','AbortError','SyntaxError'].includes(error.name) ||
    ['ECONNRESET','ECONNREFUSED','UND_ERR_SOCKET','UND_ERR_CONNECT_TIMEOUT'].includes(error.code);
   last={path:parsed.pathname,attempt,status:status??null,name:error.name,
    message:String(error.message).slice(0,300),cause_code:error.cause?.code??error.code??null,
    remaining_ms:Math.max(0,end-now()),read_only:true};
   const retry=transient && attempt<maxAttempts && now()+100*attempt<end;
   onEvent({...last,event:retry?'observation_retry':'observation_failed',retry});
   if(!retry) throw new ObservationTransportError('observation_unavailable:'+parsed.pathname,last);
   await wait(100*attempt);
  }
 }
 throw new ObservationTransportError('observation_deadline:'+parsed.pathname,last);
}
