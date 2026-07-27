from __future__ import annotations
import base64,copy,json,math,os,re,subprocess,time
from pathlib import Path
from statistics import mean
import cv2,numpy as np,requests
from .common import clamp,dump,load
from .multiview_render import render_silent,evaluate_telemetry,_mux
from .dynamic_director import safety_fallback_plan,apply_safety_fallback,safety_risk_score

THRESHOLDS={'requiredCoverageRate':.94,'actionPhaseCoverage':.90,'blankCellRate':.12,'faceClippingRate':.10,'bodyClippingRate':.08,'subtitleCollisionRate':.14,'blackFrameRate':.01,'freezeRate':.10,'blurRate':.45,'avDurationDriftSeconds':.30}

def _segment_map(composition):return {segment['id']:segment for segment in composition.get('segments',[])}
def _nearest(rows,t):return min(rows,key=lambda row:abs(row.get('time',0)-t)) if rows else None

def action_phase_coverage(telemetry,actions):
    rows=[];samples=telemetry.get('samples',[])
    for episode in actions.get('episodes',[]):
        all_required=set(episode.get('mustShowTrackIds',[]));phase_results={}
        for name,span in episode.get('phases',{}).items():
            if not isinstance(span,list) or len(span)!=2:continue
            if name=='reaction':required=set(episode.get('reactorTrackIds',[])) or all_required
            elif name in ('anticipation','action'):required=set(episode.get('actorTrackIds',[])+episode.get('objectTrackIds',[])+episode.get('targetTrackIds',[])) or all_required
            else:required=set(episode.get('objectTrackIds',[])+episode.get('targetTrackIds',[])) or all_required
            phase_samples=[sample for sample in samples if span[0]<=sample.get('time',-1)<=span[1]];scores=[]
            for sample in phase_samples:
                visible={track for cell in sample.get('cells',[]) for track in cell.get('visibleTracks',[])};scores.append(len(required&visible)/max(1,len(required)))
            phase_results[name]=round(mean(scores) if scores else 0,4)
        rows.append({'actionId':episode['id'],'requiredTrackIds':sorted(all_required),'phases':phase_results,'minimumCoverage':round(min(phase_results.values()) if phase_results else 0,4),'verifiedOutcome':bool(episode.get('verification',{}).get('verified'))})
    return rows

def _intersection_ratio(box,view):
    crop=[view['centerX']-view['cropWidth']/2,view['centerY']-view['cropHeight']/2,view['centerX']+view['cropWidth']/2,view['centerY']+view['cropHeight']/2];x1=max(box[0],crop[0]);y1=max(box[1],crop[1]);x2=min(box[2],crop[2]);y2=min(box[3],crop[3]);inter=max(0,x2-x1)*max(0,y2-y1);area=max(1e-8,(box[2]-box[0])*(box[3]-box[1]));return inter/area

