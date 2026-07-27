from __future__ import annotations
import copy,math
from collections import defaultdict
from statistics import mean
from .common import center,clamp

ACTION_TERMS=('throw','toss','roll','rolled','cube','dice',' die ','ball','kick','shoot','shot','catch','hit','strike','score','goal','save','keeper','projectile','token','card flip','drop','bounce')
OBJECT_TERMS=('ball','sports ball','dice','die','cube','token','piece','card','frisbee','bottle','projectile','object')

def is_person(row):return str(row.get('class','')).lower()=='person'

def aspect_safe_crop(required_width,required_height,normalized_aspect,min_height=.24):
    aspect=max(1e-6,float(normalized_aspect));crop_h=max(min_height,float(required_height),float(required_width)/aspect);crop_w=crop_h*aspect
    if crop_h>1:crop_h=1;crop_w=aspect
    if crop_w>1:crop_w=1;crop_h=min(1,1/aspect)
    return clamp(crop_w,.02,1),clamp(crop_h,.02,1)

def body_safe_box(row):
    box=list(row.get('box',[0,0,1,1]));x1,y1,x2,y2=box
    if str(row.get('class','')).lower()=='person':
        width=x2-x1;height=y2-y1;x1-=max(.025,width*.16);x2+=max(.025,width*.16);y1-=max(.018,height*.10);y2+=max(.035,height*.16)
    else:
        width=x2-x1;height=y2-y1;x1-=max(.018,width*.35);x2+=max(.018,width*.35);y1-=max(.018,height*.35);y2+=max(.018,height*.35)
    return [clamp(x1,0,1),clamp(y1,0,1),clamp(x2,0,1),clamp(y2,0,1)]

def _motion_tracks(moment,perception):
    tracks=defaultdict(list)
    for frame in perception.get('frames',[]):
        if not moment['start']<=frame.get('time',-1)<moment['end']:continue
        for row in frame.get('detections',[]):
            if is_person(row):continue
            vx,vy=row.get('worldVelocity',row.get('velocity',[0,0]));tracks[str(row['trackId'])].append({'time':frame['time'],'center':center(row['box']),'speed':math.hypot(vx,vy),'class':str(row.get('class','object')).lower(),'confidence':float(row.get('confidence',0))})
    ranked=[]
    for track,rows in tracks.items():
        if len(rows)<2:continue
        displacement=math.dist(rows[0]['center'],rows[-1]['center']);speed=max(row['speed'] for row in rows);klass=max(set(row['class'] for row in rows),key=lambda value:sum(item['class']==value for item in rows));semantic=any(term in klass for term in OBJECT_TERMS);score=displacement*2.2+speed+(.12 if semantic else 0)+mean(row['confidence'] for row in rows)*.05
        if displacement>=.025 or speed>=.035 or semantic:ranked.append((score,track,klass,displacement,speed))
    return sorted(ranked,reverse=True)

def prepare_moment(moment,perception):
    result=copy.deepcopy(moment);text=(' '+str(result.get('summary',''))+' '+str(result.get('type',''))+' '+str(result.get('narrativeRole',''))+' ').lower();motion=_motion_tracks(result,perception);language_action=any(term in text for term in ACTION_TERMS);strong_motion=bool(motion and (motion[0][3]>=.045 or motion[0][4]>=.055));action=bool(result.get('keepContinuousAction') or language_action or strong_motion)
    if action and motion:
        track=motion[0][1]
        if track not in result['mustShowTrackIds']:result['mustShowTrackIds'].append(track)
        result['motionPrimaryTrackId']=track;result['motionObjectClass']=motion[0][2]
    result['detectedPhysicalAction']=action;result['keepContinuousAction']=bool(result.get('keepContinuousAction') or action);result['framingEvidence']={'languageAction':language_action,'strongObjectMotion':strong_motion,'motionPrimaryTrackId':result.get('motionPrimaryTrackId'),'motionCandidates':len(motion)};return result

