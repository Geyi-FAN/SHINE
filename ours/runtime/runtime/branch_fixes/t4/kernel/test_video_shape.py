import ast,tempfile,unittest
from pathlib import Path
import numpy as np
import imageio.v2 as imageio
from t01r_video_shape import transform
B=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102')
class ActualRecording(unittest.TestCase):
    def test_only_recording_changes_real_codec_succeeds(self):
        original=ast.parse((B/'freeze/study/compat_source/run.py').read_text())
        before=ast.parse(ast.unparse(original));changed,count=transform(original)
        self.assertEqual(count,2)
        # After removing all recorder calls, the ASTs are identical: action,
        # planner, budgets, grasp events and gate activation are unchanged.
        class StripRecording(ast.NodeTransformer):
            def visit_Expr(self,node):
                if isinstance(node.value,ast.Call)and isinstance(node.value.func,ast.Attribute)and node.value.func.attr=='append_data':return ast.Pass()
                return self.generic_visit(node)
        self.assertEqual(ast.dump(StripRecording().visit(before)),ast.dump(StripRecording().visit(ast.parse(ast.unparse(changed)))))
        calls=[n for n in ast.walk(changed)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and n.func.attr=='append_data']
        obs={k:np.zeros((256,256,3),np.uint8)for k in ['agentview_image','robot0_eye_in_hand_image']}
        with tempfile.TemporaryDirectory(dir='/mnt/disk_4/geyi/t4_T01_latency_regrasp_20261104')as d:
            with imageio.get_writer(d+'/probe.mp4',fps=6,macro_block_size=16,ffmpeg_params=['-threads','1'])as writer:
                for call in calls:
                    expr=ast.Expression(body=call.args[0]);ast.fix_missing_locations(expr)
                    frame=eval(compile(expr,'actual-video-expression','eval'),{'np':np,'obs':obs,'req':{'observation/image':obs['agentview_image'],'observation/wrist_image':obs['robot0_eye_in_hand_image']}})
                    self.assertEqual(frame.shape,(256,512,3));writer.append_data(frame)
            reader=imageio.get_reader(d+'/probe.mp4');self.assertEqual(reader.count_frames(),len(calls));reader.close()
