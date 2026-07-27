from __future__ import annotations
import math,os
from collections import Counter,defaultdict
from pathlib import Path
from statistics import median
import cv2,numpy as np
from .common import center,dump,iou,cancelled

OPEN_VOCAB_PROMPTS=['dice','die','board game piece','playing card','chess piece','token','small ball','goal','microphone','phone','cup']

def _cosine(first,second):
    if not first or not second or len(first)!=len(second):return 0
    a=np.asarray(first,dtype=np.float32);b=np.asarray(second,dtype=np.float32);den=float(np.linalg.norm(a)*np.linalg.norm(b));return float(np.dot(a,b)/den) if den else 0

def _median_descriptor(rows):
    values=[row.get('appearance',[]) for row in rows if row.get('appearance')]
    if not values:return []
    return [float(median(column)) for column in zip(*values)]

def stitch_identities(perception):
    tracklets=defaultdict(list)
    for frame in perception.get('frames',[]):
        for detection in frame.get('detections',[]):
            if detection.get('class')=='person':tracklets[str(detection['trackId'])].append({'time':frame['time'],**detection})
    summaries={track:{'start':min(row['time'] for row in rows),'end':max(row['time'] for row in rows),'firstCenter':center(rows[0]['box']),'lastCenter':center(rows[-1]['box']),'appearance':_median_descriptor(rows)} for track,rows in tracklets.items()}
    parent={track:track for track in tracklets}
    def find(track):
        while parent[track]!=track:parent[track]=parent[parent[track]];track=parent[track]
        return track
    def union(first,second):
        a,b=find(first),find(second)
        if a!=b:parent[b]=a
    ordered=sorted(summaries,key=lambda track:summaries[track]['start'])
    matches=[]
    for later in ordered:
        best=None
        for earlier in ordered:
            if earlier==later:continue
            first=summaries[earlier];second=summaries[later];gap=second['start']-first['end']
            if gap<.18 or gap>4.5:continue
            similarity=_cosine(first['appearance'],second['appearance']);distance=math.dist(first['lastCenter'],second['firstCenter']);threshold=.86 if gap<=1.4 and distance<=.34 else .93
            score=similarity-(.12*distance if gap<=1.4 else 0)
            if similarity>=threshold and (best is None or score>best[0]):best=(score,earlier,similarity,gap)
        if best:union(best[1],later);matches.append({'from':best[1],'to':later,'similarity':round(best[2],4),'gap':round(best[3],3)})
    groups=defaultdict(list)
    for track in ordered:groups[find(track)].append(track)
    canonical={};identities=[]
    for index,(_,members) in enumerate(sorted(groups.items(),key=lambda item:min(summaries[track]['start'] for track in item[1])),1):
        identity=f'person-{index:03d}'
        for track in members:canonical[track]=identity
        identities.append({'canonicalId':identity,'sourceTrackIds':members,'start':min(summaries[track]['start'] for track in members),'end':max(summaries[track]['end'] for track in members),'confidence':round(max([match['similarity'] for match in matches if match['from'] in members or match['to'] in members] or [.7]),3)})
    for frame in perception.get('frames',[]):
        for detection in frame.get('detections',[]):
            raw=str(detection['trackId'])
            if detection.get('class')=='person' and raw in canonical:detection['rawTrackId']=raw;detection['trackId']=canonical[raw]
        for face in frame.get('faces',[]):
            raw=str(face.get('personTrackId'))
            if raw in canonical:face['rawPersonTrackId']=raw;face['personTrackId']=canonical[raw]
    perception.setdefault('tracking',{})['identityStitching']=True;perception['identities']=identities
    return {'identities':identities,'sourceToCanonical':canonical,'matches':matches}

