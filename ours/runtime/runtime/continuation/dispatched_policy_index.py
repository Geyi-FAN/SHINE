"""Policy sequence advances only after an actual successful actor request.

A retired generation can propose an inference that is never sent. It must not
consume an actor sequence number. An in-flight successful request still counts
even if its returned actions are discarded by the task-version fence.
"""
import inspect,textwrap

def install(cls):
 source=textwrap.dedent(inspect.getsource(cls.start))
 old="""wire=copy.deepcopy(req);logical_call=req['evaluation_call_index'];wire['evaluation_call_index']=self.policy_calls_attempted
   if self.policy_calls_attempted>0:wire.pop('evaluation_seed',None)
   self.policy_calls_attempted+=1
   answer=self.network('policy',client.infer,wire)"""
 new="""wire=copy.deepcopy(req);logical_call=req['evaluation_call_index']
   def actual_dispatch():
    wire['evaluation_call_index']=self.policy_calls_attempted
    if self.policy_calls_attempted>0:wire.pop('evaluation_seed',None)
    answer=client.infer(wire)
    self.policy_calls_attempted+=1
    return answer
   answer=self.network('policy',actual_dispatch)"""
 assert source.count(old)==1,'frozen transport anchor drift'
 source=source.replace(old,new)
 namespace=dict(cls.start.__globals__);exec(compile(source,'<R7 actual-dispatch policy sequence>','exec'),namespace)
 cls.start=namespace['start']