def face_and_caption_metrics(telemetry,perception,composition,subtitle_events=None):
    segments=_segment_map(composition);frames=perception.get('frames',[]);face_total=0;face_clipped=0;body_total=0;body_clipped=0;caption_checks=0;caption_collisions=0;by_segment={}
    for sample in telemetry.get('samples',[]):
        segment=segments.get(sample.get('segmentId'));frame=_nearest(frames,sample.get('time',0))
        if not segment or not frame:continue
        cells={cell.get('id',cell.get('cellId')):cell for cell in segment.get('layout',{}).get('cells',[])};telemetry_cells={cell.get('cellId',cell.get('id')):cell for cell in sample.get('cells',[])};active_caption=any(event['start']<=sample['time']<=event['end'] for event in (subtitle_events or []))
        for detection in frame.get('detections',[]):
            if str(detection.get('class','')).lower()!='person':continue
            track=str(detection.get('trackId'));assigned=next((cell for cell in cells.values() if track in cell.get('trackIds',[])),None);assigned_id=assigned.get('id',assigned.get('cellId')) if assigned else None
            if not assigned or assigned_id not in telemetry_cells:continue
            ratio=_intersection_ratio(detection['box'],telemetry_cells[assigned_id]['view']);body_total+=1;bucket=by_segment.setdefault(segment['id'],{'faceChecks':0,'clipped':0,'bodyChecks':0,'bodyClipped':0,'captionCollisions':0});bucket['bodyChecks']+=1
            if ratio<.97:body_clipped+=1;bucket['bodyClipped']+=1
        for face in frame.get('faces',[]):
            track=str(face.get('personTrackId'))
            if not track:continue
            assigned=next((cell for cell in cells.values() if track in cell.get('trackIds',[])),None)
            assigned_id=assigned.get('id',assigned.get('cellId')) if assigned else None
            if not assigned or assigned_id not in telemetry_cells:continue
            view=telemetry_cells[assigned_id]['view'];ratio=_intersection_ratio(face['box'],view);face_total+=1
            if ratio<.9:face_clipped+=1;by_segment.setdefault(segment['id'],{'faceChecks':0,'clipped':0,'bodyChecks':0,'bodyClipped':0,'captionCollisions':0})['clipped']+=1
            bucket=by_segment.setdefault(segment['id'],{'faceChecks':0,'clipped':0,'bodyChecks':0,'bodyClipped':0,'captionCollisions':0});bucket['faceChecks']+=1
            if active_caption:
                fx=(face['box'][0]+face['box'][2])/2;fy=(face['box'][1]+face['box'][3])/2;relative_x=(fx-(view['centerX']-view['cropWidth']/2))/max(1e-6,view['cropWidth']);relative_y=(fy-(view['centerY']-view['cropHeight']/2))/max(1e-6,view['cropHeight']);rect=assigned['outputRect'];output_x=rect[0]+relative_x*rect[2];output_y=rect[1]+relative_y*rect[3];caption_checks+=1
                if .08<=output_x<=.92 and .69<=output_y<=.89:caption_collisions+=1;bucket['captionCollisions']+=1
    return {'faceClippingRate':round(face_clipped/max(1,face_total),4),'bodyClippingRate':round(body_clipped/max(1,body_total),4),'subtitleCollisionRate':round(caption_collisions/max(1,caption_checks),4),'faceChecks':face_total,'bodyChecks':body_total,'captionChecks':caption_checks,'segments':by_segment}

def _ass_time(value):
    parts=value.split(':');return int(parts[0])*3600+int(parts[1])*60+float(parts[2])
def parse_ass_events(path):
    if not path or not Path(path).exists():return []
    rows=[]
    for line in Path(path).read_text(encoding='utf-8',errors='ignore').splitlines():
        if not line.startswith('Dialogue:'):continue
        parts=line.split(',',9)
        if len(parts)>=4:
            try:rows.append({'start':_ass_time(parts[1]),'end':_ass_time(parts[2])})
            except Exception:pass
    return rows

def inspect_output(video_path):
    cap=cv2.VideoCapture(str(video_path));fps=cap.get(cv2.CAP_PROP_FPS) or 30;frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0);sample_every=max(1,int(fps));black=blurred=frozen=0;sampled=0;previous=None;brightness=[];sharpness=[]
    for index in range(frames):
        ok,frame=cap.read()
        if not ok:break
        if index%sample_every:continue
        small=cv2.resize(frame,(180,320));gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY);light=float(gray.mean());sharp=float(cv2.Laplacian(gray,cv2.CV_64F).var());brightness.append(light);sharpness.append(sharp);black+=int(light<8);blurred+=int(sharp<18)
        if previous is not None:frozen+=int(float(cv2.absdiff(gray,previous).mean())<.35)
        previous=gray;sampled+=1
    cap.release();duration=frames/max(1,fps)
    return {'duration':round(duration,3),'sampledFrames':sampled,'blackFrameRate':round(black/max(1,sampled),4),'blurRate':round(blurred/max(1,sampled),4),'freezeRate':round(frozen/max(1,sampled-1),4),'meanBrightness':round(mean(brightness) if brightness else 0,2),'meanSharpness':round(mean(sharpness) if sharpness else 0,2)}

