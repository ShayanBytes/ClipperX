from __future__ import annotations
import copy,math
from collections import defaultdict
from statistics import mean,median
from .common import clamp,dump
from .dynamic_director import _general_layout,_stable_wide_layout,_focus_layout,_conversation_split_layout,_speaker_reaction_split_layout

SCHEMA_VERSION='1.1'

def _quantile(values,q,default=0):
    rows=sorted(float(value) for value in values)
    if not rows:return default
    position=(len(rows)-1)*q;low=int(position);high=min(len(rows)-1,low+1);part=position-low;return rows[low]*(1-part)+rows[high]*part

def _center(box):return ((box[0]+box[2])/2,(box[1]+box[3])/2)
def _area(box):return max(0,box[2]-box[0])*max(0,box[3]-box[1])
def _normalize(weights):
    total=sum(max(0,value) for value in weights.values()) or 1;return {key:max(0,value)/total for key,value in weights.items()}

def learn_video_calibration(perception,active,composition,world):
    confidences=[];speeds=[];areas=[];people=[];history=defaultdict(list)
    for frame in perception.get('frames',[]):
        count=0
        for row in frame.get('detections',[]):
            confidences.append(float(row.get('confidence',0)));box=row.get('box',[0,0,1,1]);areas.append(_area(box));vx,vy=row.get('worldVelocity',row.get('velocity',[0,0]));speeds.append(math.hypot(vx,vy));history[str(row.get('trackId'))].append((float(frame.get('time',0)),_center(box)));count+=str(row.get('class'))=='person'
        people.append(count)
    jumps=[]
    for rows in history.values():
        for first,second in zip(rows,rows[1:]):
            dt=max(.001,second[0]-first[0]);jumps.append(math.hypot(second[1][0]-first[1][0],second[1][1]-first[1][1])/dt)
    turns=[max(0,float(row.get('end',0))-float(row.get('start',0))) for row in active.get('segments',[])];segment_lengths=[max(.001,float(row['end'])-float(row['start'])) for row in composition.get('segments',[])];situations=world.get('situations',[]);evidence=[float(row.get('evidence',{}).get('mandatoryCoverage',0)) for row in situations];return {'schemaVersion':SCHEMA_VERSION,'method':'per-video robust empirical calibration','sampleCounts':{'detections':len(confidences),'tracks':len(history),'turns':len(turns),'segments':len(segment_lengths)},'detectionConfidence':{'lowerQuartile':round(_quantile(confidences,.25),4),'median':round(_quantile(confidences,.5),4),'upperQuartile':round(_quantile(confidences,.75),4)},'motionSpeed':{'median':round(_quantile(speeds,.5),5),'upperQuartile':round(_quantile(speeds,.75),5),'high':round(_quantile(speeds,.9),5)},'trackCenterVelocity':{'median':round(_quantile(jumps,.5),5),'upperQuartile':round(_quantile(jumps,.75),5)},'subjectArea':{'median':round(_quantile(areas,.5),5),'lowerQuartile':round(_quantile(areas,.25),5)},'peoplePerFrame':{'median':round(_quantile(people,.5),3),'upperQuartile':round(_quantile(people,.75),3)},'turnDuration':{'lowerQuartile':round(_quantile(turns,.25,99),4),'median':round(_quantile(turns,.5,99),4),'upperQuartile':round(_quantile(turns,.75,99),4)},'segmentDuration':{'median':round(_quantile(segment_lengths,.5,1),4)},'evidenceCoverage':{'lowerQuartile':round(_quantile(evidence,.25),4),'median':round(_quantile(evidence,.5),4)},'policy':{'fixedConfidenceCutoff':False,'fixedFallbackQuota':False,'calibratedAgainstCurrentVideo':True}}

def _observed(perception,start,end):
    frames=[row for row in perception.get('frames',[]) if start<=float(row.get('time',-1))<end];tracks=defaultdict(list)
    for frame in frames:
        for row in frame.get('detections',[]):tracks[str(row.get('trackId'))].append(row)
    return {track:{'visibility':len(rows)/max(1,len(frames)),'confidence':mean(float(row.get('confidence',0)) for row in rows),'area':mean(_area(row.get('box',[0,0,1,1])) for row in rows),'box':rows[-1].get('box',[0,0,1,1])} for track,rows in tracks.items()}

