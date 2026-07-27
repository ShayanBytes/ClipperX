from __future__ import annotations
import copy,math,shutil,subprocess
from collections import defaultdict
from pathlib import Path
from statistics import mean,pstdev
import cv2,numpy as np
from .common import clamp,cancelled,dump,load
from .framing_intelligence import body_safe_box,aspect_safe_crop

QUALITY_THRESHOLDS={'requiredCoverageRate':.94,'blankCellRate':.12,'jitterScore':.34}

def _bgr(value,default):
    text=str(value or '').lstrip('#')
    try:return tuple(int(text[index:index+2],16) for index in (4,2,0)) if len(text)==6 else default
    except ValueError:return default

def _segment_at(segments,t,index):
    while index+1<len(segments) and t>=segments[index]['end']:index+=1
    if segments and segments[index]['start']<=t<segments[index]['end']:return segments[index],index
    return None,index

def _directive_at(directives,t,index):
    while index+1<len(directives) and t>=directives[index]['end']:index+=1
    if directives and directives[index]['start']<=t<directives[index]['end']:return directives[index],index
    return None,index

def _nearest_detection_frame(perception,t,index):
    frames=perception.get('frames',[])
    while index+1<len(frames) and abs(frames[index+1]['time']-t)<=abs(frames[index]['time']-t):index+=1
    return (frames[index] if frames else {'detections':[]}),index

def _desired_view(cell,detections,source_width,source_height,tuning):
    by_track={str(row['trackId']):row for row in detections};rows=[by_track[track] for track in cell.get('trackIds',[]) if track in by_track];hint=cell.get('viewportHint',{});policy=cell.get('sourcePolicy','subject_lock');lead=.22 if policy=='trajectory_follow' else 0;boxes=[]
    for row in rows:
        box=body_safe_box(row);vx,vy=row.get('worldVelocity',row.get('velocity',[0,0]));boxes.append([box[0]+vx*lead,box[1]+vy*lead,box[2]+vx*lead,box[3]+vy*lead])
    if boxes:
        margin=max(.012,(.075 if len(boxes)>1 else .052)+float(tuning.get('extraMargin',0)));x1=clamp(min(box[0] for box in boxes)-margin,0,1);y1=clamp(min(box[1] for box in boxes)-margin,0,1);x2=clamp(max(box[2] for box in boxes)+margin,0,1);y2=clamp(max(box[3] for box in boxes)+margin,0,1)
        rect=cell.get('outputRect',[0,0,1,1]);output_aspect=(rect[2]/max(rect[3],1e-6))*(9/16);source_aspect=output_aspect*(source_height/source_width);crop_w,crop_h=aspect_safe_crop(x2-x1,y2-y1,source_aspect,.24);cx=(x1+x2)/2;cy=(y1+y2)/2
    else:
        cx=float(hint.get('centerX',.5));cy=float(hint.get('centerY',.5));crop_w=float(hint.get('cropWidth',1));crop_h=float(hint.get('cropHeight',1))
    crop_scale=float(tuning.get('cropScale',1));crop_w=clamp(crop_w*crop_scale,.04,1);crop_h=clamp(crop_h*crop_scale,.16,1)
    cx=clamp(cx,crop_w/2,1-crop_w/2);cy=clamp(cy,crop_h/2,1-crop_h/2)
    return {'centerX':cx,'centerY':cy,'cropWidth':crop_w,'cropHeight':crop_h,'detectedTracks':[str(row['trackId']) for row in rows]}

def _smooth_view(desired,previous,policy,dt,tuning):
    if previous is None:return desired.copy()
    if tuning.get('holdLastSeen') and not desired.get('detectedTracks'):
        held=previous.copy();held['detectedTracks']=[];return held
    scale=float(tuning.get('smoothingScale',1));
    if policy=='trajectory_follow':tau=.28*scale;speed=.52;dead=.012
    elif policy=='cluster_hold':tau=.58*scale;speed=.24;dead=.026
    else:tau=.72*scale;speed=.16;dead=.025
    alpha=1-math.exp(-dt/max(.03,tau));result=desired.copy()
    for key in ('centerX','centerY'):
        delta=desired[key]-previous[key]
        if abs(delta)<dead:result[key]=previous[key]
        else:result[key]=previous[key]+clamp(delta,-speed*dt,speed*dt)*alpha
    zoom_alpha=1-math.exp(-dt/max(.08,.95*scale))
    for key in ('cropWidth','cropHeight'):result[key]=previous[key]+(desired[key]-previous[key])*zoom_alpha
    return result

