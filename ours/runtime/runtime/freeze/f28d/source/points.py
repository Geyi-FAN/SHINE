import json,os,subprocess,time
from pathlib import Path
import numpy as np
import atexit
_WORKER=None
_WORKER_LOG=None
from PIL import Image
from scene_memory import SceneMemory

class Points:
    def __init__(self,folder,episode_id=None,episode_frame_at_takeover=None):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True);self.memory={};self.current={};self.frame=None;self.timings=[]
        self.episode_id=episode_id or self.folder.parent.name
        self.episode_frame_at_takeover=episode_frame_at_takeover
        self.instruction_version=0
        self.last_image_points={};self.required_reference=None
        self.scene=SceneMemory(self.folder/'memory_events.jsonl',enabled=os.environ.get('HYBRID_STATIC_CACHE','1')=='1',episode_id=self.episode_id)
        self.camera_id='main256-to224-fixed-v1'
        self.history_camera={}
        global _WORKER,_WORKER_LOG
        if _WORKER is None or _WORKER.poll() is not None:
            shared=Path(os.environ['P012_ROOT'])/'logs'/('yolo_'+str(os.getpid())+'.log')
            _WORKER_LOG=open(shared,'w')
            _WORKER=subprocess.Popen([os.environ.get('HYBRID_YOLO_PYTHON','/mnt/disk_3/geyi/miniconda3/envs/rexomni/bin/python'),str(Path(__file__).with_name('yolo_worker.py'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=_WORKER_LOG,text=True,bufsize=1,env=dict(os.environ,CUDA_VISIBLE_DEVICES=os.environ.get('HYBRID_YOLO_CUDA_VISIBLE_DEVICES',os.environ.get('CUDA_VISIBLE_DEVICES',''))))
            atexit.register(lambda p=_WORKER:p.terminate() if p.poll() is None else None)
        self.proc=_WORKER

    def observe(self,image,frame,time_source='current',camera_id=None):
        p=self.folder/(str(frame)+'_'+time_source+'.png');Image.fromarray(np.asarray(image,dtype=np.uint8)).save(p)
        self.proc.stdin.write(json.dumps(dict(image=str(p),frame=frame))+'\n');self.proc.stdin.flush()
        while True:
            line=self.proc.stdout.readline()
            if not line:raise RuntimeError('YOLO worker exited')
            try:r=json.loads(line)
            except ValueError:continue
            if isinstance(r,dict) and ('points' in r or 'error' in r):break
        if 'error' in r:raise RuntimeError(r['error'])
        assert r['frame']==frame
        # A fresh full-image miss may trigger ONE image-only local reacquisition.
        # The crop comes from a past visual point, never simulator coordinates.
        ref=self.required_reference
        if time_source=='current' and os.environ.get('REPAIR_ROI_YOLO','0')=='1' and ref and ref['time_source']=='current' and ref['keypoint']=='K3' and ref['entity'] in ('bowl','plate'):
            key=(ref['entity'],ref['keypoint']);present=any((v['entity'],v['keypoint'])==key for v in r['points'])
            previous=self.last_image_points.get(key)
            if not present and previous is not None and 0<frame-previous['frame']<=48:
                y,x=((np.asarray(previous['yx224'])+.5)/.875-.5)
                left=max(0,min(160,int(round(x))-48));top=max(0,min(160,int(round(y))-48));box=[left,top,left+96,top+96]
                self.proc.stdin.write(json.dumps(dict(image=str(p),frame=frame,roi=box,entity=ref['entity']))+'\n');self.proc.stdin.flush()
                while True:
                    line=self.proc.stdout.readline()
                    if not line:raise RuntimeError('YOLO crop worker exited')
                    try:local=json.loads(line)
                    except ValueError:continue
                    if isinstance(local,dict) and ('points' in local or 'error' in local):break
                if 'error' in local:raise RuntimeError(local['error'])
                assert local['frame']==frame
                additions=[dict(v,roi_reacquisition=True,roi_MAIN256=box) for v in local['points'] if (v['entity'],v['keypoint'])==key]
                r['points'].extend(additions);r['seconds']+=local['seconds']
                self.scene.log('image_roi_reacquisition',entity=ref['entity'],keypoint=ref['keypoint'],source_frame=frame,search_reference_frame=previous['frame'],roi_MAIN256=box,returned_points=len(additions),oracle_pixel_used=False)
        if (time_source=='current' and os.environ.get('REPAIR_ROI_YOLO','0')=='1'
                and ref and ref.get('time_source')=='current' and ref.get('keypoint')=='K1'
                and not any((v['entity'],v['keypoint'])==(ref['entity'],ref['keypoint']) for v in r['points'])):
            from unified.image_reacquisition import reacquire
            additions,audit=reacquire(self.proc,p,frame,ref,
                self.last_image_points.get((ref['entity'],ref['keypoint'])),
                r.get('det_threshold',.1),r.get('keypoint_threshold',.1))
            r['points'].extend(additions);r['seconds']+=audit.get('seconds',0.)
            self.scene.log('image_multiscale_reacquisition',entity=ref['entity'],
                           keypoint=ref['keypoint'],**audit)
        if time_source=='current':
            for value in r['points']:
                self.last_image_points[(value['entity'],value['keypoint'])]=dict(value,frame=frame)
        episode_frame=0 if time_source=='episode_start' else (None if self.episode_frame_at_takeover is None else self.episode_frame_at_takeover+frame)
        if episode_frame is not None:r['points']=[dict(p,source_episode_frame=episode_frame) for p in r['points']]
        self.timings.append(r['seconds'])
        values={(time_source,x['entity'],x['keypoint']):dict(x,time_source=time_source,frame=frame) for x in r['points']}
        if time_source=='current':
            self.current=values;self.frame=frame
            self.scene.ingest(r['points'],frame)
        else:
            if any(k[0]==time_source for k in self.memory):raise ValueError('Historical memory already frozen')
            self.memory.update(values)
            self.history_camera[time_source]=camera_id or self.camera_id
            if time_source=='episode_start':self.scene.seed_episode(r['points'],frame,self.history_camera[time_source])
        with (self.folder/'detections.jsonl').open('a') as f:f.write(json.dumps(dict(time_source=time_source,**r))+'\n')
    def transfer_episode_objects(self,evidence):
        points=[p for (time_source,_,_),p in self.memory.items() if time_source=='episode_start']
        self.scene.import_episode_objects(points,evidence['facts'],evidence['camera_transform_id'],evidence['episode_id'])
    def initialize_episode(self,image,facts,camera_id):
        """Live episode start. Called once, before the first user instruction."""
        if 'episode_start' in self.history_camera or self.scene.frame>0:
            raise ValueError('Episode already initialized; switch instructions without clearing memory')
        if self.episode_frame_at_takeover is None:self.episode_frame_at_takeover=0
        self.update_evidence(0,facts,camera_id)
        self.observe(image,-1,'episode_start',camera_id=camera_id)
        self.transfer_episode_objects(dict(episode_id=self.episode_id,camera_transform_id=camera_id,facts=facts))
    def begin_instruction(self,image,frame):
        """Only takeover K2 is renewed; episode memories and scene caches survive."""
        if frame!=self.scene.frame:raise ValueError('update current evidence before instruction switch')
        self.memory={k:v for k,v in self.memory.items() if k[0]!='instruction_takeover'}
        self.history_camera.pop('instruction_takeover',None)
        self.instruction_version+=1
        self.scene.log('instruction_switch',instruction_version=self.instruction_version,episode_id=self.episode_id,
                       preserved_object_slots=len(self.scene.cache),preserved_fixed_slots=len(self.scene.anchors))
        self.observe(image,frame,'instruction_takeover')
    def update_evidence(self,frame,facts,camera_id):
        self.camera_id=camera_id
        self.scene.evidence(frame,None,camera_id)
        if hasattr(self,'folder'):
            with (self.folder/'cache_validity_private.jsonl').open('a') as f:f.write(json.dumps(dict(frame=frame,camera=camera_id,validity_source='observable_only'))+'\n')
    def resolve(self,t,e,k):
        if t=='current':return self.scene.resolve(e,k)
        if self.history_camera.get(t)!=self.camera_id:return None,'missing'
        return self.memory.get((t,e,k)),'historical'
    def available(self,catalog):
        refs={tuple(o['reference'].get(k) for k in ('time_source','entity','keypoint')) for o in catalog.values() if o['reference']}
        return [dict(time_source=t,entity=e,keypoint=k,available=self.resolve(t,e,k)[0] is not None) for t,e,k in sorted(refs)]
    def bind(self,decision,frame):
        r=decision['reference']
        self.required_reference=r
        if r is None:
            from planner import CATALOG
            if frame!=self.frame or frame!=self.scene.frame:raise ValueError('image and evidence frame mismatch')
            assert CATALOG[decision['remaining_plan'][0]['operation']]['reference'] is None
            text=decision['policy_prompt_template']
            if '{' in text or '}' in text:raise ValueError('unbound reference')
            return text,dict(yx=None,valid=False,source='no_point_operator',reference=None)
        key=(r['time_source'],r['entity'],r['keypoint'])
        if frame!=self.frame or frame!=self.scene.frame:raise ValueError('image and evidence frame mismatch')
        p,status=self.resolve(*key)
        offset=getattr(self,'episode_frame_at_takeover',None)
        observation_episode_frame=None if offset is None else offset+frame
        source_episode_frame=None if p is None else p.get('source_episode_frame')
        episode_age=observation_episode_frame is not None and source_episode_frame is not None
        age=None if p is None else observation_episode_frame-source_episode_frame if episode_age else frame-p['frame']
        clock=dict(source_episode_frame=source_episode_frame,observation_episode_frame=observation_episode_frame,
                   age_steps=age,age_clock='episode' if episode_age else 'control_frame_initial_sentinel')
        self.scene.log('resolve',reference=r,resolution=status,source_frame=None if p is None else p['frame'],cache_kind=None if p is None else p.get('cache_kind','rolling_static'),source_time_source=None if p is None else p.get('time_source',key[0]),det_confidence=None if p is None else p.get('det_confidence'),keypoint_confidence=None if p is None else p.get('keypoint_confidence'),**clock)
        if p is None:raise ValueError('required YOLO point unavailable; no valid static cache; no GT fallback')
        point=np.asarray(p['yx224'],float)
        if point.shape!=(2,) or not np.isfinite(point).all() or (point<0).any() or (point>223).any():raise ValueError('invalid YOLO point')
        yx=np.rint(point).astype(int).tolist()
        text=decision['policy_prompt_template'].replace('{'+'.'.join(key)+'}','<'+','.join(map(str,yx))+'>')
        if '{' in text or '}' in text:raise ValueError('unbound reference')
        return text,dict(yx=yx,valid=False,source='yolo',reference=r,source_frame=p['frame'],resolution=status,cache_kind=p.get('cache_kind','rolling_static' if status!='historical' else 'historical_target'),source_time_source=p.get('time_source',key[0]),camera_transform_id=self.camera_id,**clock)
    def close(self):
        # Worker is shared sequentially within one process, never across processes.
        pass
