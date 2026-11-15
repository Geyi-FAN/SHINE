import copy,hashlib,tempfile,unittest,wave
from pathlib import Path
from receipt_enrichment import enrich

class ReceiptTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.d=Path(self.tmp.name);(self.d/'speech').mkdir();(self.d/'client').mkdir();self.raw=b'\x01\x00'*2400
  self.wav(self.d/'speech/002.wav',self.raw);self.wav(self.d/'client/output_1_2.wav',self.raw)
  self.voice=[dict(type='transcript.assistant',payload=dict(text='Paused.',receipt_key='tts_2',audioSuppressed=False))]
  self.messages=[dict(type='host.output_audio_receipt',epoch=1,outputId=2,receiptKey='tts_2',text='Paused.',expectedSamples=2400),dict(type='host.playback_started',epoch=1,outputId=2,receiptKey='tts_2'),dict(type='client.output_pcm_received',epoch=1,outputId=2,pcm_sha256=hashlib.sha256(self.raw).hexdigest(),totalSamples=2400)]
 def tearDown(self):self.tmp.cleanup()
 def wav(self,p,data):
  with wave.open(str(p),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(data)
 def check_rejected(self):self.assertEqual(enrich(self.voice,self.messages,self.d)[1]['enriched'],0)
 def test_exact_received_source_evidence(self):
  old=copy.deepcopy(self.voice);new,stats=enrich(self.voice,self.messages,self.d);self.assertEqual(stats['enriched'],1);self.assertEqual(self.voice,old);self.assertEqual(new[0]['payload']['audio_sha256'],hashlib.sha256(self.raw).hexdigest())
 def test_wrong_receipt_key(self):self.messages[0]['receiptKey']='other';self.check_rejected()
 def test_wrong_text(self):self.messages[0]['text']='Resuming.';self.check_rejected()
 def test_ambiguous_receipt(self):self.messages.append(copy.deepcopy(self.messages[0]));self.check_rejected()
 def test_corrupt_receiver_wav(self):self.wav(self.d/'client/output_1_2.wav',b'\x02\x00'*2400);self.check_rejected()
 def test_missing_rendered_source(self):(self.d/'speech/002.wav').unlink();self.check_rejected()
 def test_wrong_logged_hash(self):self.messages[2]['pcm_sha256']='0'*64;self.check_rejected()
 def test_wrong_epoch(self):self.messages[2]['epoch']=2;self.check_rejected()
 def test_wrong_sample_count(self):self.messages[0]['expectedSamples']=2401;self.check_rejected()
 def test_existing_hash_not_rewritten(self):
  self.voice[0]['payload']['audio_sha256']='existing';new,stats=enrich(self.voice,self.messages,self.d);self.assertEqual(new,self.voice);self.assertEqual(stats['enriched'],0)
if __name__=='__main__':unittest.main(verbosity=2)