def av_duration_drift(video_path):
    command=['ffprobe','-v','error','-show_entries','stream=codec_type,duration','-of','json',str(video_path)]
    try:
        data=json.loads(subprocess.run(command,capture_output=True,text=True,check=True).stdout);durations={}
        for stream in data.get('streams',[]):
            if stream.get('duration') not in (None,'N/A'):durations[stream['codec_type']]=float(stream['duration'])
        drift=abs(durations.get('video',0)-durations.get('audio',durations.get('video',0)));return {'streams':durations,'driftSeconds':round(drift,4)}
    except Exception as exc:return {'streams':{},'driftSeconds':0,'error':str(exc)}

def assess_quality(output_path,telemetry,composition,perception,actions,subtitle_path=None):
    base=evaluate_telemetry(telemetry,composition);action_rows=action_phase_coverage(telemetry,actions);action_coverage=min([row['minimumCoverage'] for row in action_rows] or [1]);face=face_and_caption_metrics(telemetry,perception,composition,parse_ass_events(subtitle_path));visual=inspect_output(output_path);sync=av_duration_drift(output_path);metrics={**base['metrics'],'actionPhaseCoverage':round(action_coverage,4),'faceClippingRate':face['faceClippingRate'],'bodyClippingRate':face['bodyClippingRate'],'subtitleCollisionRate':face['subtitleCollisionRate'],'blackFrameRate':visual['blackFrameRate'],'freezeRate':visual['freezeRate'],'blurRate':visual['blurRate'],'avDurationDriftSeconds':sync['driftSeconds']};failures=[]
    for key,threshold in THRESHOLDS.items():
        value=metrics.get(key,0);failed=value<threshold if key in ('requiredCoverageRate','actionPhaseCoverage') else value>threshold
        if failed:failures.append(key)
    score=metrics['requiredCoverageRate']*.20+metrics['actionPhaseCoverage']*.20+(1-metrics['faceClippingRate'])*.10+(1-metrics['bodyClippingRate'])*.10+(1-metrics['subtitleCollisionRate'])*.07+(1-metrics['jitterScore'])*.12+(1-metrics['blackFrameRate'])*.07+(1-metrics['freezeRate'])*.06+(1-min(1,metrics['avDurationDriftSeconds']))*.08
    return {'metrics':metrics,'thresholds':THRESHOLDS,'failures':failures,'passed':not failures,'qualityScore':round(clamp(score,0,1),4),'actionCoverage':action_rows,'faceAndCaption':face,'visualOutput':visual,'audioVideoSync':sync}

def correction_plan(report,composition,actions=None):
    failing_segments=set();episodes={row['id']:row for row in (actions or {}).get('episodes',[])}
    for row in report.get('actionCoverage',[]):
        if row['minimumCoverage']<THRESHOLDS['actionPhaseCoverage']:
            episode=episodes.get(row['actionId'],{});start=episode.get('start',-1);end=episode.get('end',-1)
            for segment in composition.get('segments',[]):
                if segment['end']>start and segment['start']<end:failing_segments.add(segment['id'])
    for segment_id,values in report.get('faceAndCaption',{}).get('segments',{}).items():
        if values.get('clipped',0)/max(1,values.get('faceChecks',0))>.1 or values.get('bodyClipped',0)/max(1,values.get('bodyChecks',0))>.08 or values.get('captionCollisions',0)>0:failing_segments.add(segment_id)
    if report['metrics'].get('requiredCoverageRate',1)<.94:failing_segments.update(segment['id'] for segment in composition.get('segments',[]))
    correctable=bool(failing_segments) or report['metrics'].get('jitterScore',0)>.34
    return {'apply':correctable,'segmentIds':sorted(failing_segments),'widenFactor':1.14,'smoothingFactor':1.35 if report['metrics'].get('jitterScore',0)>.34 else 1.08,'reasonCodes':[failure for failure in report.get('failures',[]) if failure in ('requiredCoverageRate','actionPhaseCoverage','faceClippingRate','bodyClippingRate','subtitleCollisionRate','jitterScore')]}

