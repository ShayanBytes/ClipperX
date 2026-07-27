from __future__ import annotations
import json,math
from collections import defaultdict
from pathlib import Path
from statistics import median
from .common import clamp,center,dump
from .framing_intelligence import prepare_moment,moment_geometry,allow_split,body_safe_box,aspect_safe_crop,cell_utility
from .story_graph import _gemini_generate,_chat_generate

SCHEMA_VERSION='2.0'
LAYOUTS={'single_focus','shared_wide','split_2_stack','grid_4','bands_2x3','grid_6','action_pan','action_wide'}

def _unique(values):return list(dict.fromkeys(str(value) for value in values if value is not None))

def _moments(graph):
    events=sorted(graph.get('events',[]),key=lambda event:(event['start'],event['end']));moments=[]
    for event in events:
        start=max(0,float(event['start'])-float(event.get('anticipationSeconds',0) or 0) if event.get('keepContinuousAction') else float(event['start']));end=float(event['end'])
        item={'id':f'm{len(moments)}','start':start,'end':end,'eventIds':[event['id']],'type':event.get('type','context'),'narrativeRole':event.get('narrativeRole','context'),'summary':event.get('summary',''),'mustShowTrackIds':_unique(event.get('mustShowTrackIds',[])),'optionalTrackIds':_unique(event.get('optionalTrackIds',[])),'importance':float(event.get('importance',.5)),'confidence':float(event.get('confidence',.5)),'keepContinuousAction':bool(event.get('keepContinuousAction')),'anticipationSeconds':float(event.get('anticipationSeconds',0) or 0),'coverageRequirements':event.get('coverageRequirements',{}),'directingHint':event.get('directingHint',{})}
        if moments and item['start']<moments[-1]['end']-.2:
            previous=moments[-1]
            simultaneous=bool(event.get('simultaneityGroupId')) or item['narrativeRole'] in ('reaction','payoff') or previous['narrativeRole'] in ('reaction','payoff')
            if simultaneous and not (item['keepContinuousAction']^previous['keepContinuousAction']):
                previous['end']=max(previous['end'],item['end']);previous['eventIds']+=item['eventIds'];previous['mustShowTrackIds']=_unique(previous['mustShowTrackIds']+item['mustShowTrackIds']);previous['optionalTrackIds']=_unique(previous['optionalTrackIds']+item['optionalTrackIds']);previous['importance']=max(previous['importance'],item['importance']);previous['summary']=previous['summary']+' / '+item['summary'];previous['narrativeRole']='reaction' if 'reaction' in (previous['narrativeRole'],item['narrativeRole']) else previous['narrativeRole'];continue
            previous['end']=max(previous['start']+.25,item['start'])
        moments.append(item)
    return [moment for moment in moments if moment['end']-moment['start']>=.2]

def _subject_stats(moment,perception):
    wanted=set(moment['mustShowTrackIds']);records=defaultdict(lambda:{'centers':[],'boxes':[],'classes':[],'speeds':[],'visibility':0})
    frames=[frame for frame in perception.get('frames',[]) if moment['start']<=frame.get('time',-1)<moment['end']]
    for frame in frames:
        for detection in frame.get('detections',[]):
            track=str(detection['trackId'])
            if track not in wanted:continue
            record=records[track];record['centers'].append(center(detection['box']));record['boxes'].append(detection['box']);record['classes'].append(detection.get('class','object'));record['speeds'].append(math.hypot(*detection.get('worldVelocity',detection.get('velocity',[0,0]))));record['visibility']+=1
    result={}
    for track in moment['mustShowTrackIds']:
        record=records.get(track)
        if not record or not record['centers']:continue
        result[track]={'trackId':track,'class':max(set(record['classes']),key=record['classes'].count),'center':[median([point[0] for point in record['centers']]),median([point[1] for point in record['centers']])],'box':[median([box[index] for box in record['boxes']]) for index in range(4)],'meanSpeed':sum(record['speeds'])/max(1,len(record['speeds'])),'visibility':record['visibility']/max(1,len(frames))}
    return result

