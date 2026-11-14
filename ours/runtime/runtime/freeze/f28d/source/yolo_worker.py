"""Persistent image-only YOLO JSON-lines worker. No simulator/GT imports."""
import os,sys,json,time
from pathlib import Path
import numpy as np
from PIL import Image
os.environ.setdefault('YOLO_CONFIG_DIR','/mnt/disk_4/geyi/yolo_v3r_3000_20261024/environment/ultralytics')
from ultralytics import YOLO
import torch
torch.set_num_threads(2)
DET_CONF=float(os.environ.get('HYBRID_DET_CONF','0.1'))
KPT_CONF=float(os.environ.get('HYBRID_KPT_CONF','0.1'))
assert 0<DET_CONF<=1 and 0<KPT_CONF<=1
# Pass a torch.device object: Ultralytics string selection overwrites UUID visibility.
DEVICE=torch.device('cuda:0')
model=YOLO(os.environ.get('HYBRID_YOLO_CHECKPOINT','/mnt/disk_4/geyi/yolo_v3r_3000_20261024/runs/yolo26s_pose_50ep/weights/best.pt'))
for line in sys.stdin:
    try:
        inp=json.loads(line);im=Image.open(inp['image']).convert('RGB');assert im.size==(256,256)
        roi=inp.get('roi')
        if roi is not None:
            assert len(roi)==4 and 0<=roi[0]<roi[2]<=256 and 0<=roi[1]<roi[3]<=256
            im=im.crop(roi).resize((256,256),Image.Resampling.BILINEAR)
        start=time.monotonic();r=model.predict(im,device=DEVICE,imgsz=640,half=True,conf=DET_CONF,iou=.7,verbose=False)[0]
        best={}
        for b,xy,kc in zip(r.boxes,r.keypoints.xy.cpu().numpy(),r.keypoints.conf.cpu().numpy()):
            name=model.names[int(b.cls.item())];conf=float(b.conf.item())
            if roi is not None and name!=inp.get('entity'):continue
            if roi is not None:xy=(xy+.5)*np.array([roi[2]-roi[0],roi[3]-roi[1]])/256+np.array(roi[:2])-.5
            if name in best and best[name]['confidence']>=conf:continue
            best[name]=dict(confidence=conf,xy=xy.tolist(),kc=kc.tolist())
        points=[]
        for entity,b in best.items():
            for j in range(3):
                # Preserve typed slots; inapplicable K slots are never substituted.
                if entity not in ('bowl','plate','cheese','wine_bottle') and j!=(0 if entity in ('middle_handle','top_handle','stove_button') else 2):continue
                p=((np.asarray(b['xy'][j])+.5)*.875-.5)[::-1]
                if b['kc'][j]<KPT_CONF or not np.isfinite(p).all() or np.any(p<0) or np.any(p>223):continue
                points.append(dict(entity=entity,keypoint='K'+str(j+1),yx224=p.tolist(),det_confidence=b['confidence'],keypoint_confidence=b['kc'][j],source='yolo_image_only'))
        print(json.dumps(dict(frame=inp['frame'],points=points,seconds=time.monotonic()-start,det_threshold=DET_CONF,keypoint_threshold=KPT_CONF)),flush=True)
    except Exception as e:print(json.dumps(dict(error=type(e).__name__+': '+str(e))),flush=True)
