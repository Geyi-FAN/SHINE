"""Read-only, identity-bound wording prefetch for a genuinely registered queue.

No plan/actions/points or hypothetical physical state is generated here. The
same wording Agent and validators run early with task text only. A result may
be reused only by the task that actually consumed that exact queue slot.
"""
import concurrent.futures,copy,hashlib,threading,time,types
from types import SimpleNamespace

def install(b,state):
 import task_language,text_transport
 original=task_language.normalize;direct=types.FunctionType(original.__code__,dict(original.__globals__,request_json=text_transport.request_json),original.__name__,original.__defaults__,original.__closure__)
 pool=concurrent.futures.ThreadPoolExecutor(max_workers=1,thread_name_prefix='waiting-wording')
 lock=threading.RLock();entries={};bound={};active=[None]
 def key_for(slot):return (state.episode,slot['deferred_id'],hashlib.sha256(slot['instruction'].encode()).hexdigest())
 def observe():
  with state.lock:slot=copy.deepcopy(state.deferred_task);previous=state.instruction
  if not slot:
   with lock:active[0]=None
   return
  key=key_for(slot)
  with lock:
   active[0]=key
   if key in entries:return
   from instructions import normalize_instruction
   raw=normalize_instruction(slot['instruction'],previous)[0]
   cfg,secret=text_transport.connection('planning');planner=SimpleNamespace(model=cfg['model'],url=cfg['chat_url'],key=secret)
   def work():
    started=time.monotonic();answer=direct(planner,raw,None)
    b.log('waiting_wording_prefetch_ready',deferred_id=key[1],seconds=time.monotonic()-started,read_only=True,observed_context_used=False)
    return answer
   entries[key]=dict(raw=raw,future=pool.submit(work));b.log('waiting_wording_prefetch_started',deferred_id=key[1],read_only=True)
 old_command=state.command
 def command(*args,**kwargs):
  result=old_command(*args,**kwargs);observe();return result
 state.command=command
 old_handoff=state._run_deferred
 def handoff(*args,**kwargs):
  with state.lock:
   slot=copy.deepcopy(state.deferred_task);previous_task=state.task_id
   result=old_handoff(*args,**kwargs)
   if slot and state.task_id!=previous_task:
    key=key_for(slot)
    with lock:
     if key in entries:bound[state.task_id]=key
    b.log('waiting_wording_bound_to_actual_successor',deferred_id=slot['deferred_id'],task_id=state.task_id)
   return result
 state._run_deferred=handoff
 def normalize(planner,raw,observed_context=None):
  with lock:key=bound.get(state.task_id);entry=entries.get(key)
  if entry and key[0]==state.episode and raw==entry['raw']:
   try:
    answer=copy.deepcopy(entry['future'].result(timeout=5))
    errors=task_language.wording_errors(raw,answer['output']['execution_task'])
    if not errors:
     answer['prefetched_for_deferred_id']=key[1];b.log('waiting_wording_prefetch_reused',deferred_id=key[1],task_id=state.task_id);return answer
   except(Exception,)as error:b.log('waiting_wording_prefetch_unavailable',reason=type(error).__name__)
  return original(planner,raw,observed_context)
 task_language.normalize=normalize
 old_close=b.close
 def close(*args,**kwargs):
  pool.shutdown(wait=False,cancel_futures=True);return old_close(*args,**kwargs)
 b.close=close
 return dict(entries=entries,bound=bound,observe=observe)
