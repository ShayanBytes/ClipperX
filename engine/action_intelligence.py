from __future__ import annotations
import math,re
from collections import Counter,defaultdict
from pathlib import Path
from statistics import median
import cv2,numpy as np
from .common import center,clamp,dump

OBJECT_WORDS=('ball','dice','die','token','piece','card','puck','frisbee','goal','cup','bottle','phone')
SPORT_RE=re.compile(r'\b(penalty|kick|shoot|shot|goal|goalkeeper|keeper|score|save|miss)\w*\b',re.I)
SUCCESS_RE=re.compile(r'\b(goal|scored|scores|score|made it|went in|success|won|wins)\b',re.I)
FAIL_RE=re.compile(r'\b(miss|missed|wide|failed|lost|did not|didn.t)\b',re.I)
SAVE_RE=re.compile(r'\b(save|saved|blocked|stopped)\b',re.I)
ROLL_RE=re.compile(r'\b(roll|rolled|rolling|dice|die)\b',re.I)

def _is_action_object(name):
    name=str(name).lower();return name!='person' and any(word in name for word in OBJECT_WORDS)

def build_trajectories(perception):
    tracks=defaultdict(list)
    for frame in perception.get('frames',[]):
        for detection in frame.get('detections',[]):
            if _is_action_object(detection.get('class','')):tracks[str(detection['trackId'])].append({'time':float(frame['time']),'box':detection['box'],'center':center(detection['box']),'class':detection.get('class','object'),'confidence':float(detection.get('confidence',0)),'reportedVelocity':detection.get('worldVelocity',detection.get('velocity',[0,0]))})
    output={}
    for track,rows in tracks.items():
        rows.sort(key=lambda row:row['time']);smoothed=[]
        for index,row in enumerate(rows):
            neighbors=rows[max(0,index-1):min(len(rows),index+2)];point=[median(item['center'][axis] for item in neighbors) for axis in (0,1)];smoothed.append(point)
        for index,row in enumerate(rows):
            if index:
                dt=max(.001,row['time']-rows[index-1]['time']);finite=[(smoothed[index][axis]-smoothed[index-1][axis])/dt for axis in (0,1)]
            else:finite=[0,0]
            reported=row['reportedVelocity'];velocity=[finite[axis]*.72+float(reported[axis])*.28 for axis in (0,1)];row['smoothedCenter']=[round(value,5) for value in smoothed[index]];row['velocity']=[round(value,5) for value in velocity];row['speed']=round(math.hypot(*velocity),5)
        output[track]={'trackId':track,'class':Counter(row['class'] for row in rows).most_common(1)[0][0],'samples':rows,'start':rows[0]['time'],'end':rows[-1]['time'],'displacement':round(math.dist(smoothed[0],smoothed[-1]),5),'peakSpeed':round(max(row['speed'] for row in rows),5)}
    return output

def _moving_runs(samples,threshold):
    active=[];runs=[]
    for row in samples:
        if row['speed']>=threshold:
            if active and row['time']-active[-1]['time']>.55:
                if active:runs.append(active)
                active=[]
            active.append(row)
        elif active:
            if row['time']-active[-1]['time']<=.36:active.append(row)
            else:runs.append(active);active=[]
    if active:runs.append(active)
    merged=[]
    for run in runs:
        if merged and run[0]['time']-merged[-1][-1]['time']<=.42:merged[-1].extend(run)
        else:merged.append(run)
    return [run for run in merged if run[-1]['time']-run[0]['time']>=.12 and math.dist(run[0]['smoothedCenter'],run[-1]['smoothedCenter'])>=.018]

def _frame_near(perception,t):return min(perception.get('frames',[]),key=lambda frame:abs(frame['time']-t)) if perception.get('frames') else {'detections':[]}

def _nearest_actor(perception,t,point):
    people=[row for row in _frame_near(perception,t).get('detections',[]) if row.get('class')=='person']
    if not people:return None
    ranked=sorted((math.dist(center(row['box']),point),str(row['trackId'])) for row in people);return ranked[0][1] if ranked[0][0]<=.52 else None