def _manual_override(view,corrections,t,cell_id,cell_count):
    correction=next((row for row in corrections if row.get('start',-1)<=t<=row.get('end',-1) and (row.get('cellId')==cell_id or (not row.get('cellId') and cell_count==1))),None)
    if not correction:return view
    result=view.copy();result['centerX']=float(correction.get('centerX',result['centerX']));result['centerY']=float(correction.get('centerY',result['centerY']))
    if correction.get('cropHeight') is not None:
        ratio=result['cropWidth']/max(result['cropHeight'],1e-6);result['cropHeight']=float(correction['cropHeight']);result['cropWidth']=min(1,result['cropHeight']*ratio)
    return result

def _crop(frame,view,width,height):
    source_height,source_width=frame.shape[:2];available_width=min(source_width,max(2,int(view['cropWidth']*source_width)));available_height=min(source_height,max(2,int(view['cropHeight']*source_height)));target_aspect=width/max(1,height);crop_width=available_width;crop_height=max(2,int(round(crop_width/target_aspect)))
    if crop_height>available_height:crop_height=available_height;crop_width=max(2,int(round(crop_height*target_aspect)))
    crop_width=min(source_width,crop_width);crop_height=min(source_height,crop_height);cx=int(view['centerX']*source_width);cy=int(view['centerY']*source_height);x=int(clamp(cx-crop_width/2,0,source_width-crop_width));y=int(clamp(cy-crop_height/2,0,source_height-crop_height));region=frame[y:y+crop_height,x:x+crop_width]
    if region.size==0:return np.zeros((height,width,3),dtype=np.uint8)
    return cv2.resize(region,(width,height),interpolation=cv2.INTER_LANCZOS4)

