"""Bounded Python-shaped recovery programs; AST interpretation, never exec/eval."""
import ast
import math

PROPERTIES={'hand_empty','target_visible','target_supported','outside_destination','clear_upward','target_dx_m','target_dy_m','target_dz_m','operation','stage_kind','target_xy_norm_m','target_xy_unit_x','target_xy_unit_y'}
TOOLS={'move_relative':{'dx_m','dy_m','dz_m'},'rotate_relative':{'roll_deg','pitch_deg','yaw_deg'},
       'open_gripper':set(),'observe':{'steps'},'retry_subgoal':set(),'replan_current_task':set()}


class InvalidProgram(ValueError):pass


def refresh_vector_properties(context):
    """Derived coordinates only; never creates a tool call or permission."""
    if 'target_xy_norm_m'not in context:return context
    x,y=context.get('target_dx_m'),context.get('target_dy_m')
    valid=context.get('target_visible')is True and all(type(v)in(int,float)and math.isfinite(v)for v in(x,y))
    length=math.hypot(x,y)if valid else None
    context.update(target_xy_norm_m=length,target_xy_unit_x=None if length is None else x/length if length else 0.,target_xy_unit_y=None if length is None else y/length if length else 0.)
    return context


class Program:
    def __init__(self,text,trace_conditions=False):
        self.trace_conditions=trace_conditions;self.condition_trace=[]
        if not isinstance(text,str)or len(text)>5000:raise InvalidProgram('Program must be <=5000characters')
        try:self.tree=ast.parse(text)
        except SyntaxError as exc:raise InvalidProgram('Invalid Python syntax')from exc
        if len(list(ast.walk(self.tree)))>180:raise InvalidProgram('AST node budget')
        if len(self.tree.body)!=1 or not isinstance(self.tree.body[0],ast.FunctionDef):raise InvalidProgram('One recover(ctx) function required')
        f=self.tree.body[0]
        if f.name!='recover'or[f.arg for f in f.args.args]!=['ctx']or any(a.annotation is not None for a in f.args.args)or f.decorator_list or f.returns or f.args.defaults or f.args.vararg or f.args.kwarg or f.args.kwonlyargs or f.args.posonlyargs:
            raise InvalidProgram('Use def recover(ctx), no decorators/annotations/defaults')
        self.calls=0;self._statements(f.body)
        if not self.calls or self.calls>8:raise InvalidProgram('Use1..8bounded tool calls')
        self.stack=list(reversed(f.body));self.finished=False;self.replan=False

    def _expr(self,node):
        if isinstance(node,ast.Constant):
            if not isinstance(node.value,(bool,int,float,str))or isinstance(node.value,str)and len(node.value)>80:raise InvalidProgram('Unsupported constant')
            if isinstance(node.value,(int,float))and(not math.isfinite(node.value)or abs(node.value)>100):raise InvalidProgram('Unbounded numeric constant')
        elif isinstance(node,ast.Attribute):
            if not isinstance(node.value,ast.Name)or node.value.id!='ctx'or node.attr not in PROPERTIES:raise InvalidProgram('Unknown/read-write context access')
        elif isinstance(node,ast.UnaryOp)and isinstance(node.op,(ast.Not,ast.UAdd,ast.USub)):self._expr(node.operand)
        elif isinstance(node,ast.BoolOp)and isinstance(node.op,(ast.And,ast.Or)):
            for x in node.values:self._expr(x)
        elif isinstance(node,ast.Compare):
            if any(not isinstance(x,(ast.Eq,ast.NotEq,ast.Lt,ast.LtE,ast.Gt,ast.GtE))for x in node.ops):raise InvalidProgram('Unsupported comparison')
            self._expr(node.left)
            for x in node.comparators:self._expr(x)
        elif isinstance(node,ast.BinOp)and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            self._expr(node.left);self._expr(node.right)
        elif isinstance(node,ast.Call)and isinstance(node.func,ast.Name)and node.func.id in ('min','max','abs')and not node.keywords and 1<=len(node.args)<=3:
            for x in node.args:self._expr(x)
        else:raise InvalidProgram('Expression not in the recovery language')

    def _statements(self,body):
        for node in body:
            if isinstance(node,ast.If):self._expr(node.test);self._statements(node.body);self._statements(node.orelse)
            elif isinstance(node,ast.Expr)and isinstance(node.value,ast.Call):
                c=node.value;f=c.func
                if not isinstance(f,ast.Attribute)or not isinstance(f.value,ast.Name)or f.value.id!='ctx'or f.attr not in TOOLS or c.args:
                    raise InvalidProgram('Only documented ctx tools with keyword arguments')
                names=[x.arg for x in c.keywords]
                if None in names or len(names)!=len(set(names))or not set(names)<=TOOLS[f.attr]:raise InvalidProgram('Invalid tool parameters')
                for k in c.keywords:self._expr(k.value)
                self.calls+=1
            else:raise InvalidProgram('Only if/else and bounded ctx tool calls; no imports, loops, assignment or external access')

    def value(self,node,ctx):
        if isinstance(node,ast.Constant):return node.value
        if isinstance(node,ast.Attribute):return ctx[node.attr]
        if isinstance(node,ast.UnaryOp):
            a=self.value(node.operand,ctx)
            return not a if isinstance(node.op,ast.Not)else -a if isinstance(node.op,ast.USub)else+a
        if isinstance(node,ast.BoolOp):
            if isinstance(node.op,ast.And):return all(self.value(x,ctx)for x in node.values)
            return any(self.value(x,ctx)for x in node.values)
        if isinstance(node,ast.BinOp):
            a,b=self.value(node.left,ctx),self.value(node.right,ctx)
            if type(a)not in(int,float)or type(b)not in(int,float)or not all(math.isfinite(x)and abs(x)<=1e6 for x in(a,b)):raise InvalidProgram('Arithmetic requires bounded finite numbers')
            if isinstance(node.op,ast.Add):return a+b
            if isinstance(node.op,ast.Sub):return a-b
            if isinstance(node.op,ast.Mult):return a*b
            if b==0:raise InvalidProgram('Division by zero')
            return a/b
        if isinstance(node,ast.Call):
            values=[self.value(x,ctx)for x in node.args]
            if any(type(x)not in(int,float)or not math.isfinite(x)or abs(x)>1e6 for x in values):raise InvalidProgram('Numeric helper requires bounded numbers')
            try:return {'min':min,'max':max,'abs':abs}[node.func.id](*values)
            except(TypeError,ValueError)as exc:raise InvalidProgram('Invalid numeric helper arguments')from exc
        if isinstance(node,ast.Compare):
            left=self.value(node.left,ctx)
            for op,c in zip(node.ops,node.comparators):
                right=self.value(c,ctx)
                ok=left==right if isinstance(op,ast.Eq)else left!=right if isinstance(op,ast.NotEq)else left<right if isinstance(op,ast.Lt)else left<=right if isinstance(op,ast.LtE)else left>right if isinstance(op,ast.Gt)else left>=right
                if not ok:return False
                left=right
            return True
        raise InvalidProgram('Invalid expression')

    def next(self,ctx):
        """Called again after each motion, with NEW observed context."""
        while self.stack:
            node=self.stack.pop()
            if isinstance(node,ast.If):
                result=self.value(node.test,ctx)
                if self.trace_conditions:
                    names=sorted({x.attr for x in ast.walk(node.test)if isinstance(x,ast.Attribute)})
                    self.condition_trace.append(dict(line=node.lineno,expression=ast.unparse(node.test),values={k:ctx[k]for k in names},result=bool(result)))
                self.stack.extend(reversed(node.body if result else node.orelse));continue
            c=node.value;name=c.func.attr;args={k.arg:self.value(k.value,ctx)for k in c.keywords}
            for v in args.values():
                if type(v)not in(int,float)or not math.isfinite(v):raise InvalidProgram('Motion parameters must be finite numbers')
            if name=='retry_subgoal':self.stack=[];self.finished=True;return None
            if name=='replan_current_task':
                if ctx['stage_kind']!='target'or not(ctx['hand_empty']and ctx['target_supported']and ctx['outside_destination']):raise InvalidProgram('Replan requires observed empty hand and supported object outside destination during placement')
                self.replan=True;self.stack=[];self.finished=True;return None
            return dict(tool=name,arguments=args)
        self.finished=True;return None


