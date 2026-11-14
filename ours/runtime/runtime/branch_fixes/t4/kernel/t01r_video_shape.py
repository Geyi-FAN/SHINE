"""Recording-only shape repair. No intermediate completion/timing changes."""
import ast
import hashlib

def transform(tree):
    removed=0
    class VideoOnly(ast.NodeTransformer):
        def visit_Call(self,node):
            nonlocal removed
            self.generic_visit(node)
            if isinstance(node.func,ast.Attribute) and node.func.attr=='append_data':
                class RawFrame(ast.NodeTransformer):
                    def visit_Call(self,call):
                        nonlocal removed
                        self.generic_visit(call)
                        if isinstance(call.func,ast.Name)and call.func.id=='resize':
                            if len(call.args)!=1 or call.keywords:raise ValueError('Unexpected video resize')
                            removed+=1
                            return call.args[0]
                        return call
                node.args=[RawFrame().visit(arg) for arg in node.args]
            return node
    tree=VideoOnly().visit(tree)
    if removed!=2:raise ValueError('Unexpected video structure: '+str(removed))
    ast.fix_missing_locations(tree)
    return tree,removed

def install(cls):
    original=cls.build_run_function
    if getattr(original,'_t01r_video_shape',False):return
    def build(bridge):
        original(bridge)
        path=bridge.root/'generated_kernel.py'
        tree,count=transform(ast.parse(path.read_text()))
        namespace=dict(bridge.run_function.__globals__)
        exec(compile(tree,str(path),'exec'),namespace)
        code=ast.unparse(tree)+'\n';path.write_text(code);bridge.run_function=namespace['run']
        bridge.log('t01r_video_shape_installed',version='raw-recording-size-v1',
            actual_kernel_guarded=True,video_resize_removed=count,
            generated_kernel_sha256=hashlib.sha256(code.encode()).hexdigest(),
            intermediate_phase_validation_changed=False,independent_score_changed=False)
    build._t01r_video_shape=True
    cls.build_run_function=build