def _partition(track_ids,stats,count):
    ordered=sorted(track_ids,key=lambda track:stats.get(track,{'center':[.5,.5]})['center'][0]);count=max(1,min(count,len(ordered)));groups=[]
    for index in range(count):
        start=round(index*len(ordered)/count);end=round((index+1)*len(ordered)/count);groups.append(ordered[start:end])
    return [group for group in groups if group]

def _cell_geometry(layout,index,total):
    if layout in ('single_focus','shared_wide','action_pan','action_wide'):return [0,0,1,1]
    if layout in ('split_2_stack','bands_2x3'):return [0,index*.5,1,.5]
    if layout=='grid_4':return [(index%2)*.5,(index//2)*.5,.5,.5]
    if layout=='grid_6':return [(index%3)/3,(index//3)*.5,1/3,.5]
    return [0,0,1,1]

def _viewport(group,stats,cell,source_width,source_height):
    rows=[stats[track] for track in group if track in stats]
    if not rows:return {'centerX':.5,'centerY':.5,'cropWidth':1,'cropHeight':1,'confidence':0}
    boxes=[body_safe_box(row) for row in rows];x1=min(box[0] for box in boxes);y1=min(box[1] for box in boxes);x2=max(box[2] for box in boxes);y2=max(box[3] for box in boxes)
    output_aspect=(cell[2]/cell[3])*(9/16);source_norm_aspect=output_aspect*(source_height/source_width);crop_w,crop_h=aspect_safe_crop(x2-x1,y2-y1,source_norm_aspect,.28);cx=clamp((x1+x2)/2,crop_w/2,1-crop_w/2);cy=clamp((y1+y2)/2,crop_h/2,1-crop_h/2)
    return {'centerX':round(cx,5),'centerY':round(cy,5),'cropWidth':round(crop_w,5),'cropHeight':round(crop_h,5),'confidence':round(sum(row['visibility'] for row in rows)/len(rows),3)}

def _make_candidate(moment,stats,layout,groups,base_score,reason,source_width,source_height):
    cells=[];assigned=[]
    for index,group in enumerate(groups):
        geometry=_cell_geometry(layout,index,len(groups));assigned+=group;cells.append({'id':f'cell{index}','outputRect':geometry,'trackIds':group,'sourcePolicy':'trajectory_follow' if layout=='action_pan' else ('cluster_hold' if len(group)>1 else 'subject_lock'),'viewportHint':_viewport(group,stats,geometry,source_width,source_height),'priority':'primary' if index==0 else 'supporting'})
    required=moment['mustShowTrackIds'];coverage=len(set(assigned)&set(required))/max(1,len(required));readability=sum(cell['outputRect'][2]*cell['outputRect'][3]/max(1,len(cell['trackIds'])) for cell in cells)/max(1,len(cells));utilities=[cell_utility(group,stats,cell['outputRect'],source_width,source_height) for group,cell in zip(groups,cells)];safe_cells=all(item['safe'] for item in utilities);duplicate_cells=len({tuple(sorted(group)) for group in groups})==len(groups);score=base_score*.58+coverage*.24+min(1,readability*2)*.06+(sum(item['score'] for item in utilities)/max(1,len(utilities)))*.12
    return {'id':f"{moment['id']}:{layout}",'layoutType':layout,'cells':cells,'coverage':round(coverage,3),'baseScore':round(score,4),'reason':reason,'cameraPolicy':'continuous_predictive_pan' if layout=='action_pan' else ('locked_wide' if layout in ('shared_wide','action_wide') else ('multi_region_hold' if len(cells)>1 else 'locked_subject')),'cellUtility':utilities,'hardConstraints':{'allMustShowAssigned':coverage>=.999,'preserveContinuousAction':moment['keepContinuousAction'],'allCellsMeaningful':safe_cells and duplicate_cells,'aspectSafe':True},'stage3Ready':True}

def candidates_for_moment(moment,perception):
    stats=_subject_stats(moment,perception);tracks=[track for track in moment['mustShowTrackIds'] if track in stats];width=perception.get('width',1920);height=perception.get('height',1080)
    if not tracks:tracks=moment['mustShowTrackIds'][:]
    geometry=moment_geometry(moment,stats,width,height);spread=geometry['spatialSpread'];count=len(tracks);candidates=[]
    def add(layout,groups,score,reason):
        intent=moment.get('directingHint',{}).get('spatialIntent');bonus=0
        if intent=='single_subject' and layout=='single_focus':bonus=.07
        elif intent=='shared_region' and layout=='shared_wide':bonus=.07
        elif intent=='two_independent_regions' and layout=='split_2_stack':bonus=.07
        elif intent=='continuous_action' and layout in ('action_pan','action_wide'):bonus=.07
        candidates.append(_make_candidate(moment,stats,layout,groups,min(1,score+bonus),reason,width,height))
    if moment['keepContinuousAction'] or moment.get('detectedPhysicalAction'):
        if geometry['singleFrameFeasible']:add('action_wide',[tracks],.99,'One body-safe crop contains actor, moving object, target and outcome without a split')
        add('action_pan',[tracks],.97 if not geometry['singleFrameFeasible'] else .91,'Follow one causal physical action without cutting or splitting the canvas')
        if not geometry['singleFrameFeasible']:add('action_wide',[tracks],.62,'Conservative action context fallback when predictive motion confidence is weak')
        return candidates
    if count<=1:
        add('single_focus',[tracks],.98,'One narratively dominant subject')
        add('shared_wide',[tracks],.72,'Conservative context fallback')
    else:
        feasible=geometry['singleFrameFeasible']
        add('shared_wide',[tracks],.99 if feasible else .58,'One natural body-safe frame contains the complete story' if feasible else 'Conservative unsplit fallback')
        split_groups=_partition(tracks,stats,2);split_cells=[_cell_geometry('split_2_stack',index,len(split_groups)) for index in range(len(split_groups))];split_ok,split_reason,_=allow_split(moment,geometry,split_groups,stats,width,height,split_cells)
        if split_ok:add('split_2_stack',split_groups,.82 if count<=3 else .70,split_reason)
        if 3<=count<=4:
            grid_groups=[[track] for track in tracks];grid_cells=[_cell_geometry('grid_4',index,len(grid_groups)) for index in range(len(grid_groups))];grid_ok,grid_reason,_=allow_split(moment,geometry,grid_groups,stats,width,height,grid_cells)
            if grid_ok:add('grid_4',grid_groups,.96,grid_reason)
        if 5<=count<=6:
            band_groups=_partition(tracks,stats,2);band_cells=[_cell_geometry('bands_2x3',index,len(band_groups)) for index in range(len(band_groups))];band_ok,band_reason,_=allow_split(moment,geometry,band_groups,stats,width,height,band_cells)
            if band_ok:add('bands_2x3',band_groups,.86,band_reason)
            grid_groups=[[track] for track in tracks];grid_cells=[_cell_geometry('grid_6',index,len(grid_groups)) for index in range(len(grid_groups))];grid_ok,grid_reason,_=allow_split(moment,geometry,grid_groups,stats,width,height,grid_cells)
            if grid_ok:add('grid_6',grid_groups,.69,grid_reason)
        if count>6:add('bands_2x3',_partition(tracks[:6],stats,2),.72,'Prioritize the six highest-value visible subjects')
    return candidates

def _director_prompt(moments,candidates):
    package=[]
    for moment,options in zip(moments,candidates):
        package.append({'moment':{key:moment[key] for key in ('id','start','end','eventIds','type','narrativeRole','summary','mustShowTrackIds','importance','keepContinuousAction','coverageRequirements','directingHint')},'candidates':[{'id':option['id'],'layoutType':option['layoutType'],'cells':[cell['trackIds'] for cell in option['cells']],'coverage':option['coverage'],'baseScore':option['baseScore'],'reason':option['reason']} for option in options]})
    return f'''You are Stage 2 of an AI video director. Stage 1 already established factual story events. Select exactly one supplied candidate ID for each moment. Do not invent layouts, tracks, events, or timestamps.
Rules: geometry and body safety have already removed unsafe candidates. Always prefer a single/shared/action-wide frame when it communicates the complete causal action. Use split or grid only for simultaneous narratively connected regions that cannot remain readable in one crop and where every cell adds unique information. Never split a throw, toss, roll, cube, die, kick, shot, moving ball, save, score, catch, or other physical action. Avoid rapid switching. Your choice is advisory and cannot override local safety.
Return JSON only: {{"selections":[{{"momentId":"m0","candidateId":"m0:layout","confidence":0.0,"reason":"..."}}]}}.
PACKAGE:{json.dumps(package,separators=(',',':'))[:150000]}'''

def _api_recommend(moments,candidates,provider,model,key,base):
    if not (provider and model and key):return {}
    prompt=_director_prompt(moments,candidates)
    response=_gemini_generate(model,key,prompt) if provider=='gemini' else _chat_generate(provider,model,key,base,prompt)
    return {str(item.get('momentId')):item for item in response.get('selections',[]) if item.get('momentId')}

def _transition_penalty(previous,current,previous_moment,current_moment):
    if previous['layoutType']==current['layoutType']:
        old=[cell['trackIds'] for cell in previous['cells']];new=[cell['trackIds'] for cell in current['cells']];return .015 if old==new else .055
    if previous_moment['keepContinuousAction'] and current_moment['start']<=previous_moment['end']+.25:return .8
    if current_moment['keepContinuousAction']:return .04
    complex_change=previous['layoutType'] in ('grid_4','grid_6','bands_2x3') or current['layoutType'] in ('grid_4','grid_6','bands_2x3')
    return .17 if complex_change else .1

def _optimize(moments,all_candidates,recommendations):
    layers=[]
    for index,(moment,candidates) in enumerate(zip(moments,all_candidates)):
        layer=[]
        for candidate in candidates:
            if not candidate['hardConstraints']['allMustShowAssigned'] or not candidate['hardConstraints'].get('allCellsMeaningful',True):continue
            if moment['keepContinuousAction'] and candidate['layoutType'] not in ('action_pan','action_wide'):continue
            recommendation=recommendations.get(moment['id'],{});api_bonus=.04*float(recommendation.get('confidence',0) or 0) if recommendation.get('candidateId')==candidate['id'] else 0
            own=candidate['baseScore']+api_bonus
            if index==0:layer.append({'score':own,'candidate':candidate,'previous':None});continue
            best=None
            for previous_index,previous in enumerate(layers[-1]):
                score=previous['score']+own-_transition_penalty(previous['candidate'],candidate,moments[index-1],moment)
                if best is None or score>best['score']:best={'score':score,'candidate':candidate,'previous':previous_index}
            if best:layer.append(best)
        if not layer:
            fallback=max(candidates,key=lambda option:option['coverage']);layer=[{'score':fallback['baseScore'],'candidate':fallback,'previous':None}]
        layers.append(layer)
    if not layers:return []
    index=max(range(len(layers[-1])),key=lambda item:layers[-1][item]['score']);chosen=[]
    for layer in reversed(layers):
        node=layer[index];chosen.append(node['candidate']);index=node['previous'] if node['previous'] is not None else 0
    return list(reversed(chosen))

def validate_composition(plan):
    errors=[]
    for segment in plan.get('segments',[]):
        required=set(segment.get('mustShowTrackIds',[]));assigned={track for cell in segment.get('layout',{}).get('cells',[]) for track in cell.get('trackIds',[])}
        if not required<=assigned:errors.append({'segmentId':segment['id'],'code':'MISSING_REQUIRED_SUBJECTS','missing':sorted(required-assigned)})
        if segment.get('keepContinuousAction') and segment.get('layout',{}).get('layoutType') not in ('action_pan','action_wide'):errors.append({'segmentId':segment['id'],'code':'ACTION_CONTINUITY_BROKEN'})
    return errors

def composition_to_semantic(plan,scenes):
    result={}
    for scene in scenes:
        beats=[]
        for segment in plan.get('segments',[]):
            if segment['end']<=scene['start'] or segment['start']>=scene['end']:continue
            layout=segment['layout']['layoutType'];mode='action' if layout.startswith('action_') else ('group' if len(segment['mustShowTrackIds'])>=3 else ('pair' if len(segment['mustShowTrackIds'])==2 else 'single'))
            beats.append({'start':max(scene['start'],segment['start']),'end':min(scene['end'],segment['end']),'eventType':segment['narrativeRole'],'compositionMode':mode,'primaryTrackId':segment['mustShowTrackIds'][0] if segment['mustShowTrackIds'] else None,'requiredTrackIds':segment['mustShowTrackIds'],'cameraPolicy':'action_follow' if layout=='action_pan' else ('wide_static' if mode in ('group','pair') else 'locked'),'confidence':segment['confidence'],'reason':f"Stage 2 selected {layout}: {segment['reason']}"})
        result[str(scene['id'])]={'storyBeats':beats,'confidence':round(sum(item['confidence'] for item in beats)/max(1,len(beats)),3)}
    return result

def build_composition_plan(graph,perception,out_path,provider=None,model=None,api_key=None,base_url=None,progress=None):
    progress=progress or (lambda *_:None);moments=[prepare_moment(moment,perception) for moment in _moments(graph)];progress('Stage 2 · universal action and framing feasibility',60);all_candidates=[candidates_for_moment(moment,perception) for moment in moments];recommendations={}
    if provider and model and api_key:
        try:progress('Stage 2 · API composition director',63);recommendations=_api_recommend(moments,all_candidates,provider,model,api_key,base_url)
        except Exception as exc:recommendations={'_error':{'reason':str(exc)}}
    progress('Stage 2 · continuity and feasibility optimization',66);chosen=_optimize(moments,all_candidates,recommendations);segments=[]
    for index,(moment,layout) in enumerate(zip(moments,chosen)):
        recommendation=recommendations.get(moment['id'],{});same_previous=index>0 and chosen[index-1]['layoutType']==layout['layoutType'];transition='hold' if same_previous else ('action_continuity' if layout['layoutType']=='action_pan' else 'hard_cut')
        segments.append({'id':f'composition-{index}','start':round(moment['start'],3),'end':round(moment['end'],3),'eventIds':moment['eventIds'],'narrativeRole':moment['narrativeRole'],'summary':moment['summary'],'mustShowTrackIds':moment['mustShowTrackIds'],'optionalTrackIds':moment['optionalTrackIds'],'importance':round(moment['importance'],3),'confidence':round(max(moment['confidence'],float(recommendation.get('confidence',0) or 0)),3),'keepContinuousAction':moment['keepContinuousAction'],'detectedPhysicalAction':bool(moment.get('detectedPhysicalAction')),'framingEvidence':moment.get('framingEvidence',{}),'coordinateDirectingHint':moment.get('directingHint',{}),'anticipationSeconds':moment['anticipationSeconds'],'layout':layout,'transitionIn':transition,'reason':recommendation.get('reason') if recommendation.get('candidateId')==layout['id'] else layout['reason'],'alternatives':[{'id':candidate['id'],'layoutType':candidate['layoutType'],'score':candidate['baseScore']} for candidate in all_candidates[index] if candidate['id']!=layout['id']]})
    plan={'schemaVersion':SCHEMA_VERSION,'stage':'stage-2-composition-director','segments':segments,'validation':{},'stage3Contract':{'layoutTypes':sorted(LAYOUTS),'requiresMultiViewportRenderer':True,'legacyPreviewAdapter':True,'rendererImplemented':False},'researchPolicy':{'preferNaturalSharedFrame':True,'splitOnlyForNarrativeSimultaneity':True,'groupLaughterPreservesReactors':True,'continuousActionNeverGridSplit':True,'singleFrameFirst':True,'bodySafeCellsRequired':True,'apiGeometryAuthority':False,'borderlessRenderer':True,'penaltyCoverage':'anticipate actor; preserve ball/target/outcome; pan only inside continuous action'},'apiDirector':{'used':bool(recommendations and '_error' not in recommendations),'error':recommendations.get('_error')}}
    plan['validation']={'errors':validate_composition(plan),'valid':not validate_composition(plan)};dump(out_path,plan);return plan