def _general_frame(frame,width,height):
    """Preserve the whole source over a blurred cover background without squeezing."""
    source_height,source_width=frame.shape[:2];cover=max(width/source_width,height/source_height);cover_width=max(width,int(round(source_width*cover)));cover_height=max(height,int(round(source_height*cover)));background=cv2.resize(frame,(cover_width,cover_height),interpolation=cv2.INTER_LANCZOS4);x=max(0,(cover_width-width)//2);y=max(0,(cover_height-height)//2);background=background[y:y+height,x:x+width];background=cv2.GaussianBlur(background,(0,0),24)
    fit=min(width/source_width,height/source_height);fit_width=max(2,int(round(source_width*fit)));fit_height=max(2,int(round(source_height*fit)));foreground=cv2.resize(frame,(fit_width,fit_height),interpolation=cv2.INTER_LANCZOS4);left=(width-fit_width)//2;top=(height-fit_height)//2;background[top:top+fit_height,left:left+fit_width]=foreground;return background

def _frame_safe_cells(cells,detections):
    """Never render the same full-source recovery into multiple split cells."""
    if len(cells)<=1:return cells,False
    by_track={str(row.get('trackId')):row for row in detections};ranked=[]
    for cell in cells:
        rows=[by_track[str(track)] for track in cell.get('trackIds',[]) if str(track) in by_track]
        people=[row for row in rows if str(row.get('class','')).lower()=='person'];ranked.append((cell,people or rows))
    meaningful=[item for item in ranked if item[1]]
    distinct=False
    if len(meaningful)>=2:
        centers=[]
        for _,rows in meaningful[:2]:centers.append(mean((row['box'][0]+row['box'][2])/2 for row in rows))
        distinct=abs(centers[0]-centers[1])>=.10
    if distinct:return cells,False
    chosen=max(ranked,key=lambda item:(len(item[1]),item[0].get('priority')=='primary'))[0] if meaningful else cells[0]
    single=copy.deepcopy(chosen);single['id']=f"{chosen.get('id','cell')}:collapsed";single['outputRect']=[0,0,1,1]
    return [single],True

def _inside(view,box):
    cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2;return view['centerX']-view['cropWidth']/2<=cx<=view['centerX']+view['cropWidth']/2 and view['centerY']-view['cropHeight']/2<=cy<=view['centerY']+view['cropHeight']/2

def render_silent(video_path,composition,perception,out_path,out_dir,width=1080,height=1920,tuning=None,corrections=None,progress_callback=None,telemetry_path=None):
    tuning=tuning or {};corrections=corrections or [];out_dir=Path(out_dir);cap=cv2.VideoCapture(video_path);fps=cap.get(cv2.CAP_PROP_FPS) or 30;source_width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));source_height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT));total=max(1,int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1));writer=cv2.VideoWriter(str(out_path),cv2.VideoWriter_fourcc(*'mp4v'),fps,(width,height))
    if not writer.isOpened():raise RuntimeError('Could not open Stage 3 multi-viewport writer')
    segments=composition.get('segments',[]);directives=composition.get('temporalCadence',{}).get('directives',[]);segment_index=0;directive_index=0;detection_index=0;states={};telemetry=[];frame_number=0;last_segment=None;last_directive=None;sample_every=max(1,int(fps/4))
    while True:
        ok,frame=cap.read()
        if not ok:break
        if cancelled(out_dir):cap.release();writer.release();raise RuntimeError('Cancelled')
        t=frame_number/fps;segment,segment_index=_segment_at(segments,t,segment_index);directive,directive_index=_directive_at(directives,t,directive_index);detection_frame,detection_index=_nearest_detection_frame(perception,t,detection_index);detections=detection_frame.get('detections',[]);directive_changed=bool(directive and directive.get('id')!=last_directive);hard_acquire=bool(directive_changed and directive.get('hardAcquire'));fast_acquire=bool(directive_changed and directive.get('fastAcquire'));global_style=composition.get('editorialStyle',{});segment_style=segment.get('editorial',{}) if segment else {};local_tuning={**segment_style.get('cameraTuning',{}),**tuning};canvas_color=_bgr(global_style.get('canvasColor'),(24,22,31));canvas=np.full((height,width,3),canvas_color,dtype=np.uint8);sample={'time':round(t,4),'segmentId':segment.get('id') if segment else None,'directiveId':directive.get('id') if directive else None,'hardAcquire':hard_acquire,'fastAcquire':fast_acquire,'layoutType':segment.get('layout',{}).get('layoutType') if segment else 'cadence_fallback','beatRole':segment_style.get('beatRole'),'cells':[]}
        if hard_acquire:states.clear()
        if segment is None or not segment.get('layout',{}).get('cells'):
            anchor=(directive.get('primaryTrackIds') or [None])[0] if directive else None;by_track={str(row['trackId']):row for row in detections}
            if anchor and anchor in by_track:
                cell={'id':'cadence-gap','outputRect':[0,0,1,1],'trackIds':[anchor],'sourcePolicy':'subject_lock','viewportHint':{'centerX':.5,'centerY':.5,'cropWidth':.75,'cropHeight':1}};desired=_desired_view(cell,detections,source_width,source_height,local_tuning);previous=states.get(('cadence-gap','subject_lock'));view=desired if hard_acquire or fast_acquire or previous is None else _smooth_view(desired,previous,'subject_lock',1/fps,local_tuning);states[('cadence-gap','subject_lock')]=view;canvas=_crop(frame,view,width,height);sample['cells'].append({'cellId':'cadence-gap','trackIds':[anchor],'availableTracks':[anchor],'visibleTracks':[anchor] if _inside(view,by_track[anchor]['box']) else [],'blank':False,'evidenceFallback':False,'view':{key:round(view[key],6) for key in ('centerX','centerY','cropWidth','cropHeight')}})
            else:canvas=_general_frame(frame,width,height)
        else:
            new_segment=last_segment!=segment['id'];source_cells=copy.deepcopy(segment['layout']['cells']);anchor=(directive.get('primaryTrackIds') or [None])[0] if directive else None
            if anchor and len(source_cells)==1 and not segment.get('keepContinuousAction'):source_cells[0]['trackIds']=[anchor]
            cells,collapsed_split=_frame_safe_cells(source_cells,detections);sample['collapsedDuplicateSplit']=collapsed_split
            for cell in cells:
                general_safe=cell.get('sourcePolicy')=='general_safe';continuity=segment.get('transitionIn') in ('hold','action_continuity');key=(cell['id'],cell.get('sourcePolicy')) if continuity else (segment['id'],cell['id']);desired={'centerX':.5,'centerY':.5,'cropWidth':1,'cropHeight':1,'detectedTracks':[str(row['trackId']) for row in detections]} if general_safe else _desired_view(cell,detections,source_width,source_height,local_tuning)
                if t<.7 and not desired.get('detectedTracks') and not general_safe:
                    normalized_aspect=(cell['outputRect'][2]/max(cell['outputRect'][3],1e-6))*(9/16)*(source_height/source_width);safe_w,safe_h=aspect_safe_crop(normalized_aspect,1,normalized_aspect,1);desired={'centerX':.5,'centerY':.5,'cropWidth':safe_w,'cropHeight':safe_h,'detectedTracks':[]}
                desired=_manual_override(desired,corrections,t,cell['id'],len(cells));previous=states.get(key);missing_evidence_fallback=not general_safe and not desired.get('detectedTracks') and previous is None;immediate=hard_acquire or fast_acquire or (new_segment and segment.get('transitionIn') in ('hard_cut','editorial_cut'));view={'centerX':.5,'centerY':.5,'cropWidth':1,'cropHeight':1,'detectedTracks':[]} if missing_evidence_fallback else (desired if general_safe or immediate else _smooth_view(desired,previous,cell.get('sourcePolicy','subject_lock'),1/fps,local_tuning));states[key]=view
                rect=cell['outputRect'];left=int(round(rect[0]*width));top=int(round(rect[1]*height));right=int(round((rect[0]+rect[2])*width));bottom=int(round((rect[1]+rect[3])*height));left=clamp(left,0,width-1);top=clamp(top,0,height-1);right=clamp(right,left+1,width);bottom=clamp(bottom,top+1,height);cell_width=right-left;cell_height=bottom-top;canvas[top:bottom,left:right]=_general_frame(frame,cell_width,cell_height) if general_safe or missing_evidence_fallback else _crop(frame,view,cell_width,cell_height)
                by_track={str(row['trackId']):row for row in detections};available=[track for track in cell.get('trackIds',[]) if track in by_track];visible=[track for track in available if _inside(view,by_track[track]['box'])];sample['cells'].append({'cellId':cell['id'],'trackIds':cell.get('trackIds',[]),'availableTracks':available,'visibleTracks':visible,'blank':False if general_safe or missing_evidence_fallback else not bool(available),'evidenceFallback':missing_evidence_fallback,'view':{key:round(view[key],6) for key in ('centerX','centerY','cropWidth','cropHeight')}})
            last_segment=segment['id']
        last_directive=directive.get('id') if directive else last_directive
        writer.write(canvas);frame_number+=1
        if frame_number%sample_every==0 or frame_number==1:telemetry.append(sample)
        if progress_callback and (frame_number==1 or frame_number%max(1,int(fps*2))==0):progress_callback(min(1,frame_number/total))
    cap.release();writer.release();data={'fps':fps,'frames':frame_number,'width':width,'height':height,'samples':telemetry,'tuning':tuning,'captionSafeZone':{'left':.08,'right':.92,'top':.10,'bottom':.86},'geometrySafety':{'aspectPreserving':True,'independentAxisScaling':False,'borderlessCells':True,'cellGapPixels':0,'cellStrokePixels':0,'generalFallbackPreservesFullSource':True,'sourceWidth':source_width,'sourceHeight':source_height}}
    if telemetry_path:dump(telemetry_path,data)
    return data