def estimate_camera_motion(video_path,sample_times,out_dir=None):
    cap=cv2.VideoCapture(video_path);rows=[];previous=None;previous_points=None
    for timestamp in sample_times:
        if out_dir and cancelled(out_dir):raise RuntimeError('Cancelled')
        cap.set(cv2.CAP_PROP_POS_MSEC,float(timestamp)*1000);ok,frame=cap.read()
        if not ok:rows.append({'time':timestamp,'dx':0,'dy':0,'zoom':1,'rotation':0,'confidence':0});continue
        height,width=frame.shape[:2];scale=min(1,360/max(1,width));gray=cv2.cvtColor(cv2.resize(frame,(max(2,int(width*scale)),max(2,int(height*scale)))),cv2.COLOR_BGR2GRAY)
        motion={'time':timestamp,'dx':0.0,'dy':0.0,'zoom':1.0,'rotation':0.0,'confidence':0.0}
        if previous is not None:
            points=cv2.goodFeaturesToTrack(previous,maxCorners=180,qualityLevel=.01,minDistance=7)
            if points is not None:
                next_points,status,_=cv2.calcOpticalFlowPyrLK(previous,gray,points,None);good_old=points[status.flatten()==1];good_new=next_points[status.flatten()==1]
                if len(good_old)>=8:
                    matrix,inliers=cv2.estimateAffinePartial2D(good_old,good_new,method=cv2.RANSAC,ransacReprojThreshold=2.5)
                    if matrix is not None:
                        a,b,tx=matrix[0];_,_,ty=matrix[1];motion.update(dx=round(float(tx/gray.shape[1]),6),dy=round(float(ty/gray.shape[0]),6),zoom=round(float(math.sqrt(a*a+b*b)),6),rotation=round(float(math.atan2(b,a)),6),confidence=round(float(inliers.mean()) if inliers is not None else .5,3))
        rows.append(motion);previous=gray
    cap.release();return rows

def _nearest_frame(frames,t):return min(frames,key=lambda frame:abs(frame['time']-t)) if frames else None

def detect_open_vocabulary(video_path,perception,out_dir,model_name='yolov8s-worldv2.pt',analysis_fps=4):
    report={'enabled':True,'model':model_name,'prompts':OPEN_VOCAB_PROMPTS,'detections':0,'error':None}
    try:
        from ultralytics import YOLOWorld
        model=YOLOWorld(model_name);model.set_classes(OPEN_VOCAB_PROMPTS);cap=cv2.VideoCapture(video_path);fps=cap.get(cv2.CAP_PROP_FPS) or 30;width,height=int(cap.get(3)),int(cap.get(4));every=max(1,round(fps/analysis_fps));frame_number=0
        while True:
            ok,frame=cap.read()
            if not ok:break
            if cancelled(out_dir):raise RuntimeError('Cancelled')
            if frame_number%every:frame_number+=1;continue
            result=model.track(frame,persist=True,verbose=False,conf=.18,iou=.45)[0];target=_nearest_frame(perception.get('frames',[]),frame_number/fps)
            if target is not None and result.boxes is not None:
                ids=result.boxes.id.int().cpu().tolist() if result.boxes.id is not None else list(range(len(result.boxes)));boxes=result.boxes.xyxy.cpu().tolist();scores=result.boxes.conf.cpu().tolist();classes=result.boxes.cls.int().cpu().tolist()
                for track,box,score,class_id in zip(ids,boxes,scores,classes):
                    name=model.names[class_id] if isinstance(model.names,dict) else model.names[class_id];norm=[box[0]/width,box[1]/height,box[2]/width,box[3]/height]
                    if any(existing.get('class')!='person' and iou(existing['box'],norm)>.5 for existing in target.get('detections',[])):continue
                    target.setdefault('detections',[]).append({'trackId':f'ov-{track}','class':str(name),'confidence':round(float(score),4),'box':[round(x,5) for x in norm],'rawBox':[round(x,5) for x in norm],'velocity':[0,0],'openVocabulary':True});report['detections']+=1
            frame_number+=1
        cap.release()
    except Exception as exc:report['error']=str(exc);report['enabled']=False
    return report