def _signature(layout):return (layout.get('layoutType'),tuple(tuple(sorted(str(track) for track in cell.get('trackIds',[]))) for cell in layout.get('cells',[])))
def _candidate_set(segment,situation):
    required=[str(track) for track in situation.get('requiredTrackIds',segment.get('mustShowTrackIds',[]))];preferred=[str(track) for track in situation.get('preferredTrackIds',required)] or required;candidates=[('proposed',copy.deepcopy(segment.get('layout',{}))),('stable_wide',_stable_wide_layout(segment,required)),('stable_subject',_focus_layout(segment,preferred,'stable_subject'))]
    if len(situation.get('conversationGroups',[]))>=2:
        layout=_speaker_reaction_split_layout(segment,situation['conversationGroups']) if situation.get('policy')=='speaker_reaction_split' else _conversation_split_layout(segment,situation['conversationGroups']);candidates.append(('conversation_groups',layout))
    if situation.get('evidenceVoid') or float(situation.get('evidence',{}).get('mandatoryCoverage',1))<.35 or not required:candidates.append(('complete_source',_general_layout(segment,required)))
    unique=[];seen=set();allowed=set(required);speaker=str(situation.get('currentSpeakerTrackId') or '')
    for name,layout in candidates:
        layout=copy.deepcopy(layout)
        for cell in layout.get('cells',[]):cell['trackIds']=[str(track) for track in cell.get('trackIds',[]) if str(track) in allowed]
        layout['cells']=[cell for cell in layout.get('cells',[]) if cell.get('trackIds') or layout.get('layoutType')=='general_safe']
        if situation.get('hurriedBeat') and (len(layout.get('cells',[]))>2 or (speaker and not any(speaker in cell.get('trackIds',[]) for cell in layout.get('cells',[])))):continue
        if not layout.get('cells'):continue
        signature=_signature(layout)
        if signature not in seen:seen.add(signature);unique.append((name,layout))
    return unique

def _disagreement(situation):
    evidence=situation.get('evidence',{});values=[float(evidence.get(key,0)) for key in ('mandatoryCoverage','visibility','detectionConfidence','continuityConfidence','storyConfidence')]
    if situation.get('physicalAction'):values.append(float(evidence.get('actionConfidence',0)))
    elif situation.get('activeSpeakers'):values.append(float(evidence.get('speakerConfidence',0)))
    center=mean(values) if values else 0;return math.sqrt(mean((value-center)**2 for value in values)) if values else 1

def _context_weights(segment,situation,calibration,importance):
    required=max(1,len(situation.get('requiredTrackIds',[])));scores=[float(row.get('score',0)) for row in importance];total=sum(scores) or 1;probabilities=[score/total for score in scores if score>0];entropy=-sum(value*math.log(value) for value in probabilities)/max(1,math.log(max(2,len(probabilities))));uncertainty=_disagreement(situation);turn_reference=max(.001,float(calibration['turnDuration']['median']));segment_duration=max(.001,float(segment['end'])-float(segment['start']));rapidness=turn_reference/segment_duration;motion_reference=max(.0001,float(calibration['motionSpeed']['upperQuartile']));motion_pressure=float(calibration['motionSpeed']['high'])/motion_reference;raw={'coverage':1+math.log1p(required),'story':1+entropy,'geometry':1+motion_pressure,'temporal':1+rapidness,'clarity':1+(1-uncertainty),'robustness':1+uncertainty};return _normalize(raw)

