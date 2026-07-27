from __future__ import annotations
import math,re,wave
from collections import Counter
from pathlib import Path
from statistics import mean,median,pstdev
import numpy as np
from .common import clamp,dump

LAUGH_RE=re.compile(r'\b(ha(?:ha)+|he(?:he)+|lol|laugh(?:ing|ed|s)?|giggl(?:e|ing)|chuckl(?:e|ing)|funny|hilarious)\b',re.I)
AGREE_RE=re.compile(r'\b(yes|yeah|yep|exactly|right|true|agree|absolutely)\b',re.I)
DISAGREE_RE=re.compile(r'\b(no|nope|wrong|disagree|but actually|not really)\b',re.I)
JOKE_RE=re.compile(r'\b(joke|funny|punchline|knock knock|why did|what do you call|guess what)\b',re.I)

def acoustic_timeline(wav_path,hop_seconds=.04,window_seconds=.08):
    with wave.open(str(wav_path),'rb') as source:
        rate=source.getframerate();channels=source.getnchannels();width=source.getsampwidth();raw=source.readframes(source.getnframes())
    if width!=2:return []
    signal=np.frombuffer(raw,dtype='<i2').astype(np.float32)/32768
    if channels>1:signal=signal.reshape(-1,channels).mean(axis=1)
    hop=max(1,int(rate*hop_seconds));window=max(hop,int(rate*window_seconds));rows=[];frequencies=np.fft.rfftfreq(window,1/rate)
    for start in range(0,max(1,len(signal)-window+1),hop):
        chunk=signal[start:start+window]
        if len(chunk)<window:chunk=np.pad(chunk,(0,window-len(chunk)))
        centered=chunk-float(chunk.mean());energy=float(np.sqrt(np.mean(centered*centered)+1e-12));zcr=float(np.mean(np.signbit(centered[1:])!=np.signbit(centered[:-1])));spectrum=np.abs(np.fft.rfft(centered*np.hanning(window)));centroid=float(np.sum(frequencies*spectrum)/max(1e-9,np.sum(spectrum)));pitch=0.0;voicing=0.0
        if energy>.002:
            fft_size=1<<(2*window-1).bit_length();frequency_domain=np.fft.rfft(centered,fft_size);correlation=np.fft.irfft(frequency_domain*np.conj(frequency_domain),fft_size)[:window];lo=max(1,int(rate/400));hi=min(len(correlation)-1,int(rate/65))
            if hi>lo:
                lag=lo+int(np.argmax(correlation[lo:hi]));voicing=float(correlation[lag]/max(1e-9,correlation[0]));pitch=float(rate/lag) if voicing>.22 else 0
        rows.append({'time':round((start+window/2)/rate,4),'energy':energy,'energyNorm':0.0,'zcr':zcr,'centroid':centroid,'pitch':pitch,'voicing':voicing})
    energies=[row['energy'] for row in rows];low=float(np.percentile(energies,15)) if energies else 0;high=float(np.percentile(energies,92)) if energies else 1
    for row in rows:row['energyNorm']=round(clamp((row['energy']-low)/max(1e-6,high-low),0,1),4);row['energy']=round(row['energy'],6);row['zcr']=round(row['zcr'],4);row['centroid']=round(row['centroid'],1);row['pitch']=round(row['pitch'],2);row['voicing']=round(row['voicing'],4)
    return rows

def _speech_act(text):
    if LAUGH_RE.search(text):return 'laughter'
    if AGREE_RE.search(text):return 'agreement'
    if DISAGREE_RE.search(text):return 'disagreement'
    if '?' in text or re.search(r'\b(who|what|why|when|where|how|can you|did you|do you)\b',text,re.I):return 'question'
    if JOKE_RE.search(text):return 'joke_setup'
    return 'statement'

def build_utterances(words,max_seconds=8):
    utterances=[];current=[]
    for word in sorted(words,key=lambda row:row.get('start',0)):
        speaker=str(word.get('speaker','SPEAKER_00'))
        if current and (speaker!=str(current[-1].get('speaker')) or word['start']-current[-1]['end']>.65 or word['end']-current[0]['start']>max_seconds):
            utterances.append(_make_utterance(current,len(utterances)));current=[]
        current.append(word)
    if current:utterances.append(_make_utterance(current,len(utterances)))
    return utterances

