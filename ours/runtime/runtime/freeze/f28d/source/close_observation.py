"""A measurement candidate stops manipulation while stability is observed, not scored."""
import numpy as np

def current_candidate(geometry,level,reference):
    point=geometry.get(level+'_handle.K1')
    if point is None:return None
    axis=np.asarray(reference['opening_axis'],float);axis/=np.linalg.norm(axis)
    delta=np.asarray(point)-np.asarray(reference['xyz'],float);gap=float(np.dot(delta,axis))
    residual=float(np.linalg.norm(delta-gap*axis))
    return gap if np.isfinite(gap) and residual<=.012 else None

class CloseObservation:
    def __init__(self):self.start=None;self.cooldown=-1
    def advance(self,frame,gap):
        request_view=False
        if self.start is None and frame>=self.cooldown and gap is not None and abs(gap)<=.010:self.start=frame
        if self.start is not None:
            if gap is not None and abs(gap)>.010:
                self.start=None;self.cooldown=frame+12
            elif frame-self.start>18:
                self.start=None;self.cooldown=frame+12;request_view=True
        return dict(observe=self.start is not None,ready=self.start is not None and frame-self.start>=9,
            start=self.start,request_view=request_view,current_gap_m=gap,
            note='candidate observation only, never creates a completion event')