def moment_geometry(moment,stats,source_width,source_height):
    rows=[stats[track] for track in moment.get('mustShowTrackIds',[]) if track in stats]
    if not rows:return {'singleFrameFeasible':False,'singleFrameQuality':0,'spatialSpread':1,'cropWidth':1,'cropHeight':1,'occupancy':0,'minimumPersonScale':0,'allBodySafe':False}
    safe=[]
    for row in rows:safe.append(body_safe_box(row))
    x1=min(box[0] for box in safe);y1=min(box[1] for box in safe);x2=max(box[2] for box in safe);y2=max(box[3] for box in safe);required_w=x2-x1;required_h=y2-y1;normalized_aspect=(9/16)*(source_height/max(1,source_width));crop_w,crop_h=aspect_safe_crop(required_w,required_h,normalized_aspect,.28);fits=required_w<=crop_w+.001 and required_h<=crop_h+.001;crop_area=max(1e-6,crop_w*crop_h);subject_area=sum(max(0,box[2]-box[0])*max(0,box[3]-box[1]) for box in safe);occupancy=min(1,subject_area/crop_area);person_scales=[(box[3]-box[1])/crop_h for box,row in zip(safe,rows) if str(row.get('class','')).lower()=='person'];minimum_scale=min(person_scales) if person_scales else .3;empty_penalty=max(0,.07-occupancy)*4;quality=clamp((1 if fits else .2)*.58+min(1,minimum_scale/.24)*.25+min(1,occupancy/.12)*.17-empty_penalty,0,1);centers=[row.get('center',[.5,.5])[0] for row in rows]
    return {'singleFrameFeasible':bool(fits and quality>=.62),'singleFrameQuality':round(quality,4),'spatialSpread':round(max(centers)-min(centers) if len(centers)>1 else 0,4),'cropWidth':round(crop_w,4),'cropHeight':round(crop_h,4),'occupancy':round(occupancy,4),'minimumPersonScale':round(minimum_scale,4),'allBodySafe':fits}

def cell_utility(group,stats,cell,source_width,source_height):
    rows=[stats[track] for track in group if track in stats]
    if not rows:return {'score':0,'safe':False,'reason':'no visible assigned subject'}
    safe=[body_safe_box(row) for row in rows];x1=min(box[0] for box in safe);y1=min(box[1] for box in safe);x2=max(box[2] for box in safe);y2=max(box[3] for box in safe);normalized_aspect=(cell[2]/max(cell[3],1e-6))*(9/16)*(source_height/max(1,source_width));crop_w,crop_h=aspect_safe_crop(x2-x1,y2-y1,normalized_aspect,.24);fits=(x2-x1)<=crop_w+.001 and (y2-y1)<=crop_h+.001;occupancy=sum((box[2]-box[0])*(box[3]-box[1]) for box in safe)/max(1e-6,crop_w*crop_h);person_scale=min([(box[3]-box[1])/crop_h for box,row in zip(safe,rows) if str(row.get('class','')).lower()=='person'] or [.3]);score=clamp((.52 if fits else .05)+min(1,occupancy/.14)*.25+min(1,person_scale/.25)*.23,0,1);return {'score':round(score,4),'safe':bool(fits and score>=.58),'occupancy':round(occupancy,4),'personScale':round(person_scale,4),'reason':'body-safe meaningful cell' if fits else 'assigned subject cannot fit cell safely'}

def allow_split(moment,geometry,groups,stats,source_width,source_height,cell_geometries):
    if moment.get('detectedPhysicalAction') or moment.get('keepContinuousAction'):return False,'continuous physical action must remain one camera intention',[]
    utilities=[cell_utility(group,stats,cell,source_width,source_height) for group,cell in zip(groups,cell_geometries)]
    if any(not item['safe'] for item in utilities):return False,'one or more cells are blank, fragmentary, or low utility',utilities
    role=str(moment.get('narrativeRole','')).lower();simultaneous=role in ('reaction','payoff','group_reaction') or bool(moment.get('coverageRequirements',{}).get('simultaneous'))
    separated=geometry['spatialSpread']>=.42
    if geometry['singleFrameFeasible'] and geometry['singleFrameQuality']>=.70:return False,'one readable crop already contains the story',utilities
    if not (simultaneous or separated):return False,'split has no independent simultaneous narrative value',utilities
    return True,'separated simultaneous regions require independent safe cells',utilities