def _make_utterance(words,index):
    text=' '.join(word.get('text','') for word in words).strip();return {'id':f'u{index}','start':round(words[0]['start'],3),'end':round(words[-1]['end'],3),'speaker':str(Counter(str(word.get('speaker','SPEAKER_00')) for word in words).most_common(1)[0][0]),'text':text,'wordCount':len(words),'speechAct':_speech_act(text),'personTrackId':None}

def _interval_features(timeline,start,end):
    rows=[row for row in timeline if start<=row['time']<=end];pitches=[row['pitch'] for row in rows if row['pitch']>0]
    return {'meanEnergy':round(mean([row['energyNorm'] for row in rows]) if rows else 0,4),'peakEnergy':round(max([row['energyNorm'] for row in rows] or [0]),4),'medianPitch':round(median(pitches) if pitches else 0,2),'pitchRange':round((max(pitches)-min(pitches)) if len(pitches)>1 else 0,2),'pitchVariation':round(pstdev(pitches) if len(pitches)>1 else 0,2),'meanCentroid':round(mean([row['centroid'] for row in rows]) if rows else 0,1),'meanZcr':round(mean([row['zcr'] for row in rows]) if rows else 0,4)}

def add_prosody(utterances,timeline):
    for utterance in utterances:
        features=_interval_features(timeline,utterance['start'],utterance['end']);duration=max(.1,utterance['end']-utterance['start']);features['wordsPerSecond']=round(utterance['wordCount']/duration,2);features['emphasis']=round(clamp(features['peakEnergy']*.65+min(1,features['pitchRange']/140)*.35,0,1),3);features['arousal']=round(clamp(features['meanEnergy']*.55+min(1,features['pitchVariation']/70)*.25+min(1,features['wordsPerSecond']/4)*.2,0,1),3);utterance['prosody']=features
    return utterances

def diarization_overlaps(segments):
    rows=[];ordered=sorted(segments,key=lambda row:row.get('start',0))
    for index,first in enumerate(ordered):
        for second in ordered[index+1:]:
            if second.get('start',0)>=first.get('end',0):break
            if second.get('speaker')==first.get('speaker'):continue
            start=max(first.get('start',0),second.get('start',0));end=min(first.get('end',0),second.get('end',0))
            if end-start>=.08:rows.append({'start':round(start,3),'end':round(end,3),'speakers':[str(first.get('speaker')),str(second.get('speaker'))],'duration':round(end-start,3)})
    return rows

def conversation_edges(utterances):
    edges=[]
    for previous,current in zip(utterances,utterances[1:]):
        if current['speaker']==previous['speaker']:continue
        overlap=previous['end']-current['start'];gap=current['start']-previous['end']
        if overlap>=.12:edges.append({'type':'interrupts','from':current['id'],'to':previous['id'],'strength':round(min(1,.55+overlap),3)})
        elif gap<=1.4:edges.append({'type':'responds_to','from':current['id'],'to':previous['id'],'strength':round(clamp(1-gap/1.4,.25,1),3)})
        if current['speechAct']=='agreement':edges.append({'type':'agrees_with','from':current['id'],'to':previous['id'],'strength':.82})
        elif current['speechAct']=='disagreement':edges.append({'type':'disagrees_with','from':current['id'],'to':previous['id'],'strength':.82})
        elif current['speechAct']=='laughter':edges.append({'type':'laughs_at','from':current['id'],'to':previous['id'],'strength':.85})
    return edges

def _visual_reactions(perception):
    rows=[]
    for frame in perception.get('frames',[]):
        participants=[str(face['personTrackId']) for face in frame.get('faces',[]) if face.get('personTrackId') and float(face.get('mouthMotion',0))>=.018]
        if participants:rows.append({'time':float(frame['time']),'participants':participants})
    return rows