def patch_composition(composition,plan):
    result=copy.deepcopy(composition)
    for segment in result.get('segments',[]):
        if segment['id'] not in plan.get('segmentIds',[]) and plan.get('segmentIds'):continue
        tuning=segment.setdefault('editorial',{}).setdefault('cameraTuning',{});tuning['cropScale']=round(max(1,float(tuning.get('cropScale',1)))*plan.get('widenFactor',1.1),3);tuning['smoothingScale']=round(float(tuning.get('smoothingScale',1))*plan.get('smoothingFactor',1.1),3);segment['editorial']['stage8Correction']=True
    return result

def build_contact_sheet(video_path,out_path,columns=3,rows=3):
    cap=cv2.VideoCapture(str(video_path));frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0);images=[]
    for index in np.linspace(0,max(0,frames-1),columns*rows).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES,int(index));ok,frame=cap.read()
        if ok:images.append(cv2.resize(frame,(240,426)))
    cap.release()
    if not images:return None
    while len(images)<columns*rows:images.append(np.zeros_like(images[0]))
    sheet=np.vstack([np.hstack(images[row*columns:(row+1)*columns]) for row in range(rows)]);cv2.imwrite(str(out_path),sheet,[cv2.IMWRITE_JPEG_QUALITY,82]);return str(out_path)

def _gemini_critique(model,key,contact_sheet,report):
    if not (model and key and contact_sheet):return {'used':False}
    image=base64.b64encode(Path(contact_sheet).read_bytes()).decode();prompt='You are a strict final-video quality supervisor. Inspect this chronological contact sheet and the deterministic metrics. Report only visible, actionable issues. Do not invent timestamps or identities. Return JSON {"overall":"pass|needs_attention","confidence":0.0,"issues":[{"category":"framing|continuity|readability|artifact","severity":"low|medium|high","description":"..."}]}. METRICS:'+json.dumps(report.get('metrics',{}),separators=(',',':'))
    url='https://'+'generativelanguage.googleapis.com/v1beta/models/'+str(model)+':generateContent?key='+str(key);body={'contents':[{'parts':[{'text':prompt},{'inline_data':{'mime_type':'image/jpeg','data':image}}]}],'generationConfig':{'responseMimeType':'application/json','temperature':.05}};error=None
    for attempt in range(3):
        try:
            response=requests.post(url,json=body,timeout=120)
            if response.status_code in (429,500,502,503,504):raise RuntimeError(f'temporary provider error {response.status_code}')
            response.raise_for_status();text=response.json()['candidates'][0]['content']['parts'][0]['text'];text=text.strip().removeprefix('```json').removesuffix('```').strip();return {'used':True,'provider':'gemini','result':json.loads(text)}
        except Exception as exc:error=exc;time.sleep(attempt+1)
    return {'used':False,'error':str(error)}

def benchmark_report(assessment,ai_critique=None):
    metrics=assessment['metrics'];categories={'storyCoverage':round((metrics['requiredCoverageRate']+metrics['actionPhaseCoverage'])/2,4),'compositionSafety':round(1-(metrics.get('faceClippingRate',0)*.38+metrics.get('bodyClippingRate',0)*.42+metrics.get('subtitleCollisionRate',0)*.20),4),'cameraQuality':round(1-metrics['jitterScore'],4),'renderIntegrity':round(1-(metrics['blackFrameRate']*.45+metrics['freezeRate']*.35+min(1,metrics['avDurationDriftSeconds'])*.2),4)}
    return {'schemaVersion':'1.0','stage':'stage-8-benchmark-lab','categories':categories,'overallScore':assessment['qualityScore'],'passed':assessment['passed'],'failedGates':assessment['failures'],'aiCritique':ai_critique or {'used':False},'policy':{'deterministicGatesOverrideAiOpinion':True,'singleTargetedCorrectionMaximum':True}}

