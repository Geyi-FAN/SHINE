"""Execute actual activation sequencing statements against strict actor protocol."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

W=Path(__file__).resolve().parents[2]


class ActorSequenceTests(unittest.TestCase):
    def test_new_tasks_do_not_restart_an_existing_episode_actor_context(self):
        tree=ast.parse((W/'runtime/unified/gateway.py').read_text())
        activate=next(n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='activate')
        statements=[]
        for n in ast.walk(activate):
            if isinstance(n,ast.Assign)and any(isinstance(t,ast.Attribute)and t.attr=='policy_calls_attempted'for t in n.targets):
                statements.append(n)
            if isinstance(n,ast.Expr)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Attribute)and n.value.func.attr=='start':
                statements.append(n)
        statements.sort(key=lambda n:n.lineno)
        script=compile(ast.fix_missing_locations(ast.Module(body=statements,type_ignores=[])),'<actual task activation sequence>','exec')
        server=[]
        class Bridge:
            policy_calls_attempted=0
            def start(self,client,resume=False):
                for _ in range(2):
                    index=self.policy_calls_attempted
                    if index==0 and server:raise RuntimeError('Refuse duplicate first call')
                    if index!=len(server):raise RuntimeError('out of order')
                    server.append(index)
                    self.policy_calls_attempted+=1
        bridge=Bridge()
        for _ in range(3):exec(script,dict(b=bridge,client=object()))
        self.assertEqual(server,list(range(6)))

    def test_actor_evidence_is_issued_by_actual_transport_wrapper(self):
        tree=ast.parse((W/'runtime/unified/gateway.py').read_text())
        cls=next(n for n in ast.walk(tree)if isinstance(n,ast.ClassDef)and n.name=='Client')
        code=compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),'<actual actor evidence wrapper>','exec')
        events=[]
        class ClientBase:
            def infer(self,request):return dict(actions=[[0.]*7 for _ in range(10)])
        class Array:
            @staticmethod
            def asarray(value,dtype):return value
            float32=float
        ns=dict(SmolHTTPClient=ClientBase,b=SimpleNamespace(token=lambda:('e','t',2,3),log=lambda name,**kw:events.append((name,kw))),fingerprint=lambda _: 'actual-test-hash',np=Array)
        exec(code,ns)
        answer=ns['Client']().infer(dict(prompt='actual prompt',evaluation_call_index=7))
        self.assertEqual([e[0]for e in events],['executor_input','executor_output'])
        self.assertEqual(events[1][1]['identity'],['e','t',2,3])
        self.assertEqual(events[1][1]['action_count'],10)
        self.assertFalse(answer['paired_response_memo_hit'])