def _candidate_features(layout,segment,situation,observed,previous_signature,calibration):
    required=[str(track) for track in situation.get('requiredTrackIds',[])];importance={str(row.get('trackId')):float(row.get('score',0)) for row in situation.get('importance',[])};assigned={str(track) for cell in layout.get('cells',[]) for track in cell.get('trackIds',[])};covered=[track for track in required if track in assigned];coverage=len(covered)/max(1,len(required));story=sum(importance.get(track,0) for track in covered)/max(.0001,sum(importance.values()) or 1);observed_required=[observed[track] for track in covered if track in observed];evidence_strength=mean(row['visibility']*row['confidence'] for row in observed_required) if observed_required else 0;layout_type=layout.get('layoutType','unknown');complete=layout_type=='general_safe';cells=layout.get('cells',[]);geometry_parts=[]
    for cell in cells:
        boxes=[observed[str(track)]['box'] for track in cell.get('trackIds',[]) if str(track) in observed]
        if not boxes:geometry_parts.append(1 if complete else 0);continue
        span=max(box[2] for box in boxes)-min(box[0] for box in boxes);geometry_parts.append(clamp(1-span,0,1))
    geometry=mean(geometry_parts) if geometry_parts else 0;temporal=1 if previous_signature is None or _signature(layout)==previous_signature else clamp((float(segment['end'])-float(segment['start']))/max(.001,float(calibration['turnDuration']['median'])),0,1);subject_area=mean(row['area'] for row in observed_required) if observed_required else 0;area_reference=max(.0001,float(calibration['subjectArea']['median']));clarity=clamp(subject_area/area_reference,0,1)
    if complete:clarity=clamp((1-evidence_strength)*(1-subject_area),0,1);geometry=1
    robustness=1 if complete else clamp((coverage+geometry+evidence_strength)/3,0,1);return {'coverage':coverage,'story':story,'geometry':geometry,'temporal':temporal,'clarity':clarity,'robustness':robustness,'evidenceStrength':evidence_strength,'completeSource':complete}

def _track_set(candidate):return {str(track) for cell in candidate['layout'].get('cells',[]) for track in cell.get('trackIds',[])}
def _jaccard(left,right):
    union=set(left)|set(right);return len(set(left)&set(right))/len(union) if union else 1

def _uncertainty(features,situation,samples):
    values=[float(features[key]) for key in ('coverage','story','geometry','clarity','robustness')];center=mean(values);dispersion=math.sqrt(mean((value-center)**2 for value in values));evidence_disagreement=_disagreement(situation);support=math.sqrt(max(1,samples));return clamp((dispersion+evidence_disagreement)/support,0,1)

def _transition_value(previous,current,previous_situation,current_situation):
    previous_tracks=_track_set(previous);current_tracks=_track_set(current);shot_similarity=_jaccard(previous_tracks,current_tracks);same_layout=previous['layoutType']==current['layoutType'];required_similarity=_jaccard(previous_situation.get('requiredTrackIds',[]),current_situation.get('requiredTrackIds',[]));story_change=1-required_similarity;visual_continuity=(shot_similarity+(1 if same_layout else 0))/2;return clamp(story_change+(1-story_change)*visual_continuity,0,1)

def optimize_sequence(layers,situations):
    if not layers:return [],{'pathScore':0,'runnerUpScore':0,'sequenceMargin':0,'transitions':[]}
    scores=[];backs=[]
    for index,layer in enumerate(layers):
        row_scores=[];row_backs=[]
        for current_index,current in enumerate(layer['candidates']):
            emission=float(current['riskAdjustedUtility'])
            if index==0:row_scores.append(emission);row_backs.append(None);continue
            options=[]
            for previous_index,previous in enumerate(layers[index-1]['candidates']):
                transition=_transition_value(previous,current,situations[index-1],situations[index]);temporal_weight=float(layer['weights'].get('temporal',0));options.append((scores[index-1][previous_index]+emission+temporal_weight*transition,previous_index))
            best=max(options,key=lambda row:row[0]);row_scores.append(best[0]);row_backs.append(best[1])
        scores.append(row_scores);backs.append(row_backs)
    ranking=sorted(enumerate(scores[-1]),key=lambda row:row[1],reverse=True);cursor=ranking[0][0];path=[]
    for index in range(len(layers)-1,-1,-1):path.append(cursor);cursor=backs[index][cursor] if index else None
    path.reverse();transitions=[]
    for index in range(1,len(path)):
        transitions.append({'fromSegmentId':layers[index-1]['segmentId'],'toSegmentId':layers[index]['segmentId'],'value':round(_transition_value(layers[index-1]['candidates'][path[index-1]],layers[index]['candidates'][path[index]],situations[index-1],situations[index]),6)})
    runner=ranking[1][1] if len(ranking)>1 else ranking[0][1];return path,{'pathScore':round(ranking[0][1],6),'runnerUpScore':round(runner,6),'sequenceMargin':round(ranking[0][1]-runner,6),'transitions':transitions}