def supervise_render(source_path,output_path,composition,perception,actions,subtitle_path,out_dir,width,height,provider=None,model=None,api_key=None,progress=None):
    progress=progress or (lambda *_:None);out_dir=Path(out_dir);progress('Stage 8 · inspecting final pixels and narrative coverage',98);telemetry=load(out_dir/'render-telemetry.json',{}) or {};first=assess_quality(output_path,telemetry,composition,perception,actions,subtitle_path);plan=correction_plan(first,composition,actions);selected=first;selected_pass=1;corrected_composition=None
    if plan['apply']:
        progress('Stage 8 · bounded targeted correction render',99);dump(out_dir/'stage8-corrections.json',plan);corrected_composition=patch_composition(composition,plan);dump(out_dir/'composition-stage8-corrected.json',corrected_composition);silent=out_dir/'stage8-corrected-silent.mp4';candidate=out_dir/'stage8-corrected-output.mp4';candidate_telemetry=render_silent(source_path,corrected_composition,perception,silent,out_dir,width,height,{},[],lambda _:None,out_dir/'stage8-corrected-telemetry.json');_mux(source_path,silent,candidate,out_dir,subtitle_path);second=assess_quality(candidate,candidate_telemetry,corrected_composition,perception,actions,subtitle_path)
        first_risk=safety_risk_score(first);second_risk=safety_risk_score(second)
        if second_risk<first_risk-.001 or (second_risk<=first_risk+.001 and second['qualityScore']>first['qualityScore']+.002):
            os.replace(candidate,output_path);dump(out_dir/'render-telemetry.json',candidate_telemetry);selected=second;selected_pass=2;composition=corrected_composition
        else:
            try:candidate.unlink()
            except FileNotFoundError:pass
    fallback_plan=safety_fallback_plan(selected,composition)
    if fallback_plan['apply']:
        progress('Closed-loop critic · testing conservative safety fallback',99);dump(out_dir/'closed-loop-fallback.json',fallback_plan);fallback_composition=apply_safety_fallback(composition,fallback_plan);dump(out_dir/'composition-closed-loop-fallback.json',fallback_composition);silent=out_dir/'closed-loop-fallback-silent.mp4';candidate=out_dir/'closed-loop-fallback-output.mp4';candidate_telemetry=render_silent(source_path,fallback_composition,perception,silent,out_dir,width,height,{},[],lambda _:None,out_dir/'closed-loop-fallback-telemetry.json');_mux(source_path,silent,candidate,out_dir,subtitle_path);fallback_assessment=assess_quality(candidate,candidate_telemetry,fallback_composition,perception,actions,subtitle_path);old_risk=safety_risk_score(selected);new_risk=safety_risk_score(fallback_assessment)
        if new_risk<old_risk-.001 or (new_risk<=old_risk+.001 and fallback_assessment['qualityScore']>selected['qualityScore']+.002):
            os.replace(candidate,output_path);dump(out_dir/'render-telemetry.json',candidate_telemetry);selected=fallback_assessment;selected_pass=3;composition=fallback_composition
        else:
            try:candidate.unlink()
            except FileNotFoundError:pass
    contact=build_contact_sheet(output_path,out_dir/'quality-contact-sheet.jpg');ai={'used':False,'reason':'Only Gemini contact-sheet critique is enabled'}
    if provider=='gemini' and model and api_key:ai=_gemini_critique(model,api_key,contact,selected)
    summary={'stage':'stage-8-multimodal-quality-supervisor','pass1':first,'final':selected,'selectedPass':selected_pass,'correction':plan,'closedLoopFallback':fallback_plan,'finalSafetyRisk':safety_risk_score(selected),'selectionPolicy':'lowest deterministic safety risk, then highest quality','aiCritique':ai,'contactSheet':'quality-contact-sheet.jpg' if contact else None};dump(out_dir/'quality-supervisor.json',summary);benchmark=benchmark_report(selected,ai);benchmark['policy']['closedLoopSafetyFallback']=True;benchmark['policy']['riskMagnitudeBeforeAestheticScore']=True;dump(out_dir/'benchmark-report.json',benchmark);progress('Stage 8 complete · benchmark gates finalized',100);return {'qualitySupervisor':summary,'benchmark':benchmark,'composition':composition}