def detect_reactions(audio,perception,timeline):
    candidates=[];visual=_visual_reactions(perception)
    for utterance in build_utterances(audio.get('words',[])):
        if utterance['speechAct']=='laughter':candidates.append({'start':utterance['start'],'end':utterance['end'],'sources':['transcript'],'participants':[],'confidence':.88})
    for row in visual:
        if len(row['participants'])>=2:candidates.append({'start':row['time']-.12,'end':row['time']+.3,'sources':['visual_group'],'participants':row['participants'],'confidence':.76})
    for index in range(1,len(timeline)-1):
        row=timeline[index];neighborhood=timeline[max(0,index-3):index+4];pitches=[item['pitch'] for item in neighborhood if item['pitch']>0];peaks=sum(1 for a,b,c in zip(neighborhood,neighborhood[1:],neighborhood[2:]) if b['energyNorm']>a['energyNorm'] and b['energyNorm']>c['energyNorm'] and b['energyNorm']>.55)
        if row['energyNorm']>.62 and row['zcr']>.07 and len(pitches)>=3 and pstdev(pitches)>24 and peaks>=1:candidates.append({'start':row['time']-.18,'end':row['time']+.28,'sources':['acoustic'],'participants':[],'confidence':.58})
    candidates.sort(key=lambda item:item['start']);merged=[]
    for item in candidates:
        if merged and item['start']<=merged[-1]['end']+.42:
            previous=merged[-1];previous['end']=max(previous['end'],item['end']);previous['sources']=list(dict.fromkeys(previous['sources']+item['sources']));previous['participants']=list(dict.fromkeys(previous['participants']+item['participants']));previous['confidence']=max(previous['confidence'],item['confidence'])
        else:merged.append(item.copy())
    for index,item in enumerate(merged):item['id']=f'r{index}';item['start']=round(max(0,item['start']),3);item['end']=round(item['end'],3);item['confidence']=round(clamp(item['confidence']+.08*max(0,len(item['sources'])-1)+.05*max(0,len(item['participants'])-1),0,1),3);item['groupReaction']=len(item['participants'])>=2
    return merged

def joke_chains(utterances,reactions):
    chains=[]
    for reaction in reactions:
        previous=[utterance for utterance in utterances if 0<=reaction['start']-utterance['end']<=3.2]
        if not previous:continue
        trigger=previous[-1];explicit=trigger['speechAct'] in ('joke_setup','question') or bool(JOKE_RE.search(trigger['text']))
        if explicit or reaction['confidence']>=.72:chains.append({'id':f'j{len(chains)}','setupUtteranceId':trigger['id'],'reactionId':reaction['id'],'start':trigger['start'],'end':reaction['end'],'confidence':round(min(.96,reaction['confidence']+(.12 if explicit else 0)),3),'causalHypothesis':'The preceding utterance triggered the detected reaction'})
    return chains

def attach_visible_people(social,active,out_path=None):
    frames=active.get('frames',[]);speaker_map=active.get('mapping',{});resolved={}
    for utterance in social.get('utterances',[]):
        candidates=[str(row['personTrackId']) for row in frames if utterance['start']<=row.get('time',-1)<=utterance['end'] and row.get('personTrackId')]
        person=speaker_map.get(utterance['speaker']) or (Counter(candidates).most_common(1)[0][0] if candidates else None);utterance['personTrackId']=person
        if person:resolved.setdefault(utterance['speaker'],Counter())[person]+=1
    social['speakerPersonMap']={speaker:counts.most_common(1)[0][0] for speaker,counts in resolved.items()};social['visiblePeopleAttached']=True
    if out_path:dump(out_path,social)
    return social

def build_social_intelligence(audio,perception,wav_path,out_path,progress=None):
    progress=progress or (lambda *_:None);progress('Stage 5 · extracting pitch, energy and rhythm',39);timeline=acoustic_timeline(wav_path);progress('Stage 5 · reconstructing conversational turns',42);utterances=add_prosody(build_utterances(audio.get('words',[])),timeline);edges=conversation_edges(utterances);overlap_regions=diarization_overlaps(audio.get('diarization',[]));progress('Stage 5 · detecting laughter and group reactions',46);reactions=detect_reactions(audio,perception,timeline);chains=joke_chains(utterances,reactions);overlaps=[edge for edge in edges if edge['type']=='interrupts'];data={'schemaVersion':'1.0','stage':'stage-5-social-audio-intelligence','utterances':utterances,'conversationEdges':edges,'overlapRegions':overlap_regions,'reactions':reactions,'jokeChains':chains,'summary':{'utterances':len(utterances),'interruptions':len(overlaps),'overlapRegions':len(overlap_regions),'groupReactions':sum(item['groupReaction'] for item in reactions),'jokeChains':len(chains),'speakers':sorted({item['speaker'] for item in utterances})},'acousticTimeline':[{key:row[key] for key in ('time','energyNorm','pitch','voicing')} for row in timeline[::5]],'visiblePeopleAttached':False};dump(out_path,data);return data
