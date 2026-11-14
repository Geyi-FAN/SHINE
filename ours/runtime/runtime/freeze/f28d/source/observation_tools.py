"""Bounded observation actions from robot proprioception, never object GT."""
import numpy as np
from hold_gate import PoseHold

class OpenThenWithdraw:
    def __init__(self,obs,controller,axis,open_steps=16,distance=.040):
        self.pose=PoseHold(obs,controller);self.axis=np.asarray(axis,float)
        self.axis/=np.linalg.norm(self.axis);self.open_steps=open_steps
        self.distance=distance;self.ticks=0;self.moved=False
    def action(self,obs):
        if self.ticks>=self.open_steps and not self.moved:
            self.pose.xyz+=self.axis*self.distance;self.moved=True
        result=self.pose.action(obs);result[6]=-1.;self.ticks+=1
        return result