def _targets(perception,t,actor,start_point,end_point):
    detections=_frame_near(perception,t).get('detections',[]);vector=np.asarray(end_point)-np.asarray(start_point);length=float(np.linalg.norm(vector));ranked=[]
    for row in detections:
        track=str(row['trackId']);name=str(row.get('class','')).lower()
        if track==actor or ('ball' in name) or ('dice' in name) or ('die'==name):continue
        point=np.asarray(center(row['box']));delta=point-np.asarray(start_point);distance=float(np.linalg.norm(delta));alignment=float(np.dot(delta,vector)/(max(1e-6,distance*length))) if length else 0;goal_bonus=.6 if 'goal' in name else 0
        if alignment>.15 and distance<.85:ranked.append((alignment+goal_bonus-distance*.25,track,name,row['box']))
    ranked.sort(reverse=True);return [{'trackId':item[1],'class':item[2],'box':item[3]} for item in ranked[:2]]

def _words(audio,start,end):return ' '.join(row.get('text','') for row in audio.get('words',[]) if start<=row.get('start',-1)<=end)

def _classify(klass,text):
    name=klass.lower()
    if 'dice' in name or name=='die' or (ROLL_RE.search(text) and any(word in name for word in ('token','piece'))):return 'dice_roll'
    if 'ball' in name and SPORT_RE.search(text):return 'sports_shot'
    if 'ball' in name:return 'projectile_action'
    if any(word in name for word in ('token','piece','card')):return 'tabletop_action'
    return 'object_action'

def _outcome(action_type,text,reached_target,settled,die_face=None):
    if SAVE_RE.search(text):return {'status':'saved','success':False,'confidence':.9,'evidence':['transcript_save']}
    if FAIL_RE.search(text):return {'status':'missed','success':False,'confidence':.86,'evidence':['transcript_failure']}
    if SUCCESS_RE.search(text):return {'status':'success','success':True,'confidence':.9,'evidence':['transcript_success']}
    if action_type=='dice_roll' and die_face:return {'status':'settled','success':None,'value':die_face['value'],'confidence':die_face['confidence'],'evidence':['motion_settled','visual_pip_count']}
    if reached_target:return {'status':'target_reached','success':True,'confidence':.72,'evidence':['trajectory_target_entry']}
    if settled:return {'status':'settled','success':None,'confidence':.62,'evidence':['trajectory_settled']}
    return {'status':'unresolved','success':None,'confidence':.35,'evidence':['insufficient_outcome_evidence']}

def count_die_pips(crop):
    if crop is None or crop.size==0:return None
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY) if crop.ndim==3 else crop;gray=cv2.resize(gray,(160,160));blur=cv2.GaussianBlur(gray,(5,5),0);circles=cv2.HoughCircles(blur,cv2.HOUGH_GRADIENT,dp=1.2,minDist=18,param1=80,param2=16,minRadius=5,maxRadius=20)
    count=0 if circles is None else len(circles[0])
    if 1<=count<=6:return {'value':count,'confidence':round(.58+count*.035,3)}
    return None

def estimate_die_face(video_path,episode):
    if episode['type']!='dice_roll':return None
    cap=cv2.VideoCapture(video_path);cap.set(cv2.CAP_PROP_POS_MSEC,episode['end']*1000);ok,frame=cap.read();cap.release()
    if not ok:return None
    sample=episode.get('_endSample');box=sample.get('box') if sample else None
    if not box:return None
    height,width=frame.shape[:2];pad=.04;x1=max(0,int((box[0]-pad)*width));y1=max(0,int((box[1]-pad)*height));x2=min(width,int((box[2]+pad)*width));y2=min(height,int((box[3]+pad)*height));return count_die_pips(frame[y1:y2,x1:x2])