def apply_adaptive_intelligence(composition,perception,active,world,calibration_path,utility_path,sequence_path=None,progress=None):
    progress=progress or (lambda *_:None);progress('Adaptive intelligence · calibrating to this video',66);result=copy.deepcopy(composition);calibration=learn_video_calibration(perception,active,result,world);situation_map={row['segmentId']:row for row in world.get('situations',[])};layers=[];ordered_situations=[]
    for segment in result.get('segments',[]):
        situation=situation_map.get(segment['id'],{'requiredTrackIds':segment.get('mustShowTrackIds',[]),'preferredTrackIds':segment.get('mustShowTrackIds',[]),'importance':[],'evidence':{}});ordered_situations.append(situation);observed=_observed(perception,float(segment['start']),float(segment['end']));weights=_context_weights(segment,situation,calibration,situation.get('importance',[]));candidates=[]
        for name,layout in _candidate_set(segment,situation):
            features=_candidate_features(layout,segment,situation,observed,None,calibration);utility=sum(weights[key]*features[key] for key in weights);uncertainty=_uncertainty(features,situation,calibration['sampleCounts']['detections']);risk_adjusted=utility-weights['robustness']*uncertainty;candidates.append({'name':name,'layoutType':layout.get('layoutType'),'utility':round(utility,6),'uncertainty':round(uncertainty,6),'riskAdjustedUtility':round(risk_adjusted,6),'features':{key:round(value,6) if isinstance(value,float) else value for key,value in features.items()},'layout':layout})
        candidates.sort(key=lambda row:row['riskAdjustedUtility'],reverse=True);layers.append({'segmentId':segment['id'],'weights':weights,'candidates':candidates})
    path,sequence=optimize_sequence(layers,ordered_situations);decisions=[]
    for index,(segment,layer,selected_index) in enumerate(zip(result.get('segments',[]),layers,path)):
        winner=layer['candidates'][selected_index];greedy=layer['candidates'][0];runner=layer['candidates'][1] if len(layer['candidates'])>1 else greedy;segment['layout']=copy.deepcopy(winner['layout']);segment['adaptiveIntelligence']={'selected':winner['name'],'utility':winner['utility'],'riskAdjustedUtility':winner['riskAdjustedUtility'],'decisionMargin':round(winner['riskAdjustedUtility']-runner['riskAdjustedUtility'],6),'sequenceOptimized':winner['name']!=greedy['name'],'fallbackSelectedBecauseBestUtility':winner['name']=='complete_source','fallbackSelectedBecauseBestSequenceUtility':winner['name']=='complete_source'};decisions.append({'segmentId':segment['id'],'weights':{key:round(value,6) for key,value in layer['weights'].items()},'selected':winner['name'],'greedyLocalWinner':greedy['name'],'selectedLayoutType':winner['layoutType'],'decisionMargin':segment['adaptiveIntelligence']['decisionMargin'],'candidates':[{key:value for key,value in row.items() if key!='layout'} for row in layer['candidates']]})
    sequence_report={'schemaVersion':SCHEMA_VERSION,'stage':'sequence-level-editing-graph','selectedPath':[row['selected'] for row in decisions],**sequence,'policy':{'globalPathOptimization':True,'transitionContinuity':True,'storyChangesPermitMotivatedCuts':True,'isolatedFallbackRegretEvaluated':True}}
    report={'schemaVersion':SCHEMA_VERSION,'stage':'adaptive-utility-director','calibration':calibration,'decisions':decisions,'sequenceOptimization':sequence_report,'summary':{'segments':len(decisions),'fallbackSelections':sum(row['selected']=='complete_source' for row in decisions),'advancedSelections':sum(row['selected']!='complete_source' for row in decisions),'sequenceOverrides':sum(row['selected']!=row['greedyLocalWinner'] for row in decisions),'meanDecisionMargin':round(mean([row['decisionMargin'] for row in decisions] or [0]),6)},'policy':{'candidateArgmaxInsteadOfFixedThreshold':True,'fallbackHasNoSpecialPriority':True,'fallbackMustWinSequenceUtility':True,'calibrationIsPerVideo':True,'riskAdjustedMultiHypothesisScoring':True,'greedySegmentSelection':False}};dump(calibration_path,calibration);dump(utility_path,report);dump(sequence_path,sequence_report) if sequence_path else None;progress('Adaptive intelligence · globally optimized camera sequence',67);return result,calibration,report
