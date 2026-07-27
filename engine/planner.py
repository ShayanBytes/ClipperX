from __future__ import annotations
from collections import Counter, defaultdict
from statistics import median
from .common import dump, area, center

MIN_EDITORIAL_SHOT=1.15
MAX_EDITORIAL_SHOT=7.0

def _scene_frames(scene, perception):
    return [f for f in perception.get('frames',[]) if scene['start'] <= f['time'] < scene['end']]

def _people_and_objects(frames):
    people=defaultdict(list); objects=defaultdict(list)
    for frame in frames:
        for detection in frame.get('detections',[]):
            (people if detection.get('class')=='person' else objects)[str(detection['trackId'])].append(detection)
    return people,objects

def _visible_order(people):
    return sorted(people,key=lambda track:sum(area(row['box']) for row in people[track]),reverse=True)

def _speaker_runs(scene, active):
    rows=[row for row in active.get('frames',[]) if scene['start']<=row.get('time',-1)<scene['end'] and row.get('personTrackId') and row.get('confidence',0)>=.30]
    if not rows:return []
    # A trailing vote removes one-frame face/mouth mistakes before editorial cuts are chosen.
    stable=[]
    for row in rows:
        window=[candidate for candidate in rows if row['time']-.75<=candidate['time']<=row['time']]
        scores=defaultdict(float)
        for candidate in window:scores[str(candidate['personTrackId'])]+=max(.15,float(candidate.get('confidence',0)))
        stable.append((row['time'],max(scores,key=scores.get)))
    raw=[]
    for timestamp,track in stable:
        if not raw or raw[-1]['track']!=track:raw.append({'start':timestamp,'end':timestamp,'track':track})
        else:raw[-1]['end']=timestamp
    step=median([b[0]-a[0] for a,b in zip(stable,stable[1:]) if b[0]>a[0]]) if len(stable)>1 else .25
    for index,run in enumerate(raw):run['end']=(raw[index+1]['start'] if index+1<len(raw) else min(scene['end'],run['end']+step))
    # Do not cut for a quick interjection or a noisy identity change.
    merged=[]
    for run in raw:
        if merged and run['end']-run['start']<MIN_EDITORIAL_SHOT:
            merged[-1]['end']=run['end']
        elif merged and merged[-1]['track']==run['track']:
            merged[-1]['end']=run['end']
        else:merged.append(run.copy())
    return merged

def _base_beats(scene,people,active):
    visible=_visible_order(people); duration=scene['end']-scene['start']; beats=[]
    establish=min(1.4,max(0,duration*.18)) if len(visible)>=3 and duration>=4 else 0
    if establish>=1:
        beats.append({'start':scene['start'],'end':scene['start']+establish,'mode':'group','requiredTrackIds':visible[:4],'primaryTrackId':None,'cameraPolicy':'wide_static','transition':'cut','confidence':.76,'reason':'Establish the group before dialogue coverage','eventType':'establishing'})
    cursor=scene['start']+establish
    runs=_speaker_runs(scene,active)
    for run in runs:
        start=max(cursor,run['start']);end=min(scene['end'],run['end'])
        if end-start<.55:continue
        beats.append({'start':start,'end':end,'mode':'single','requiredTrackIds':[run['track']],'primaryTrackId':run['track'],'cameraPolicy':'locked','transition':'cut','confidence':.78,'reason':'Cut directly to the stable active speaker','eventType':'dialogue'})
        cursor=end
    if not beats or cursor<scene['end']-.5:
        start=cursor if beats else scene['start']; required=visible[:min(4,len(visible))]
        mode='group' if len(required)>=3 else ('pair' if len(required)==2 else ('single' if required else 'wide'))
        beats.append({'start':start,'end':scene['end'],'mode':mode,'requiredTrackIds':required,'primaryTrackId':required[0] if len(required)==1 else None,'cameraPolicy':'wide_static' if len(required)>1 else 'locked','transition':'cut','confidence':.64,'reason':'Stable coverage while speaker evidence is uncertain','eventType':'conversation'})
    return beats

def _semantic_beats(scene,semantic,valid_tracks):
    override=semantic.get(str(scene['id'])) or semantic.get(scene['id']) or {}
    source=override.get('storyBeats') or override.get('beats') or []
    beats=[]
    for item in source:
        confidence=float(item.get('confidence',override.get('confidence',0)) or 0)
        if confidence<.55:continue
        start=float(item.get('start',item.get('relativeStart',0)))
        end=float(item.get('end',item.get('relativeEnd',scene['end']-scene['start'])))
        if start<scene['start']-.01:start+=scene['start']
        if end<=scene['end']-scene['start']+.01:end+=scene['start']
        start=max(scene['start'],start);end=min(scene['end'],end)
        if end-start<.45:continue
        requested=[str(x) for x in item.get('requiredTrackIds',item.get('requiredEntities',[]))]
        requested=[(x[1:] if len(x)>1 and x[0].upper() in ('P','O') and x[1:] in valid_tracks else x) for x in requested]
        requested=[x for x in requested if x in valid_tracks]
        primary=str(item.get('primaryTrackId')) if item.get('primaryTrackId') is not None else None
        if primary and len(primary)>1 and primary[0].upper() in ('P','O') and primary[1:] in valid_tracks:primary=primary[1:]
        if primary not in valid_tracks:primary=requested[0] if requested else None
        mode=item.get('compositionMode',item.get('mode','wide'))
        policy=item.get('cameraPolicy') or ('action_follow' if mode=='action' else ('locked' if mode=='single' else 'wide_static'))
        focus=item.get('focusPoint')
        if not (isinstance(focus,list) and len(focus)==2):focus=None
        beats.append({'start':start,'end':end,'mode':mode,'requiredTrackIds':requested,'primaryTrackId':primary,'cameraPolicy':policy,'transition':'cut','confidence':confidence,'reason':item.get('reason','Vision model identified a narrative beat'),'eventType':item.get('eventType','semantic'),'focusPoint':focus})
    return sorted(beats,key=lambda beat:beat['start'])

