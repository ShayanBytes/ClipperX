from __future__ import annotations
import os, subprocess
from pathlib import Path
from .common import dump

def analyze_audio(video_path,out_path,out_dir,model='base',language=None,hf_token=None):
    wav=str(Path(out_dir,'audio.wav'))
    subprocess.run(['ffmpeg','-y','-i',video_path,'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',wav],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    from faster_whisper import WhisperModel
    whisper=WhisperModel(model,device='cpu',compute_type='int8')
    segments,info=whisper.transcribe(wav,language=language,word_timestamps=True,vad_filter=True,beam_size=3)
    words=[]; vad=[]; text=[]
    for seg in segments:
        vad.append({'start':seg.start,'end':seg.end,'confidence':1.0}); text.append(seg.text.strip())
        for word in seg.words or []:
            words.append({'start':round(word.start,3),'end':round(word.end,3),'text':word.word.strip(),'probability':round(word.probability,4),'speaker':'SPEAKER_00'})
    diarization=_diarize(wav,hf_token)
    if diarization:
        for word in words:
            midpoint=(word['start']+word['end'])/2
            match=next((s for s in diarization if s['start']<=midpoint<=s['end']),None)
            if match: word['speaker']=match['speaker']
    data={'language':info.language,'languageProbability':info.language_probability,'text':' '.join(text),'words':words,'vad':vad,'diarization':diarization or _speaker_segments(words),'diarizationSource':'pyannote' if diarization else 'voice-activity-fallback'}
    dump(out_path,data); return data

def _diarize(wav,token):
    if not token: return []
    try:
        from pyannote.audio import Pipeline
        pipe=Pipeline.from_pretrained('pyannote/speaker-diarization-3.1',use_auth_token=token)
        result=pipe(wav); return [{'start':round(turn.start,3),'end':round(turn.end,3),'speaker':speaker} for turn,_,speaker in result.itertracks(yield_label=True)]
    except Exception: return []

def _speaker_segments(words):
    if not words:return []
    return [{'start':words[0]['start'],'end':words[-1]['end'],'speaker':'SPEAKER_00'}]
