from pathlib import Path
Q=Path(__file__).resolve().parents[1]
# Display the actual observation to the benchmark client, no new actor input.
p=Q/'actors/B0/code/raw_gateway.py';s=p.read_text()
needle="   if path in ['/status','/api/status']:return self.respond(200,copy.deepcopy(b.public))"
if "if path=='/api/frame.jpg':"not in s:
 s=s.replace(needle,needle+"\n   if path=='/api/frame.jpg':\n    from PIL import Image\n    image=io.BytesIO();Image.fromarray(np.ascontiguousarray(b.obs['agentview_image'][::-1,::-1])).save(image,format='JPEG');data=image.getvalue();self.send_response(200);self.send_header('Content-Type','image/jpeg');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return")
p.write_text(s)
# Complete cold JIT/VAD initialization before registering any real input.
for method in ['B0','B1']:
 p=Q/'actors'/method/'code/asr_server.py';s=p.read_text()
 needle=' vad_model=load_silero_vad();lock=asyncio.Lock();client_lock=asyncio.Lock()'
 if 'vad_warm_iterator'not in s:
  assert s.count(needle)==1
  s=s.replace(needle,needle+"\n vad_warm_iterator=VADIterator(vad_model,sampling_rate=16000,min_silence_duration_ms=400,speech_pad_ms=0)\n for _ in range(64):\n  with torch.no_grad():vad_warm_iterator(torch.zeros(512,dtype=torch.float32),return_seconds=False)\n vad_warm_iterator.reset_states()")
 p.write_text(s)
print('actual JPEG observation endpoint and pre-admission VAD warmup ready')