def _ball_actions(scene,frames,people,objects):
    ball_ids=[track for track,rows in objects.items() if rows and rows[0].get('class')=='sports ball']
    if not ball_ids:return []
    times=[]
    for frame in frames:
        if any(str(d['trackId']) in ball_ids for d in frame.get('detections',[])):times.append(frame['time'])
    if not times:return []
    groups=[]
    for timestamp in times:
        if not groups or timestamp-groups[-1][-1]>.8:groups.append([timestamp])
        else:groups[-1].append(timestamp)
    actions=[]
    for group in groups:
        start=max(scene['start'],group[0]-.45);end=min(scene['end'],group[-1]+.9)
        proximity=Counter()
        for frame in frames:
            if not start<=frame['time']<end:continue
            balls=[d for d in frame.get('detections',[]) if str(d['trackId']) in ball_ids]
            persons=[d for d in frame.get('detections',[]) if d.get('class')=='person']
            for ball in balls:
                bx,by=center(ball['box'])
                for person in persons:
                    px,py=center(person['box']); proximity[str(person['trackId'])]+=1/max(.04,abs(px-bx)+abs(py-by))
        actors=[track for track,_ in proximity.most_common(2)] or _visible_order(people)[:2]
        actions.append({'start':start,'end':end,'mode':'action','requiredTrackIds':actors+ball_ids[:1],'primaryTrackId':actors[0] if actors else None,'cameraPolicy':'action_follow','transition':'cut','confidence':.84,'reason':'Hold actor, object trajectory, and likely outcome in one stable action frame','eventType':'tracked_action'})
    return actions

def _overlay_actions(beats,actions):
    result=list(beats)
    for action in actions:
        next_beats=[]
        for beat in result:
            if beat['end']<=action['start'] or beat['start']>=action['end']:
                next_beats.append(beat);continue
            if beat['start']<action['start']-.2:next_beats.append({**beat,'end':action['start']})
            if beat['end']>action['end']+.2:next_beats.append({**beat,'start':action['end']})
        next_beats.append(action);result=sorted(next_beats,key=lambda item:item['start'])
    return result

def _normalize(scene,beats,visible):
    cleaned=[];cursor=scene['start']
    def fallback(start,end):
        required=visible[:min(4,len(visible))];mode='group' if len(required)>=3 else ('pair' if len(required)==2 else ('single' if required else 'wide'))
        return {'start':start,'end':end,'mode':mode,'requiredTrackIds':required,'primaryTrackId':required[0] if len(required)==1 else None,'cameraPolicy':'wide_static' if len(required)>1 else 'locked','transition':'cut','confidence':.56,'reason':'Safe coverage between narrative beats','eventType':'fallback'}
    for beat in sorted(beats,key=lambda item:item['start']):
        start=max(scene['start'],float(beat['start']));end=min(scene['end'],float(beat['end']))
        if start>cursor+.15:cleaned.append(fallback(cursor,start))
        start=max(start,cursor)
        if end-start<.35:continue
        required=[str(x) for x in beat.get('requiredTrackIds',[]) if x is not None]
        if not required and beat.get('mode')!='wide':required=visible[:1]
        # Split very long coverage, but keep the same framing so this does not create a visual pan.
        while end-start>MAX_EDITORIAL_SHOT:
            cleaned.append({**beat,'start':start,'end':start+MAX_EDITORIAL_SHOT,'requiredTrackIds':required})
            start+=MAX_EDITORIAL_SHOT
        cleaned.append({**beat,'start':start,'end':end,'requiredTrackIds':required});cursor=max(cursor,end)
    if cursor<scene['end']-.15:cleaned.append(fallback(cursor,scene['end']))
    return cleaned or [fallback(scene['start'],scene['end'])]

def build_shot_plans(scenes,perception,audio,active,out_path,profile='Podcast',semantic=None):
    semantic=semantic or {};plans=[];shot_index=0
    for scene in scenes:
        frames=_scene_frames(scene,perception);people,objects=_people_and_objects(frames);visible=_visible_order(people)
        valid_tracks=set(people)|set(objects)
        beats=_semantic_beats(scene,semantic,valid_tracks) or _base_beats(scene,people,active)
        beats=_overlay_actions(beats,_ball_actions(scene,frames,people,objects))
        if profile.lower()=='single' and visible:
            for beat in beats:
                if beat['mode'] not in ('action',):beat.update(mode='single',requiredTrackIds=[beat.get('primaryTrackId') or visible[0]],primaryTrackId=beat.get('primaryTrackId') or visible[0],cameraPolicy='locked')
        for beat in _normalize(scene,beats,visible):
            plans.append({**beat,'id':shot_index,'parentSceneId':scene['id'],'importantObjectIds':[track for track in beat.get('requiredTrackIds',[]) if track in objects]})
            shot_index+=1
    data={'shots':plans,'editorialPolicy':{'speakerChanges':'hard_cut','minimumShotSeconds':MIN_EDITORIAL_SHOT,'maximumShotSeconds':MAX_EDITORIAL_SHOT,'panPolicy':'dead-zone slow follow only'}}
    dump(out_path,data);return data
