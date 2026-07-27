from __future__ import annotations
import copy,math
from collections import defaultdict
from statistics import mean,median
from .common import clamp,dump
from .framing_intelligence import body_safe_box
from .multiview_render import _desired_view
from .dynamic_director import _stable_wide_layout,_focus_layout,_conversation_split_layout,_speaker_reaction_split_layout,_general_layout

SCHEMA_VERSION='1.1'
PERTURBATIONS=('base','drop_primary','jitter_left','jitter_right','confidence_loss')

def _overlap(segment,t):return float(segment.get('start',0))<=t<float(segment.get('end',0))
def _sample_frames(perception,start,end,limit=14):
    rows=[row for row in perception.get('frames',[]) if start<=float(row.get('time',-1))<end]
    if len(rows)<=limit:return rows
    step=max(1,len(rows)//limit);return rows[::step][:limit]

def _project(row,horizon):
    item=copy.deepcopy(row);vx,vy=item.get('worldVelocity',item.get('velocity',[0,0]));box=item.get('box',[0,0,1,1]);item['box']=[clamp(box[0]+vx*horizon,0,1),clamp(box[1]+vy*horizon,0,1),clamp(box[2]+vx*horizon,0,1),clamp(box[3]+vy*horizon,0,1)];return item

def _perturb(rows,kind,required,jitter_delta):
    result=copy.deepcopy(rows)
    if kind=='drop_primary' and required:
        result=[row for row in result if str(row.get('trackId'))!=str(required[0])]
    elif kind in ('jitter_left','jitter_right'):
        delta=-jitter_delta if kind=='jitter_left' else jitter_delta
        for row in result:
            box=row.get('box',[0,0,1,1]);row['box']=[clamp(box[0]+delta,0,1),box[1],clamp(box[2]+delta,0,1),box[3]]
    elif kind=='confidence_loss':
        for row in result:row['confidence']=float(row.get('confidence',.7))*.45
    return result

def _body_fit(view,row):
    safe=body_safe_box(row);left=view['centerX']-view['cropWidth']/2;right=view['centerX']+view['cropWidth']/2;top=view['centerY']-view['cropHeight']/2;bottom=view['centerY']+view['cropHeight']/2
    margin=min(safe[0]-left,right-safe[2],safe[1]-top,bottom-safe[3]);area=max(1e-9,(safe[2]-safe[0])*(safe[3]-safe[1]));visible=max(0,min(right,safe[2])-max(left,safe[0]))*max(0,min(bottom,safe[3])-max(top,safe[1]))/area
    return margin,clamp(visible,0,1)

def _segment_trials(segment,perception,source_width,source_height,horizons,jitter_delta,track_classes=None):
    frames=_sample_frames(perception,float(segment['start']),float(segment['end']));layout=segment.get('layout',{});cells=layout.get('cells',[]);results=[];centers=defaultdict(list);track_classes=track_classes or {}
    for frame in frames:
        base=frame.get('detections',[])
        for horizon in horizons:
            projected=[_project(row,horizon) for row in base]
            for perturbation in PERTURBATIONS:
                for cell in cells:
                    required=[str(track) for track in cell.get('trackIds',[])];human_required=[track for track in required if track_classes.get(track)=='person' or track.lower().startswith('person')];tuning=segment.get('editorial',{}).get('cameraTuning',{});rows=_perturb(projected,perturbation,human_required,jitter_delta);view={'centerX':.5,'centerY':.5,'cropWidth':1,'cropHeight':1} if cell.get('sourcePolicy')=='general_safe' else _desired_view(cell,rows,source_width,source_height,tuning);by_track={str(row.get('trackId')):row for row in rows};original={str(row.get('trackId')):row for row in projected};held=perturbation=='drop_primary' and tuning.get('holdLastSeen');evidence=original if held else by_track;present=[track for track in human_required if track in evidence];fits=[_body_fit(view,evidence[track]) for track in present];margins=[item[0] for item in fits];visibility=[item[1] for item in fits];coverage=len(present)/len(human_required) if human_required else 1;safe=sum(value>=0 for value in margins)/len(present) if present else 1;results.append({'time':round(float(frame.get('time',0)),3),'horizon':horizon,'perturbation':perturbation,'cellId':cell.get('id'),'coverage':round(coverage,3),'bodySafe':round(safe,3),'bodyVisibility':round(min(visibility or [1]),3),'minimumMargin':round(min(margins or [1]),4),'requiredHumanTracks':human_required,'center':[round(view['centerX'],4),round(view['centerY'],4)]})
                    if perturbation=='base' and horizon==0:centers[cell.get('id')].append((view['centerX'],view['centerY']))
    jumps=[]
    for rows in centers.values():jumps.extend(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(rows,rows[1:]))
    base=[row for row in results if row['perturbation']=='base'];current=[row for row in base if row['horizon']==0];future=[row for row in base if row['horizon']>0];perturbed=[row for row in results if row['perturbation']!='base'];return {'trials':results,'metrics':{'trialCount':len(results),'baseCoverage':round(mean([row['coverage'] for row in base] or [1]),4),'currentBodySafety':round(mean([row['bodySafe'] for row in current] or [1]),4),'minimumBodyVisibility':round(min([row['bodyVisibility'] for row in current] or [1]),4),'minimumCurrentMargin':round(min([row['minimumMargin'] for row in current] or [1]),4),'futureBodySafety':round(mean([row['bodySafe'] for row in future] or [1]),4),'perturbationCoverage':round(mean([row['coverage'] for row in perturbed] or [1]),4),'minimumFutureMargin':round(min([row['minimumMargin'] for row in future] or [1]),4),'typicalPlannedJump':round(_quantile(jumps,.5,0),4),'maximumPlannedJump':round(max(jumps or [0]),4)}}

def _plan_issues(composition,world,segment_reports,calibration):
    issues=[];segments=composition.get('segments',[]);situations={row['segmentId']:row for row in world.get('situations',[])}
    total=max(.001,sum(float(row['end'])-float(row['start']) for row in segments));fallback=sum(float(row['end'])-float(row['start']) for row in segments if row.get('layout',{}).get('layoutType')=='general_safe');misused=[row['id'] for row in segments if row.get('layout',{}).get('layoutType')=='general_safe' and not situations.get(row['id'],{}).get('evidenceVoid',True)]
    if misused:issues.append({'code':'fallback_overuse','severity':'P1','segmentIds':misused,'value':round(fallback/total,4),'decisionRule':'trustworthy evidence exists'})
    jump_reference=max(float(calibration.get('trackCenterVelocity',{}).get('upperQuartile',0))*float(calibration.get('segmentDuration',{}).get('median',1)),_quantile([row.get('metrics',{}).get('typicalPlannedJump',0) for row in segment_reports.values()],.75,0));body_reference=_quantile([row.get('metrics',{}).get('futureBodySafety',1) for row in segment_reports.values()],.25,1);drop_reference=_quantile([row.get('metrics',{}).get('perturbationCoverage',1) for row in segment_reports.values()],.25,1)
    for segment in segments:
        report=segment_reports.get(segment['id'],{}).get('metrics',{});segment_issues=[]
        base_coverage=float(report.get('baseCoverage',1))
        if base_coverage>0 and (report.get('minimumBodyVisibility',1)<.82 or (report.get('currentBodySafety',1)<.75 and report.get('minimumCurrentMargin',1)<-.02)):segment_issues.append('body_fragment')
        if base_coverage<.25 and segment.get('layout',{}).get('layoutType')!='general_safe':segment_issues.append('required_subject_missing')
        elif report.get('futureBodySafety',1)<min(.70,body_reference) and report.get('minimumFutureMargin',1)<-.03:segment_issues.append('predicted_subject_exit')
        if report.get('maximumPlannedJump',0)>jump_reference and jump_reference>0:segment_issues.append('camera_travel_spike')
        if report.get('perturbationCoverage',1)<=drop_reference and report.get('perturbationCoverage',1)<report.get('baseCoverage',1):segment_issues.append('detector_dropout_fragility')
        cells=segment.get('layout',{}).get('cells',[]);signatures=[tuple(sorted(str(track) for track in cell.get('trackIds',[]))) for cell in cells]
        if len(cells)>1 and (any(not signature for signature in signatures) or len(signatures)!=len(set(signatures))):segment_issues.append('redundant_split')
        for code in segment_issues:issues.append({'code':code,'severity':'P1' if code in ('body_fragment','required_subject_missing','predicted_subject_exit','redundant_split') else 'P2','segmentIds':[segment['id']],'metrics':report})
    for previous,current in zip(segments,segments[1:]):
        duration=float(current['end'])-float(current['start']);previous_focus=tuple(tuple(cell.get('trackIds',[])) for cell in previous.get('layout',{}).get('cells',[]));current_focus=tuple(tuple(cell.get('trackIds',[])) for cell in current.get('layout',{}).get('cells',[]));physical=current.get('dynamicDirector',{}).get('actionEpisodeIds')
        turn_reference=float(calibration.get('turnDuration',{}).get('lowerQuartile',duration));situation=situations.get(current['id'],{});dialogue=bool(situation.get('currentSpeakerTrackId') or situation.get('activeSpeakers'));valid_reference=math.isfinite(turn_reference) and .15<=turn_reference<=10
        if dialogue and valid_reference and duration<turn_reference and previous_focus!=current_focus and not physical:issues.append({'code':'hurried_dialogue_switch','severity':'P1','segmentIds':[current['id']],'value':duration,'adaptiveReference':turn_reference})
    return issues

def _track_classes(perception):
    classes=defaultdict(list)
    for frame in perception.get('frames',[]):
        for row in frame.get('detections',[]):classes[str(row.get('trackId'))].append(str(row.get('class','object')).lower())
    return {track:max(set(values),key=values.count) for track,values in classes.items() if values}

def _spatial_groups(tracks,perception,start=None,end=None,candidate_groups=None):
    frames=[frame for frame in perception.get('frames',[]) if (start is None or float(frame.get('time',-1))>=start) and (end is None or float(frame.get('time',-1))<end)]
    positions=defaultdict(list);presence=defaultdict(set)
    for frame_index,frame in enumerate(frames):
        for row in frame.get('detections',[]):
            track=str(row.get('trackId'))
            if track not in {str(x) for x in tracks} or str(row.get('class','')).lower()!='person':continue
            box=row.get('box',[0,0,1,1]);positions[track].append((box[0]+box[2])/2);presence[track].add(frame_index)
    if candidate_groups:
        groups=[];used=set()
        for group in candidate_groups[:2]:
            clean=[str(track) for track in group if str(track) in positions and str(track) not in used]
            if clean:groups.append(clean);used.update(clean)
    else:
        ordered=sorted(positions,key=lambda track:median(positions[track]))
        if len(ordered)<2:return []
        gaps=[(median(positions[b])-median(positions[a]),index+1) for index,(a,b) in enumerate(zip(ordered,ordered[1:]))]
        gap,cut=max(gaps);groups=[ordered[:cut],ordered[cut:]] if gap>=.16 else []
    if len(groups)<2:return []
    left_frames=set().union(*(presence[track] for track in groups[0]));right_frames=set().union(*(presence[track] for track in groups[1]));co_visible=len(left_frames&right_frames)
    centers=[median([x for track in group for x in positions[track]]) for group in groups]
    if abs(centers[0]-centers[1])<.16 or co_visible<max(1,int(len(frames)*.12)):return []
    return groups

def _viable_tracks(segment,situation,tracks):
    preferred=[str(x) for x in situation.get('reliablePreferredTrackIds',[])];required=[str(x) for x in situation.get('reliableRequiredTrackIds',[])];speaker=str(situation.get('currentSpeakerTrackId') or '')
    rows=list(dict.fromkeys(([speaker] if speaker and speaker in situation.get('reliableTrackIds',[]) else [])+preferred+required))
    return rows or [str(x) for x in tracks if str(x) not in set(situation.get('missingTrackIds',[]))]

def _repair(composition,issues,world=None,perception=None,aggressive=False,force_safe=False):
    result=copy.deepcopy(composition);by_id={row['id']:row for row in result.get('segments',[])};original={row['id']:row for row in composition.get('segments',[])};situations={row.get('segmentId'):row for row in (world or {}).get('situations',[])};repaired=[]
    for issue in issues:
        for segment_id in issue.get('segmentIds',[]):
            segment=by_id.get(segment_id)
            if not segment:continue
            code=issue['code'];tracks=[str(track) for track in segment.get('mustShowTrackIds',[])];situation=situations.get(segment_id,{})
            if force_safe and code in ('body_fragment','required_subject_missing','predicted_subject_exit'):
                viable=_viable_tracks(segment,situation,tracks)
                if situation.get('evidenceVoid') or not viable:
                    segment['layout']=_general_layout(segment,tracks);segment['confidenceFallback']=True
                else:
                    segment['mustShowTrackIds']=viable;segment['layout']=_stable_wide_layout(segment,viable);segment['confidenceFallback']=False
                segment['transitionIn']='hold'
            elif aggressive and code=='body_fragment':
                speaker=situation.get('currentSpeakerTrackId');candidate=situation.get('conversationGroups',[]);groups=_spatial_groups(tracks,perception or {},float(segment.get('start',0)),float(segment.get('end',0)),candidate) if candidate else []
                inferred=_spatial_groups(tracks,perception or {},float(segment.get('start',0)),float(segment.get('end',0)))
                if speaker and situation.get('hurriedBeat') and len(groups)>=2:segment['layout']=_speaker_reaction_split_layout(segment,groups)
                elif speaker:segment['layout']=_focus_layout(segment,[str(speaker)],'stable_subject')
                elif situation.get('physicalAction'):segment['layout']=_stable_wide_layout(segment,_viable_tracks(segment,situation,tracks) or tracks)
                elif len(groups)>=2:segment['layout']=_conversation_split_layout(segment,groups)
                elif len(inferred)>=2:segment['layout']=_conversation_split_layout(segment,inferred)
                else:segment['layout']=_stable_wide_layout(segment,_viable_tracks(segment,situation,tracks) or tracks)
                segment['transitionIn']='hold'
            elif aggressive and code=='required_subject_missing':
                viable=_viable_tracks(segment,situation,tracks)
                if situation.get('evidenceVoid') or not viable:segment['layout']=_general_layout(segment,tracks)
                else:segment['mustShowTrackIds']=viable;segment['layout']=_stable_wide_layout(segment,viable)
                segment['transitionIn']='hold'
            if code in ('fallback_overuse','redundant_split'):segment['layout']=_stable_wide_layout(segment,tracks);segment['transitionIn']='hold'
            elif code=='hurried_dialogue_switch':
                index=next((i for i,row in enumerate(result['segments']) if row['id']==segment_id),0)
                if index>0:segment['layout']=copy.deepcopy(result['segments'][index-1]['layout']);segment['transitionIn']='hold'
            elif code=='detector_dropout_fragility':
                tuning=segment.setdefault('editorial',{}).setdefault('cameraTuning',{});tuning['holdLastSeen']=True;tuning['smoothingScale']=max(1.2,float(tuning.get('smoothingScale',1)))
            elif not (force_safe and code in ('body_fragment','required_subject_missing','predicted_subject_exit')):
                tuning=segment.setdefault('editorial',{}).setdefault('cameraTuning',{});tuning['cropScale']=max(1.22,float(tuning.get('cropScale',1)));tuning['smoothingScale']=max(1.45,float(tuning.get('smoothingScale',1)));tuning['holdLastSeen']=True
                if code=='body_fragment':tuning['cropScale']=max(1.65 if aggressive else 1.45,float(tuning.get('cropScale',1)));tuning['minimumBodyVisibility']=.82
                if code=='required_subject_missing':tuning['holdLastSeen']=True;tuning['missingEvidenceFallback']='single_frame_only'
                if code=='predicted_subject_exit':
                    for cell in segment.get('layout',{}).get('cells',[]):
                        if segment.get('dynamicDirector',{}).get('actionEpisodeIds'):cell['sourcePolicy']='trajectory_follow'
            segment['predictiveGuard']={'repaired':True,'reason':code,'strategy':'last_resort_full_source' if force_safe else ('structural_retry' if aggressive else 'widen_and_hold')};repaired.append({'segmentId':segment_id,'code':code,'strategy':segment['predictiveGuard']['strategy'],'before':original.get(segment_id,{}).get('layout',{}).get('layoutType'),'after':segment.get('layout',{}).get('layoutType')})
    return result,repaired

def _quantile(values,q,default=0):
    rows=sorted(float(value) for value in values)
    if not rows:return default
    position=(len(rows)-1)*q;low=int(position);high=min(len(rows)-1,low+1);part=position-low;return rows[low]*(1-part)+rows[high]*part

def predictive_preflight(composition,perception,world,actions,risk_path,tests_path,progress=None,calibration=None):
    progress=progress or (lambda *_:None);progress('Predictive guard · simulating future motion and edge cases',67);calibration=calibration or {}
    # Perception stores `source` as the input path. Older fixtures stored a
    # metadata object there, so accepting both shapes keeps resumed projects
    # compatible and prevents calling `.get()` on a path string.
    source=perception.get('source')
    metadata=source if isinstance(source,dict) else perception.get('video',{})
    metadata=metadata if isinstance(metadata,dict) else {}
    source_width=int(perception.get('width',metadata.get('width',1920)) or 1920);source_height=int(perception.get('height',metadata.get('height',1080)) or 1080);segment_reference=float(calibration.get('segmentDuration',{}).get('median') or _quantile([float(row['end'])-float(row['start']) for row in composition.get('segments',[])],.5,1));turn_reference=float(calibration.get('turnDuration',{}).get('median',segment_reference));usable_turn=turn_reference if math.isfinite(turn_reference) and turn_reference<segment_reference*10 else segment_reference;horizons=tuple(round(value,4) for value in (0,segment_reference/4,segment_reference/2,min(segment_reference,usable_turn)));track_classes=_track_classes(perception);area_reference=float(calibration.get('subjectArea',{}).get('lowerQuartile',.01));jitter_delta=max(float(calibration.get('trackCenterVelocity',{}).get('upperQuartile',0))*segment_reference/4,math.sqrt(max(0,area_reference))/10);all_trials=[]
    def evaluate(plan,attempt):
        reports={}
        for segment in plan.get('segments',[]):
            report=_segment_trials(segment,perception,source_width,source_height,horizons,jitter_delta,track_classes);reports[segment['id']]=report;all_trials.extend({'attempt':attempt,'segmentId':segment['id'],**row} for row in report['trials'])
        return reports,_plan_issues(plan,world,reports,calibration)
    initial_reports,detected=evaluate(composition,0);repaired,repairs=_repair(composition,detected,world,perception);reports,issues=evaluate(repaired,1)
    critical=lambda rows:[row for row in rows if row.get('severity')=='P1' and row.get('code') in ('body_fragment','required_subject_missing','predicted_subject_exit')]
    if critical(issues):
        repaired,rows=_repair(repaired,critical(issues),world,perception,aggressive=True);repairs.extend(rows);reports,issues=evaluate(repaired,2)
    if critical(issues):
        repaired,rows=_repair(repaired,critical(issues),world,perception,force_safe=True);repairs.extend(rows);reports,issues=evaluate(repaired,3)
    release_blocked=any(row.get('severity') in ('P0','P1') for row in issues);risk={'schemaVersion':'1.2','stage':'predictive-reliability-guard','horizonsSeconds':list(horizons),'jitterDelta':round(jitter_delta,6),'perturbations':list(PERTURBATIONS),'segments':{key:value['metrics'] for key,value in reports.items()},'detectedIssues':detected,'issues':issues,'repairs':repairs,'summary':{'segments':len(reports),'simulatedTrials':len(all_trials),'detectedIssues':len(detected),'unresolvedIssues':len(issues),'repairedSegments':len(set(row['segmentId'] for row in repairs)),'releaseBlocked':release_blocked},'policy':{'predictBeforeRender':True,'minimumHumanBodyVisibility':.82,'retryUnsafeSceneBeforeRender':True,'structuralRetryBeforeFallback':True,'fullSourceIsLastResort':True,'unresolvedP1RequiresPixelReview':True,'scenarioBasedTesting':True,'metamorphicPerturbations':True,'adaptiveHorizons':True,'adaptiveJitterMagnitude':True,'adaptiveRiskReferences':True,'userDoesNotNeedToDiscoverKnownFailureClasses':True}};tests={'schemaVersion':'1.2','stage':'counterfactual-scenario-tests','trials':all_trials};dump(risk_path,risk);dump(tests_path,tests);progress('Predictive guard · repaired and re-verified foreseeable inconsistencies',68);return repaired,risk,tests