def enrich_interactions(perception,camera_motion):
    frames=perception.get('frames',[]);motion_by_time={round(row['time'],4):row for row in camera_motion};previous_time=None
    for frame in frames:
        motion=min(camera_motion,key=lambda row:abs(row['time']-frame['time'])) if camera_motion else {'dx':0,'dy':0,'zoom':1,'rotation':0,'confidence':0};dt=max(.001,frame['time']-previous_time) if previous_time is not None else 1/max(1,perception.get('analysisFps',8));camera_velocity=[motion.get('dx',0)/dt,motion.get('dy',0)/dt];people=[row for row in frame.get('detections',[]) if row.get('class')=='person'];objects=[row for row in frame.get('detections',[]) if row.get('class')!='person'];interactions=[]
        for detection in frame.get('detections',[]):
            velocity=detection.get('velocity',[0,0]);detection['worldVelocity']=[round(float(velocity[0]-camera_velocity[0]),5),round(float(velocity[1]-camera_velocity[1]),5)]
        for index,first in enumerate(people):
            for second in people[index+1:]:
                distance=math.dist(center(first['box']),center(second['box']))
                if distance<=.36:interactions.append({'type':'near','from':first['trackId'],'to':second['trackId'],'strength':round(1-distance/.36,3)})
        for obj in objects:
            ox,oy=center(obj['box'])
            for person in people:
                box=person['box'];pad=.08
                if box[0]-pad<=ox<=box[2]+pad and box[1]-pad<=oy<=box[3]+pad:interactions.append({'type':'manipulates','from':person['trackId'],'to':obj['trackId'],'strength':.75})
        faces={str(face.get('personTrackId')):face for face in frame.get('faces',[]) if face.get('personTrackId')}
        for person in people:
            face=faces.get(str(person['trackId']))
            if not face or abs(face.get('headYaw',0))<.12:continue
            px,py=center(person['box']);direction=1 if face['headYaw']>0 else -1;candidates=[]
            for other in people:
                if other is person:continue
                ox,oy=center(other['box']);delta=(ox-px)*direction
                if delta>0 and abs(oy-py)<.35:candidates.append((delta+abs(oy-py),other['trackId']))
            if candidates:interactions.append({'type':'looks_at','from':person['trackId'],'to':min(candidates)[1],'strength':round(min(1,abs(face['headYaw'])),3)})
        frame['cameraMotion']=motion;frame['cameraVelocity']=[round(x,5) for x in camera_velocity];frame['interactions']=interactions;previous_time=frame['time']
    perception.setdefault('tracking',{})['cameraMotionCompensation']=True;perception['tracking']['interactionGraph']=True
    return perception

def enhance_perception(video_path,perception,out_path,out_dir,progress=None,use_open_vocabulary=True):
    progress=progress or (lambda *_:None);frames=perception.get('frames',[]);times=[frame['time'] for frame in frames];progress('Stage 4 · estimating global camera motion',18);camera=estimate_camera_motion(video_path,times,out_dir);progress('Stage 4 · open-vocabulary small-object grounding',24);open_vocab=detect_open_vocabulary(video_path,perception,out_dir) if use_open_vocabulary else {'enabled':False,'detections':0,'error':'disabled'};progress('Stage 4 · persistent identity stitching',29);identities=stitch_identities(perception);progress('Stage 4 · interaction and gaze grounding',32);enrich_interactions(perception,camera);perception.setdefault('tracking',{})['openVocabulary']=open_vocab['enabled'];dump(out_path,perception);report={'stage':'stage-4-perceptual-grounding','cameraMotionSamples':len(camera),'meanCameraConfidence':round(sum(row.get('confidence',0) for row in camera)/max(1,len(camera)),3),'openVocabulary':open_vocab,'identityMap':identities,'interactionEdges':sum(len(frame.get('interactions',[])) for frame in frames)};dump(Path(out_dir)/'grounding-report.json',report);dump(Path(out_dir)/'identity-map.json',identities);return perception,report
