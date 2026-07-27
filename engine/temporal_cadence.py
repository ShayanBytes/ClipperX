from __future__ import annotations
import copy
from collections import Counter,defaultdict
from .common import dump

SCHEMA_VERSION='1.0'
ANALYSIS_CADENCE_SECONDS=1.0
MIN_SPEAKER_CONFIDENCE=.58


def _overlap(row,start,end):
    return float(row.get('end',row.get('start',0)))>start and float(row.get('start',0))<end


def _segment_at(segments,t):
    return next((row for row in segments if float(row.get('start',0))<=t<float(row.get('end',0))),None)


def _visible_people(perception,start,end):
    frames=[row for row in perception.get('frames',[]) if start<=float(row.get('time',-1))<end]
    observations=defaultdict(list)
    for frame in frames:
        for row in frame.get('detections',[]):
            if str(row.get('class','')).lower()!='person':continue
            observations[str(row.get('trackId'))].append(row)
    result={}
    for track,rows in observations.items():
        result[track]={'visibility':len(rows)/max(1,len(frames)),'confidence':sum(float(row.get('confidence',0)) for row in rows)/len(rows)}
    return result


def _speaker_scores(active,start,end):
    scores=defaultdict(list)
    for row in active.get('frames',[]):
        if start<=float(row.get('time',-1))<end and row.get('personTrackId'):
            scores[str(row['personTrackId'])].append(float(row.get('confidence',0)))
    return {track:sum(values)/len(values) for track,values in scores.items()}


def _boundaries(duration,scenes,segments):
    points={0.0,round(float(duration),3)}
    cursor=0.0
    while cursor<duration:
        points.add(round(cursor,3));cursor+=ANALYSIS_CADENCE_SECONDS
    for scene in scenes:
        points.add(round(max(0,min(duration,float(scene.get('start',0)))),3));points.add(round(max(0,min(duration,float(scene.get('end',duration)))),3))
    for segment in segments:
        points.add(round(max(0,min(duration,float(segment.get('start',0)))),3));points.add(round(max(0,min(duration,float(segment.get('end',duration)))),3))
    return sorted(points)


def build_temporal_cadence(composition,scenes,perception,active,duration,out_path=None,progress=None):
    """Inspect evidence every second and reset immediately at verified visual cuts.

    Directives do not force a cut every second. They expose per-second evidence to
    the renderer, which changes anchor only when a grounded speaker/performer or
    scene boundary motivates it.
    """
    progress=progress or (lambda *_:None);progress('Temporal director · second-by-second evidence scan',67)
    result=copy.deepcopy(composition);segments=result.get('segments',[]);points=_boundaries(float(duration),scenes,segments);scene_starts={round(float(row.get('start',0)),3) for row in scenes if float(row.get('start',0))>0};directives=[];last_anchor=None
    for index,(start,end) in enumerate(zip(points,points[1:])):
        if end-start<.04:continue
        segment=_segment_at(segments,(start+end)/2);visible=_visible_people(perception,start,end);speakers=_speaker_scores(active,start,end);base=[]
        if segment:
            for cell in segment.get('layout',{}).get('cells',[]):base.extend(str(track) for track in cell.get('trackIds',[]))
            base=list(dict.fromkeys([str(x) for x in segment.get('mustShowTrackIds',[])]+base))
        action=bool(segment and segment.get('keepContinuousAction'));grounded_base=[track for track in base if track in visible and visible[track]['visibility']>=.18];speaker=next((track for track,_ in sorted(speakers.items(),key=lambda item:item[1],reverse=True) if track in visible and speakers[track]>=MIN_SPEAKER_CONFIDENCE),None)
        if action and grounded_base:anchor=grounded_base[0];reason='continuous performer/action anchor checked at one-second cadence'
        elif speaker:anchor=speaker;reason='grounded active speaker checked at one-second cadence'
        elif grounded_base:anchor=grounded_base[0];reason='existing narrative anchor remains visibly grounded'
        elif last_anchor in visible and visible[last_anchor]['visibility']>=.30:anchor=last_anchor;reason='short evidence gap holds the last grounded anchor'
        else:anchor=None;reason='no grounded subject; preserve conservative source context'
        hard=round(start,3) in scene_starts
        fast=bool(anchor and anchor!=last_anchor and speaker==anchor and speakers.get(anchor,0)>=.72 and visible.get(anchor,{}).get('visibility',0)>=.45)
        if hard:reason='verified visual scene boundary; reacquire immediately from new-screen evidence'
        directives.append({'id':f'cadence-{index}','start':round(start,3),'end':round(end,3),'segmentId':segment.get('id') if segment else None,'primaryTrackIds':[anchor] if anchor else [],'speakerTrackId':speaker,'visibleTrackIds':sorted(visible),'hardAcquire':hard,'fastAcquire':fast,'generalSafe':anchor is None,'reason':reason})
        if anchor:last_anchor=anchor
    result['temporalCadence']={'schemaVersion':SCHEMA_VERSION,'analysisCadenceSeconds':ANALYSIS_CADENCE_SECONDS,'sceneCutTimes':sorted(scene_starts),'directives':directives,'policy':{'inspectEverySecond':True,'changeOnlyWhenMotivated':True,'strongSpeakerChangesAcquireImmediately':True,'sceneCutsResetCameraImmediately':True,'continuousActionPreservesPerformer':True,'gapsNeverBorrowFutureSegments':True,'silentBystandersNotPromoted':True}}
    result.setdefault('stage3Contract',{})['temporalCadenceDirector']=True
    if out_path:dump(out_path,result['temporalCadence'])
    return result
