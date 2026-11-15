"""Read-only normalization of an output-only TTS adapter's recorded evidence.

No speech is generated. Existing transcript words, timestamps and raw files stay
unchanged. Fill only an absent audio hash after exact tag, rendered source WAV,
receiver WAV, receiver hash and sample count agree. The frozen R8 judge can then
use its already supported exact-output-key + PCM-hash path.
"""
import copy,hashlib,wave
from pathlib import Path

def pcm(path):
    with wave.open(str(path),'rb') as f:
        if (f.getframerate(),f.getnchannels(),f.getsampwidth()) != (24000,1,2):
            raise ValueError('unexpected WAV format')
        return f.readframes(f.getnframes())

def enrich(voice,messages,directory):
    answer=copy.deepcopy(voice);count=0;rejected=[]
    for e in answer:
        p=e.get('payload',{})
        if e.get('type')!='transcript.assistant' or p.get('audio_sha256') or p.get('audioSuppressed'):
            continue
        key=p.get('receipt_key','')
        if not key.startswith('tts_') or not key[4:].isdigit():
            continue
        sid=int(key[4:]);tags=[m for m in messages if m.get('type')=='host.output_audio_receipt'
            and m.get('receiptKey')==key and m.get('text')==p.get('text') and m.get('outputId')==sid]
        if len(tags)!=1:
            rejected.append(dict(key=key,reason='non_unique_exact_text_receipt'));continue
        tag=tags[0];identity=(tag.get('epoch'),sid)
        same=lambda m:(m.get('epoch'),m.get('outputId'))==identity
        receives=[m for m in messages if m.get('type')=='client.output_pcm_received' and same(m)]
        starts=[m for m in messages if m.get('type')=='host.playback_started' and same(m)
                and m.get('receiptKey')==key and not m.get('bindingUpdate')]
        if len(receives)!=1 or len(starts)!=1:
            rejected.append(dict(key=key,reason='non_unique_received_playback_identity'));continue
        try:
            source=pcm(Path(directory)/'speech'/('%03d.wav'%sid))
            received=pcm(Path(directory)/'client'/('output_%s_%s.wav'%identity))
        except (OSError,wave.Error,ValueError):
            rejected.append(dict(key=key,reason='missing_or_invalid_source_or_receiver_wav'));continue
        digest=hashlib.sha256(source).hexdigest()
        if (not source or source!=received or receives[0].get('pcm_sha256')!=digest
                or len(source)//2!=tag.get('expectedSamples')
                or len(source)//2!=receives[0].get('totalSamples')):
            rejected.append(dict(key=key,reason='source_receiver_hash_or_sample_count_mismatch'));continue
        p['audio_sha256']=digest
        e['audit_evidence_normalization']='output_only_TTS_exact_identity_source_and_receiver_PCM'
        count+=1
    return answer,dict(enriched=count,rejected=rejected)
