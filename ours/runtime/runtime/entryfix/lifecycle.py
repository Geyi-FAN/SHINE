"""A retired SOURCE kernel may not restart under a newly accepted task."""
def same_task(bridge):return bridge.task==bridge.state.task_id
def install(cls):
    hooks=cls.install_hooks
    def scoped_hooks(b):
        hooks(b);factory=b.runner.Points
        def points(*a,**kw):
            p=factory(*a,**kw)
            if not getattr(p,'_task_takeover_scope_installed',False):
                def begin(image,frame):
                    subject=tuple(b.token()[:3])
                    if getattr(p,'_task_takeover_subject',None)==subject:return
                    if b.engine_start_step>p.scene.frame:p.update_evidence(b.engine_start_step,b.cache_reader.memory_evidence(),b.cache_reader.memory_camera_id())
                    # The base method clears ONLY instruction_takeover, keeps
                    # episode memory and caches, and obtains image-only points.
                    result=b.points_class.begin_instruction(p,image,b.engine_start_step)
                    p._task_takeover_subject=subject
                    b.log('takeover_memory_bound_to_task',subject=list(subject),frame=b.engine_start_step,preserves_episode_memory=True)
                    return result
                p.begin_instruction=begin;p._task_takeover_scope_installed=True
            return p
        b.runner.Points=points
    cls.install_hooks=scoped_hooks
    start=cls.start
    def guarded(b,*a,**kw):
        if not same_task(b):
            b.log('old_kernel_restart_suppressed',retired_task_id=b.task,current_task_id=b.state.task_id,creates_completion=False)
            return None
        return start(b,*a,**kw)
    cls.start=guarded

def patch_loop(source):
    old="elif b.route=='symbolic'and b.task:"
    assert source.count(old)==1
    return source.replace(old,"elif b.route=='symbolic'and b.task and state.task_id==b.task:")
