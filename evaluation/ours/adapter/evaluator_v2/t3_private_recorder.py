"""Owner-published physical evidence; legacy aliases are read-only copies."""
import json
from repair6.recorder import Recorder as Parent


class Recorder(Parent):
    def _record(self, phase='passive', owner=None):
        super()._record(phase,owner)
        self.last['engine_control_step']=self.b.control_steps
        from entryfix.support import container_support
        if not hasattr(self,'support_monitor'):self.support_monitor=self.b.rt.monitor(self.b.env,6)
        self.last['measurements']['cheese']['container_support_evidence']=container_support(self.support_monitor)
        folder=self.root/'recordings'/self.b.state.episode
        folder.mkdir(parents=True,exist_ok=True)
        with (folder/'control_ticks.jsonl').open('a')as f:
            f.write(json.dumps(self.last)+'\n')