class MotionBudget:
    def __init__(self):self.translation_m=0.;self.rotation_deg=0.;self.commands=0
    def authorize(self,command,ctx):
        tool,args=command['tool'],command['arguments']
        if not ctx['hand_empty']:raise InvalidProgram('Recovery reposition needs currently certified EMPTY hand')
        if tool=='move_relative':
            x,y,z=(args.get(k,0.)for k in ['dx_m','dy_m','dz_m'])
            if math.hypot(x,y)>.015 or not -.010<=z<=.030:raise InvalidProgram('Translation exceeds per-command bound')
            size=math.sqrt(x*x+y*y+z*z)
            if self.translation_m+size>.065:raise InvalidProgram('Cumulative translation bound')
            if z>0 and not ctx['clear_upward']:raise InvalidProgram('No current visible upward clearance')
            if z<0 and(not ctx['target_visible']or ctx['target_dz_m']-z>-.030):raise InvalidProgram('Downward correction must retain >=3cm observed target clearance')
            if math.hypot(x,y)>0 and(not ctx['target_visible']or not ctx['target_supported']or ctx['target_dz_m']>-.040):raise InvalidProgram('Horizontal correction requires target visible/supported and hand >=4cm above its reference')
            self.translation_m+=size
        elif tool=='rotate_relative':
            r,p,y=(args.get(k,0.)for k in ['roll_deg','pitch_deg','yaw_deg'])
            size=math.sqrt(r*r+p*p+y*y)
            if abs(r)>8 or abs(p)>8 or abs(y)>15 or self.rotation_deg+size>22:raise InvalidProgram('Rotation exceeds bound')
            if not ctx['clear_upward']or ctx['target_dz_m']>-.040:raise InvalidProgram('Rotate only with observed clearance above the supported target')
            self.rotation_deg+=size
        elif tool=='observe':
            if not 4<=args.get('steps',8)<=12 or int(args.get('steps',8))!=args.get('steps',8):raise InvalidProgram('Observation needs4..12control steps')
        elif tool!='open_gripper':raise InvalidProgram('Unknown executable tool')
        self.commands+=1
        if self.commands>8:raise InvalidProgram('Too many commands')


def preflight(text,context):
    """Reject bounds on the currently traversed path before ANY motion.

    This is validation, not simulated completion. Every live tool and conditional
    is checked again with measured observations during actual execution.
    """
    p=Program(text);b=MotionBudget();c=dict(context);commands=[]
    for _ in range(9):
        cmd=p.next(c)
        if cmd is None:return commands
        b.authorize(cmd,c);commands.append(cmd)
        if cmd['tool']=='move_relative':
            for axis in ('x','y','z'):c['target_d'+axis+'_m']-=cmd['arguments'].get('d'+axis+'_m',0.)
            refresh_vector_properties(c)
    raise InvalidProgram('Preflight command budget')