def evaluate_telemetry(telemetry,composition,out_path=None):
    available=0;visible=0;blank=0;cell_samples=0;series=defaultdict(list)
    for sample in telemetry.get('samples',[]):
        for cell in sample.get('cells',[]):
            available+=len(cell.get('availableTracks',[]));visible+=len(cell.get('visibleTracks',[]));blank+=int(cell.get('blank',False));cell_samples+=1;series[(sample.get('segmentId'),cell['cellId'])].append((sample['time'],cell['view']['centerX'],cell['view']['centerY']))
    velocity_variation=[];acceleration=[]
    for rows in series.values():
        velocities=[]
        for first,second in zip(rows,rows[1:]):
            dt=max(.001,second[0]-first[0]);velocities.append(math.hypot(second[1]-first[1],second[2]-first[2])/dt)
        if len(velocities)>1:velocity_variation.append(pstdev(velocities));acceleration.extend(abs(b-a) for a,b in zip(velocities,velocities[1:]))
    coverage=visible/max(1,available) if available else 1;blank_rate=blank/max(1,cell_samples);velocity_std=mean(velocity_variation) if velocity_variation else 0;acceleration_mean=mean(acceleration) if acceleration else 0;jitter=min(1,velocity_std/.16+acceleration_mean/1.4);duration=max([sample['time'] for sample in telemetry.get('samples',[])] or [0]);switches=max(0,len(composition.get('segments',[]))-1);switch_rate=switches/max(1,duration/60)
    metrics={'requiredCoverageRate':round(coverage,4),'blankCellRate':round(blank_rate,4),'velocityStd':round(velocity_std,5),'meanAcceleration':round(acceleration_mean,5),'jitterScore':round(jitter,4),'layoutSwitchesPerMinute':round(switch_rate,3),'captionSafeZoneDeclared':bool(telemetry.get('captionSafeZone'))}
    failures=[key for key,threshold in QUALITY_THRESHOLDS.items() if (metrics[key]<threshold if key=='requiredCoverageRate' else metrics[key]>threshold)];score=coverage*.58+(1-jitter)*.27+(1-blank_rate)*.15;result={'metrics':metrics,'thresholds':QUALITY_THRESHOLDS,'failures':failures,'passed':not failures,'qualityScore':round(score,4)}
    if out_path:dump(out_path,result)
    return result

