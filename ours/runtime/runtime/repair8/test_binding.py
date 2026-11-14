import hashlib,tempfile,unittest,wave,os
from pathlib import Path
from repair8.audible_binding import bound_output
class Binding(unittest.TestCase):
 def test_queued_output_bound_without_two_second_guess(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'client';p.mkdir();pcm=b'\x01\x00'*100
   with wave.open(str(p/'output_1_3.wav'),'wb')as f:f.setparams((1,2,24000,0,'NONE',''));f.writeframes(pcm)
   transcript=dict(receipt_key='result:2',audio_sha256=hashlib.sha256(pcm).hexdigest())
   messages=[dict(type='host.playback_started',direction='sent',epoch=1,outputId=3,time=20),dict(type='host.playback_started',direction='sent',epoch=1,outputId=3,time=20.1,bindingUpdate=True,receiptKey='result:2')]
   self.assertEqual(len(bound_output(transcript,messages,d)),1)
   transcript['audio_sha256']='wrong';self.assertFalse(bound_output(transcript,messages,d))
 def test_binding_update_cannot_fake_actual_start(self):
  self.assertFalse(bound_output(dict(receipt_key='k',audio_sha256='h'),[dict(type='host.playback_started',direction='sent',epoch=1,outputId=3,bindingUpdate=True,receiptKey='k')]))
 def test_wrong_key_cannot_bind(self):
  self.assertFalse(bound_output(dict(receipt_key='new',audio_sha256='h'),[dict(type='host.playback_started',direction='sent',epoch=1,outputId=3,receiptKey='old')]))
if __name__=='__main__':unittest.main()
