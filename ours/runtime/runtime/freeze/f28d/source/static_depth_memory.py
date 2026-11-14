"""Measured destination depth retained only for a valid existing M1 static epoch."""
import hashlib,json

class StaticDepthMemory:
    def __init__(self):self.values={}
    def update(self,scene,geometry,frame):
        entries={**scene.cache,**scene.anchors};active={}
        for (entity,keypoint),entry in entries.items():
            if keypoint!='K3':continue
            key=entity+'.'+keypoint
            epoch=hashlib.sha256(json.dumps(dict(visual_epoch=entry.get('epoch_id'),camera=scene.camera),sort_keys=True).encode()).hexdigest()
            active[key]=epoch
            if key in self.values and self.values[key]['epoch']!=epoch:self.values.pop(key)
            if key in geometry:
                self.values[key]=dict(xyz_m=list(geometry[key]),source_frame=frame,epoch=epoch,
                    source='measured RGB-D at YOLO K3; retained by existing M1 static validity',
                    validity_source='observable pixel-consensus cache epoch; no simulator object pose')
        for key in list(self.values):
            if key not in active:self.values.pop(key)
        return {k:dict(v) for k,v in self.values.items()}