def propose_corrections(evaluation):
    failures=evaluation.get('failures',[]);return {'extraMargin':.055 if 'requiredCoverageRate' in failures else 0,'smoothingScale':1.65 if 'jitterScore' in failures else 1.15,'holdLastSeen':True,'reason':'Automatic Stage 3 correction for '+(', '.join(failures) if failures else 'quality margin')}

def _mux(video_path,silent_path,out_path,out_dir,subtitle_path=None):
    out_dir=Path(out_dir).resolve();cmd=['ffmpeg','-y','-i',Path(silent_path).name,'-i',str(Path(video_path).resolve())];ass=Path(subtitle_path).resolve() if subtitle_path else None
    if ass and ass.exists():
        local=out_dir/'subtitles.ass'
        if ass!=local and not local.exists():shutil.copy2(ass,local)
        cmd+=['-vf','ass=filename=subtitles.ass']
    cmd+=['-map','0:v','-map','1:a?','-c:v','libx264','-preset','veryfast','-crf','21','-c:a','aac','-shortest','-movflags','+faststart',str(Path(out_path).resolve())]
    result=subprocess.run(cmd,cwd=str(out_dir),capture_output=True,text=True)
    if result.returncode!=0:raise RuntimeError('Stage 3 final mux failed. '+'\n'.join((result.stderr or '').splitlines()[-12:]))

def render_stage3(video_path,composition,perception,out_path,out_dir,subtitle_path=None,width=1080,height=1920,corrections=None,progress=None):
    progress=progress or (lambda *_:None);out_dir=Path(out_dir);pass1=out_dir/'stage3-pass1-silent.mp4';progress('Stage 3 · multi-viewport render pass 1',72);telemetry1=render_silent(video_path,composition,perception,pass1,out_dir,width,height,{},corrections,lambda part:progress('Stage 3 · multi-viewport render pass 1',72+int(part*15)),out_dir/'render-telemetry-pass1.json');progress('Stage 3 · coverage and camera-motion evaluation',88);evaluation1=evaluate_telemetry(telemetry1,composition,out_dir/'render-evaluation-pass1.json');chosen=pass1;chosen_telemetry=telemetry1;chosen_evaluation=evaluation1;correction=None
    if not evaluation1['passed']:
        correction=propose_corrections(evaluation1);dump(out_dir/'render-corrections.json',correction);pass2=out_dir/'stage3-pass2-silent.mp4';progress('Stage 3 · automatic correction render',89);telemetry2=render_silent(video_path,composition,perception,pass2,out_dir,width,height,correction,corrections,lambda part:progress('Stage 3 · automatic correction render',89+int(part*7)),out_dir/'render-telemetry-pass2.json');evaluation2=evaluate_telemetry(telemetry2,composition,out_dir/'render-evaluation-pass2.json')
        if evaluation2['qualityScore']>=evaluation1['qualityScore']:chosen=pass2;chosen_telemetry=telemetry2;chosen_evaluation=evaluation2
    dump(out_dir/'render-telemetry.json',chosen_telemetry);summary={'pass1':evaluation1,'final':chosen_evaluation,'correctionApplied':bool(correction),'selectedPass':2 if chosen.name.startswith('stage3-pass2') else 1};dump(out_dir/'render-evaluation.json',summary);progress('Stage 3 · audio, captions and final verification',97);_mux(video_path,chosen,out_path,out_dir,subtitle_path);progress('Stage 3 complete · awaiting final quality supervision',97);return {'path':str(Path(out_path).resolve()),'frames':chosen_telemetry['frames'],'fps':chosen_telemetry['fps'],'width':width,'height':height,'quality':summary}
