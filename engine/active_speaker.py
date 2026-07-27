from __future__ import annotations
from collections import defaultdict,deque
from statistics import mean
from .common import dump,area

MOUTH_ACTIVE=.014
STRONG_MOUTH=.025
DOMINANCE_MARGIN=.006
HISTORY_SECONDS=.75


def _audible(audio,t):
    return any(segment.get('start',0)<=t<=segment.get('end',0) for segment in audio.get('vad',[]))


def map_active_speakers(perception,audio,out_path):
    frames=perception.get('frames',[]);diar=audio.get('diarization',[]);trusted_diar=audio.get('diarizationSource')=='pyannote'
    output=[];current=None;candidate=None;candidate_since=0.0;last_audible_time=-99.0;last_time=0.0;speaker_face_scores=defaultdict(lambda:defaultdict(float));history=defaultdict(deque)
    for frame in frames:
        t=float(frame['time']);last_time=t;audio_label=next((segment.get('speaker') for segment in diar if segment.get('start',0)<=t<=segment.get('end',0)),None) if trusted_diar else ('VOICE' if _audible(audio,t) else None);audible=bool(audio_label)
        visible=[face for face in frame.get('faces',[]) if face.get('personTrackId')];visible_people=[str(row.get('trackId')) for row in frame.get('detections',[]) if str(row.get('class','')).lower()=='person']
        for face in visible:
            track=str(face['personTrackId']);mouth=float(face.get('mouthMotion',0));history[track].append((t,mouth));
            while history[track] and t-history[track][0][0]>HISTORY_SECONDS:history[track].popleft()
        ranked=[]
        for face in visible:
            track=str(face['personTrackId']);mouth=float(face.get('mouthMotion',0));temporal=mean(value for _,value in history[track]);support=sum(value>=MOUTH_ACTIVE for _,value in history[track]);size=min(.18,area(face['box']));score=mouth*5.2+temporal*3.0+min(4,support)*.012+size*.06;ranked.append((score,track,mouth,temporal,support,size))
        ranked.sort(reverse=True);best=ranked[0] if ranked else None;runner=ranked[1] if len(ranked)>1 else None;margin=(best[0]-runner[0]) if best else 0;mouth_dominant=bool(best and best[2]>=MOUTH_ACTIVE and (not runner or best[2]-runner[2]>=DOMINANCE_MARGIN or best[2]>=runner[2]*1.65) and (best[4]>=2 or best[2]>=STRONG_MOUTH))
        proposed=best[1] if mouth_dominant else None;body_fallback=False
        new_turn=audible and t-last_audible_time>.24
        if not audible:candidate=None
        if audible and not proposed:
            if current in visible_people:proposed=current;body_fallback=True
            elif len(visible_people)==1:proposed=visible_people[0];body_fallback=True
        # A real silence boundary resets the previous identity. Strong mouth
        # evidence can therefore acquire the new speaker immediately instead
        # of spending the first half-second on the previous person.
        if new_turn and mouth_dominant:current=proposed;candidate=None
        elif audible and proposed and proposed!=current:
            if candidate!=proposed:candidate=proposed;candidate_since=t
            persistence=t-candidate_since;threshold=.20 if best and best[2]>=STRONG_MOUTH and margin>=.035 else (.34 if mouth_dominant else (.30 if body_fallback else .72))
            if current is None or persistence>=threshold:current=proposed;candidate=None
        elif proposed==current:candidate=None
        if audible:last_audible_time=t
        confidence=0.0
        if audible and current:
            selected=next((row for row in ranked if row[1]==current),None);selected_mouth=selected[2] if selected else 0;confidence=min(.97,(.42 if body_fallback else .48)+max(0,margin)*2.0+selected_mouth*5.0+(0.08 if selected and selected[4]>=2 else 0))
        if trusted_diar and audio_label and current:speaker_face_scores[audio_label][current]+=confidence
        output.append({'time':t,'audioSpeaker':audio_label if audible else None,'personTrackId':current if audible else None,'confidence':round(confidence,3),'mouthEvidence':round(best[2],4) if best else 0,'mouthTemporalEvidence':round(best[3],4) if best else 0,'mouthDominanceMargin':round(margin,4),'candidateCount':len(ranked),'mappingEvidence':'body_continuity' if body_fallback else ('mouth_temporal_dominance' if mouth_dominant else ('ambiguous_faces' if ranked else 'none'))})
    if trusted_diar:
        mapping={speaker:max(scores,key=scores.get) for speaker,scores in speaker_face_scores.items() if scores}
        for row in output:
            if row['audioSpeaker'] in mapping and row['confidence']<.72:row['personTrackId']=mapping[row['audioSpeaker']];row['mappingEvidence']='diarization_consensus'
    else:mapping={}
    grounded=[index for index,row in enumerate(output) if row.get('personTrackId')]
    for left,right in zip(grounded,grounded[1:]):
        first,last=output[left],output[right]
        if first['personTrackId']!=last['personTrackId'] or last['time']-first['time']>1.6:continue
        for index in range(left+1,right):
            row=output[index]
            if row.get('audioSpeaker') and not row.get('personTrackId'):
                row['personTrackId']=first['personTrackId'];row['confidence']=round(min(first['confidence'],last['confidence'])*.8,3);row['mappingEvidence']='interpolated_grounded_turn'
    segments=[]
    for row in output:
        track=row.get('personTrackId')
        if not track:continue
        if not segments or segments[-1]['personTrackId']!=track:segments.append({'start':row['time'],'end':row['time'],'personTrackId':track})
        else:segments[-1]['end']=row['time']
    mapped=sum(bool(row.get('personTrackId')) for row in output if row.get('audioSpeaker'));audible_rows=sum(bool(row.get('audioSpeaker')) for row in output)
    data={'mapping':mapping,'frames':output,'segments':segments,'mappingCoverage':round(mapped/max(1,audible_rows),4),'mappingEvidence':{'mouthTemporalDominance':sum(row.get('mappingEvidence')=='mouth_temporal_dominance' for row in output),'bodyContinuity':sum(row.get('mappingEvidence')=='body_continuity' for row in output),'ambiguousFaces':sum(row.get('mappingEvidence')=='ambiguous_faces' for row in output),'diarizationConsensus':sum(row.get('mappingEvidence')=='diarization_consensus' for row in output)},'policy':{'switchPersistenceSeconds':.34,'strongSwitchSeconds':.20,'silenceTurnResetSeconds':.24,'holdThroughOcclusion':True,'usesMouthMotion':True,'usesTemporalMouthDominance':True,'rejectsLargestFaceWithoutMouthEvidence':True,'singleVisibleBodyFallback':True,'interpolateAgreedGroundedTurns':True,'neverGuessAmongMultipleBodies':True}}
    dump(out_path,data);return data
