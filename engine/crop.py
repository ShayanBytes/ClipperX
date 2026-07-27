from __future__ import annotations
import bisect,math
from collections import defaultdict
from statistics import median
from .common import clamp,union_box,dump,load,center

def _percentile(values,q,default):
    if not values:return default
    ordered=sorted(values);return ordered[min(len(ordered)-1,max(0,int((len(ordered)-1)*q)))]

def _target_for(frame,shot,aspect_norm,lookahead=.16):
    detections={str(d['trackId']):d for d in frame.get('detections',[])};wanted=[]
    for track in shot.get('requiredTrackIds',[]):
        detection=detections.get(str(track))
        if detection:
            box=list(detection['box']);vx,vy=detection.get('worldVelocity',detection.get('velocity',[0,0]));lead=lookahead if shot.get('cameraPolicy')=='action_follow' else 0
            wanted.append([box[0]+vx*lead,box[1]+vy*lead,box[2]+vx*lead,box[3]+vy*lead])
    focus=shot.get('focusPoint')
    if isinstance(focus,list) and len(focus)==2:
        fx,fy=float(focus[0]),float(focus[1]);wanted.append([fx-.08,fy-.08,fx+.08,fy+.08])
    target=union_box(wanted)
    if not target:return {'cx':.5,'cy':.5,'h':1.0,'w':min(1.0,aspect_norm),'visible':False}
    margin=.10 if shot.get('mode')=='action' else (.075 if len(wanted)>1 else .055)
    target=[clamp(target[0]-margin,0,1),clamp(target[1]-margin,0,1),clamp(target[2]+margin,0,1),clamp(target[3]+margin,0,1)]
    req_h=max(.34,target[3]-target[1]);req_w=max(.08,target[2]-target[0])
    crop_h=clamp(max(req_h,req_w/max(aspect_norm,1e-6)),.42,1.0);crop_w=min(1.0,crop_h*aspect_norm);cx,cy=center(target)
    return {'cx':clamp(cx,crop_w/2,1-crop_w/2),'cy':clamp(cy,crop_h/2,1-crop_h/2),'h':crop_h,'w':crop_w,'visible':True}

def _median_filter(values,radius=3):
    output=[]
    for index in range(len(values)):
        window=values[max(0,index-radius):min(len(values),index+radius+1)]
        output.append({key:median([row[key] for row in window]) for key in ('cx','cy','h','w')}|{'visible':any(row['visible'] for row in window)})
    return output