def build_action_intelligence(video_path,perception,audio,out_path,progress=None):
    progress=progress or (lambda *_:None);progress('Stage 6 · reconstructing object trajectories',36);trajectories=build_trajectories(perception);progress('Stage 6 · identifying actors, releases and targets',37);episodes=[]
    duration=max([frame.get('time',0) for frame in perception.get('frames',[])] or [0])
    for track,trajectory in trajectories.items():
        threshold=.045 if any(word in trajectory['class'].lower() for word in ('dice','die','token','piece')) else .075
        for run in _moving_runs(trajectory['samples'],threshold):
            start=max(trajectory['start'],run[0]['time']-.18);end=min(duration,run[-1]['time']+.22);text=_words(audio,max(0,start-1.2),end+2);actor=_nearest_actor(perception,start,run[0]['smoothedCenter']);targets=_targets(perception,end,actor,run[0]['smoothedCenter'],run[-1]['smoothedCenter']);action_type=_classify(trajectory['class'],text);end_sample=run[-1];reached=any(target['box'][0]<=end_sample['smoothedCenter'][0]<=target['box'][2] and target['box'][1]<=end_sample['smoothedCenter'][1]<=target['box'][3] for target in targets);settled=end_sample['speed']<threshold*1.25 or end>=trajectory['end']-.25
            episode={'id':f'a{len(episodes)}','type':action_type,'start':round(start,3),'end':round(end,3),'peakTime':round(max(run,key=lambda row:row['speed'])['time'],3),'actorTrackIds':[actor] if actor else [],'objectTrackIds':[track],'targetTrackIds':[target['trackId'] for target in targets],'objectClass':trajectory['class'],'trajectory':{'displacement':round(math.dist(run[0]['smoothedCenter'],run[-1]['smoothedCenter']),4),'peakSpeed':round(max(row['speed'] for row in run),4),'startPoint':[round(value,4) for value in run[0]['smoothedCenter']],'endPoint':[round(value,4) for value in run[-1]['smoothedCenter']]},'phases':{'anticipation':[round(max(0,start-.7),3),round(start,3)],'action':[round(start,3),round(end,3)],'outcome':[round(end,3),round(min(duration,end+1.4),3)]},'keepContinuousAction':True,'transcriptEvidence':text,'_endSample':end_sample}
            die_face=estimate_die_face(video_path,episode) if action_type=='dice_roll' and settled else None;episode['outcome']=_outcome(action_type,text,reached,settled,die_face);episode['reactionIds']=[];episode['reactorTrackIds']=[];episode['mustShowTrackIds']=list(dict.fromkeys(episode['actorTrackIds']+episode['objectTrackIds']+episode['targetTrackIds']));episode['verification']={'verified':episode['outcome']['confidence']>=.6,'uncertainty':None if episode['outcome']['confidence']>=.6 else 'Outcome could not be verified from trajectory or transcript'};episode.pop('_endSample',None);episodes.append(episode)
    progress('Stage 6 · verifying action outcomes',38);report={'schemaVersion':'1.0','stage':'stage-6-action-outcome-specialists','episodes':episodes,'trajectorySummaries':[{key:value[key] for key in ('trackId','class','start','end','displacement','peakSpeed')} for value in trajectories.values()],'summary':{'episodes':len(episodes),'verifiedOutcomes':sum(item['verification']['verified'] for item in episodes),'sportsShots':sum(item['type']=='sports_shot' for item in episodes),'diceRolls':sum(item['type']=='dice_roll' for item in episodes)}};dump(out_path,report);return report

def attach_social_reactions(actions,social,out_path=None):
    for episode in actions.get('episodes',[]):
        reactions=[row for row in social.get('reactions',[]) if episode['end']-.25<=row.get('start',-1)<=episode['end']+3]
        episode['reactionIds']=[row['id'] for row in reactions];episode['reactorTrackIds']=list(dict.fromkeys(track for row in reactions for track in row.get('participants',[])));episode['mustShowTrackIds']=list(dict.fromkeys(episode.get('mustShowTrackIds',[])+episode['reactorTrackIds']))
        if reactions:episode['phases']['reaction']=[round(min(row['start'] for row in reactions),3),round(max(row['end'] for row in reactions),3)]
    actions['socialReactionsAttached']=True
    if out_path:dump(out_path,actions)
    return actions