def make_crop_keyframes(perception,shots,out_path,corrections_path=None,lookahead=.16,smoothing=.72,max_pan_speed=.24):
    W,H=perception['width'],perception['height'];aspect_norm=(H/W)*(9/16);corrections=load(corrections_path,[]) if corrections_path else []
    by_shot=defaultdict(list)
    for frame in perception.get('frames',[]):
        shot=next((item for item in shots.get('shots',[]) if item['start']<=frame['time']<item['end']),None)
        if shot:by_shot[shot['id']].append((frame,_target_for(frame,shot,aspect_norm,lookahead)))
    planned={}
    for shot in shots.get('shots',[]):
        rows=by_shot.get(shot['id'],[]);targets=[target for _,target in rows]
        if not targets:continue
        policy=shot.get('cameraPolicy','locked')
        if policy in ('locked','wide_static'):
            # Editorial dialogue shots are locked like a real tripod camera. Use robust
            # shot-level geometry rather than following every detector movement.
            visible=[target for target in targets if target['visible']] or targets
            fixed={'cx':median([x['cx'] for x in visible]),'cy':median([x['cy'] for x in visible]),'h':_percentile([x['h'] for x in visible],.82,1.0),'visible':True}
            fixed['w']=min(1.0,fixed['h']*aspect_norm);planned[shot['id']]=[fixed.copy() for _ in targets]
        else:planned[shot['id']]=_median_filter(targets,4 if policy=='action_follow' else 6)
    keys=[];previous=None;previous_shot=None;shot_positions=defaultdict(int)
    for frame in perception.get('frames',[]):
        t=frame['time'];shot=next((item for item in shots.get('shots',[]) if item['start']<=t<item['end']),shots.get('shots',[{}])[-1] if shots.get('shots') else None)
        if shot is None:continue
        index=shot_positions[shot['id']];shot_positions[shot['id']]+=1
        targets=planned.get(shot['id']);target=targets[min(index,len(targets)-1)] if targets else {'cx':.5,'cy':.5,'h':1,'w':min(1,aspect_norm)}
        cx,cy,crop_h=target['cx'],target['cy'],target['h'];crop_w=min(1,crop_h*aspect_norm)
        correction=next((item for item in corrections if item.get('start',-1)<=t<=item.get('end',-1)),None)
        if correction:
            cx=float(correction.get('centerX',cx));cy=float(correction.get('centerY',cy));crop_h=float(correction.get('cropHeight',crop_h));crop_w=min(1,crop_h*aspect_norm)
        policy=shot.get('cameraPolicy','locked')
        if previous and previous_shot==shot['id'] and policy not in ('locked','wide_static'):
            dt=max(1e-3,t-previous['time']);tau=.58 if policy=='action_follow' else 1.1;alpha=1-math.exp(-dt/tau)
            # Dead zone stops the camera reacting to tiny tracker movements.
            dead_x=max(.018,previous['cropWidth']*.055);dead_y=max(.014,previous['cropHeight']*.035)
            dx=cx-previous['centerX'];dy=cy-previous['centerY']
            if abs(dx)<dead_x:cx=previous['centerX']
            if abs(dy)<dead_y:cy=previous['centerY']
            speed=.22 if policy=='action_follow' else .10;limit=min(max_pan_speed,speed)*dt
            cx=previous['centerX']+clamp(cx-previous['centerX'],-limit,limit)*alpha
            cy=previous['centerY']+clamp(cy-previous['centerY'],-limit,limit)*alpha
            zoom_alpha=1-math.exp(-dt/1.25);crop_h=previous['cropHeight']+(crop_h-previous['cropHeight'])*zoom_alpha;crop_w=min(1,crop_h*aspect_norm)
        # A new shot intentionally jumps to the new composition: it is an editorial cut, not a hurried pan.
        cx=clamp(cx,crop_w/2,1-crop_w/2);cy=clamp(cy,crop_h/2,1-crop_h/2)
        key={'time':t,'centerX':round(cx,6),'centerY':round(cy,6),'cropWidth':round(crop_w,6),'cropHeight':round(crop_h,6),'shotId':shot['id'],'mode':shot.get('mode','wide'),'cameraPolicy':policy,'confidence':shot.get('confidence',.5)}
        keys.append(key);previous=key;previous_shot=shot['id']
    data={'sourceWidth':W,'sourceHeight':H,'keyframes':keys,'stabilization':{'hardCuts':True,'deadZone':True,'shotLockedDialogue':True,'medianTrajectoryFilter':True}}
    dump(out_path,data);return data

def interpolate(keys,t):
    if not keys:return {'centerX':.5,'centerY':.5,'cropWidth':.3164,'cropHeight':1}
    times=[key['time'] for key in keys];index=bisect.bisect_right(times,t)
    if index<=0:return keys[0]
    if index>=len(keys):return keys[-1]
    a,b=keys[index-1],keys[index]
    # Never tween across an editorial shot boundary. This is the key difference
    # between a calm cut and a frantic pan from one speaker to another.
    if a.get('shotId') is not None and b.get('shotId') is not None and a.get('shotId')!=b.get('shotId'):
        return {key:a[key] for key in ('centerX','centerY','cropWidth','cropHeight')}
    fraction=(t-a['time'])/max(1e-6,b['time']-a['time'])
    return {key:(a[key]+(b[key]-a[key])*fraction) for key in ('centerX','centerY','cropWidth','cropHeight')}
