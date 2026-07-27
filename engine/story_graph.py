from __future__ import annotations
import json,math,mimetypes,os,re,time
from collections import Counter,defaultdict
from pathlib import Path
from statistics import median
from typing import Any,Callable
import requests
from .common import area,center,clamp,dump
from .framing_intelligence import body_safe_box

SCHEMA_VERSION='1.1'
WINDOW_SECONDS=12.0
REACTION_WORDS=re.compile(r'\b(laugh|laughing|laughter|haha+|hehe+|lol|giggle|chuckle|funny|joke)\b',re.I)
ACTION_WORDS=re.compile(r'\b(roll|rolled|throw|toss|shoot|shot|kick|hit|miss|score|goal|dice|die|cube|ball)\w*\b',re.I)
ALLOWED_RELATIONS={'causes','reacts_to','answers','continues','simultaneous_with','reveals','resolves','contrasts_with','motivates'}

def _strip_label(value,valid):
    value=str(value)
    if len(value)>1 and value[0].upper() in ('P','O') and value[1:] in valid:return value[1:]
    return value

def _frame_tracks(frame):return {str(row['trackId']):row for row in frame.get('detections',[])}

def _zone(value,axis='x'):
    if value<.333:return 'left' if axis=='x' else 'top'
    if value>.667:return 'right' if axis=='x' else 'bottom'
    return 'center' if axis=='x' else 'middle'

def _direction(first,last):
    dx,dy=last[0]-first[0],last[1]-first[1]
    if math.hypot(dx,dy)<.025:return 'stationary'
    horizontal='right' if dx>.02 else ('left' if dx<-.02 else '')
    vertical='down' if dy>.02 else ('up' if dy<-.02 else '')
    return '-'.join(part for part in (vertical,horizontal) if part) or 'small-motion'

def _interval_samples(rows,limit=12):
    if len(rows)<=limit:return rows
    return [rows[round(index*(len(rows)-1)/(limit-1))] for index in range(limit)]

def _coordinate_dossier(frames,summaries,source_width,source_height,start,end):
    by_track=defaultdict(list);timeline=[]
    for frame in frames:
        sample={'time':round(float(frame.get('time',0)),3),'subjects':[]}
        for row in frame.get('detections',[]):
            track=str(row.get('trackId'));box=[round(float(v),4) for v in row.get('box',[0,0,1,1])];cx,cy=center(box);vx,vy=row.get('worldVelocity',row.get('velocity',[0,0]));safe=body_safe_box(row)
            entry={'trackId':track,'class':str(row.get('class','object')).lower(),'box':box,'bodySafeBox':[round(v,4) for v in safe],'center':[round(cx,4),round(cy,4)],'screenZone':f"{_zone(cy,'y')}-{_zone(cx)}",'velocity':[round(float(vx),5),round(float(vy),5)],'confidence':round(float(row.get('confidence',0)),3),'touchesSourceEdge':bool(box[0]<=.015 or box[1]<=.015 or box[2]>=.985 or box[3]>=.985)}
            sample['subjects'].append(entry);by_track[track].append((float(frame.get('time',0)),entry))
        timeline.append(sample)
    tracks=[]
    for summary in summaries:
        track=str(summary['trackId']);rows=by_track.get(track,[]);centers=[row[1]['center'] for row in rows];boxes=[row[1]['box'] for row in rows]
        if not rows:continue
        xs=[point[0] for point in centers];ys=[point[1] for point in centers];areas=[max(0,b[2]-b[0])*max(0,b[3]-b[1]) for b in boxes]
        tracks.append({'trackId':track,'class':summary['class'],'firstSeen':round(rows[0][0],3),'lastSeen':round(rows[-1][0],3),'startCenter':centers[0],'endCenter':centers[-1],'meanCenter':summary['meanCenter'],'medianBox':summary['medianBox'],'xRange':[round(min(xs),3),round(max(xs),3)],'yRange':[round(min(ys),3),round(max(ys),3)],'meanArea':round(sum(areas)/max(1,len(areas)),4),'screenZone':f"{_zone(summary['meanCenter'][1],'y')}-{_zone(summary['meanCenter'][0])}",'motionDirection':_direction(centers[0],centers[-1]),'displacement':round(math.dist(centers[0],centers[-1]),4),'visibility':summary['visibility'],'meanSpeed':summary['meanSpeed'],'edgeRisk':round(sum(row[1]['touchesSourceEdge'] for row in rows)/max(1,len(rows)),3)})
    relations=[];ids=[row['trackId'] for row in tracks if row['class']=='person']
    for index,left in enumerate(ids):
        left_rows={round(t,3):entry for t,entry in by_track[left]}
        for right in ids[index+1:]:
            right_rows={round(t,3):entry for t,entry in by_track[right]};times=sorted(set(left_rows)&set(right_rows))
            if not times:continue
            distances=[];orders=[];union_widths=[];vertical_overlaps=[]
            for t in times:
                a,b=left_rows[t],right_rows[t];distances.append(math.dist(a['center'],b['center']));orders.append('leftOf' if a['center'][0]<b['center'][0] else 'rightOf');union_widths.append(max(a['bodySafeBox'][2],b['bodySafeBox'][2])-min(a['bodySafeBox'][0],b['bodySafeBox'][0]));vertical_overlaps.append(max(0,min(a['box'][3],b['box'][3])-max(a['box'][1],b['box'][1])))
            distance=sum(distances)/len(distances);union=sum(union_widths)/len(union_widths)
            relations.append({'trackA':left,'trackB':right,'coVisibleRate':round(len(times)/max(1,len(frames)),3),'meanCenterDistance':round(distance,3),'horizontalRelation':Counter(orders).most_common(1)[0][0],'meanUnionWidth':round(union,3),'meanVerticalOverlap':round(sum(vertical_overlaps)/len(vertical_overlaps),3),'sameNaturalRegion':bool(distance<.24),'singleVerticalCropLikely':bool(union<.30)})
    normalized_aspect=round((9/16)*(source_height/max(1,source_width)),5)
    return {'coordinateSystem':{'origin':'top-left','units':'normalized 0..1','xDirection':'right','yDirection':'down','sourceWidth':source_width,'sourceHeight':source_height,'targetAspect':'9:16','normalizedVerticalCropWidthAtFullHeight':normalized_aspect},'window':[round(start,3),round(end,3)],'tracks':tracks,'pairwiseRelations':relations,'timeline':_interval_samples(timeline,12),'interpretationRules':{'box':'[left,top,right,bottom]','center':'[x,y]','bodySafeBox':'box expanded by safety margin','positionIsEvidenceNotNarrativeImportance':True,'coVisibilityRequiredForSplit':True,'distantSubjectsMayNeedIndependentViews':True,'nearbySubjectsShouldShareOneNaturalFrame':True}}

def _provider_capabilities(provider,model):
    override=os.getenv('CLIPPERX_MODEL_INPUT','auto').strip().lower();provider=str(provider or '').lower();name=str(model or '').lower()
    if override in ('text','image','video'):return {'mode':override,'text':True,'image':override in ('image','video'),'video':override=='video','source':'environment override'}
    if provider=='gemini':return {'mode':'video','text':True,'image':True,'video':True,'source':'Gemini native file adapter'}
    image_hint=any(token in name for token in ('vision','-vl','visual','gpt-4o','claude-3'))
    return {'mode':'image' if image_hint else 'text','text':True,'image':image_hint,'video':False,'source':'safe automatic capability inference'}

def _window_evidence(start,end,perception,audio,active,social=None,actions=None):
    frames=[frame for frame in perception.get('frames',[]) if start<=frame.get('time',-1)<end]
    words=[word for word in audio.get('words',[]) if start<=word.get('start',-1)<end]
    speaker_rows=[row for row in active.get('frames',[]) if start<=row.get('time',-1)<end and row.get('personTrackId')]
    tracks=defaultdict(lambda:{'classes':Counter(),'centers':[],'boxes':[],'mouth':[],'speed':[],'visibleFrames':0})
    simultaneous_expression=[]
    for frame in frames:
        faces={str(face.get('personTrackId')):face for face in frame.get('faces',[]) if face.get('personTrackId')}
        expressive=[]
        for detection in frame.get('detections',[]):
            track=str(detection['trackId']);record=tracks[track];record['classes'][detection.get('class','object')]+=1;record['centers'].append(center(detection['box']));record['boxes'].append(detection['box']);record['speed'].append(math.hypot(*detection.get('worldVelocity',detection.get('velocity',[0,0]))));record['visibleFrames']+=1
            if track in faces:
                motion=float(faces[track].get('mouthMotion',0));record['mouth'].append(motion)
                if motion>=.018:expressive.append(track)
        if len(expressive)>=2:simultaneous_expression.append({'time':frame['time'],'tracks':expressive})
    summaries=[]
    for track,record in tracks.items():
        centers=record['centers'];boxes=record['boxes'];klass=record['classes'].most_common(1)[0][0]
        summaries.append({'trackId':track,'class':klass,'meanCenter':[round(sum(point[0] for point in centers)/len(centers),3),round(sum(point[1] for point in centers)/len(centers),3)],'medianBox':[round(median([box[index] for box in boxes]),3) for index in range(4)],'visibility':round(record['visibleFrames']/max(1,len(frames)),3),'meanSpeed':round(sum(record['speed'])/max(1,len(record['speed'])),3),'meanMouthMotion':round(sum(record['mouth'])/max(1,len(record['mouth'])),4),'maxMouthMotion':round(max(record['mouth'] or [0]),4)})
    transcript=' '.join(word.get('text','') for word in words).strip()
    speakers=Counter(str(row['personTrackId']) for row in speaker_rows)
    person_centers=sorted(item['meanCenter'][0] for item in summaries if item['class']=='person')
    spread=person_centers[-1]-person_centers[0] if len(person_centers)>1 else 0
    social=social or {};social_utterances=[row for row in social.get('utterances',[]) if row.get('end',0)>start and row.get('start',0)<end];social_reactions=[row for row in social.get('reactions',[]) if row.get('end',0)>start and row.get('start',0)<end];social_chains=[row for row in social.get('jokeChains',[]) if row.get('end',0)>start and row.get('start',0)<end];social_edges=[row for row in social.get('conversationEdges',[]) if row.get('from') in {item.get('id') for item in social_utterances} or row.get('to') in {item.get('id') for item in social_utterances}];actions=actions or {};action_episodes=[row for row in actions.get('episodes',[]) if row.get('end',0)>start and row.get('start',0)<end]
    return {'start':round(start,3),'end':round(end,3),'transcript':transcript,'wordTimes':[{'start':w.get('start'),'end':w.get('end'),'text':w.get('text')} for w in words],'tracks':summaries,'activeSpeakerVotes':dict(speakers),'simultaneousExpression':simultaneous_expression[::max(1,len(simultaneous_expression)//12)],'signals':{'laughterLanguage':bool(REACTION_WORDS.search(transcript)),'actionLanguage':bool(ACTION_WORDS.search(transcript)),'simultaneousExpressivePeople':max([len(row['tracks']) for row in simultaneous_expression] or [0]),'personHorizontalSpread':round(spread,3),'interactionEdges':sum(len(frame.get('interactions',[])) for frame in frames),'cameraMotionRms':round(math.sqrt(sum(frame.get('cameraMotion',{}).get('dx',0)**2+frame.get('cameraMotion',{}).get('dy',0)**2 for frame in frames)/max(1,len(frames))),5),'identityStitched':bool(perception.get('tracking',{}).get('identityStitching')),'socialGroupReactions':sum(bool(row.get('groupReaction')) for row in social_reactions),'interruptions':sum(row.get('type')=='interrupts' for row in social_edges),'jokePayoffs':len(social_chains),'actionEpisodes':len(action_episodes),'verifiedActionOutcomes':sum(bool(row.get('verification',{}).get('verified')) for row in action_episodes)},'social':{'utterances':social_utterances,'reactions':social_reactions,'conversationEdges':social_edges,'jokeChains':social_chains},'actionEpisodes':action_episodes,'coordinateDossier':_coordinate_dossier(frames,summaries,int(perception.get('width',1920) or 1920),int(perception.get('height',1080) or 1080),start,end)}

def build_evidence(perception,audio,active,scenes,duration,social=None,actions=None):
    windows=[]
    for scene in scenes:
        cursor=float(scene['start'])
        while cursor<scene['end']-.05:
            end=min(float(scene['end']),cursor+WINDOW_SECONDS);window=_window_evidence(cursor,end,perception,audio,active,social,actions);window['sceneId']=scene['id'];windows.append(window);cursor=end
    return {'duration':round(duration,3),'windows':windows,'transcript':audio.get('text',''),'sceneBoundaries':scenes}

def _local_events(evidence):
    events=[];index=0
    for window in evidence['windows']:
        signals=window['signals'];people=[item['trackId'] for item in window['tracks'] if item['class']=='person'];objects=[item['trackId'] for item in window['tracks'] if item['class']!='person'];speakers=sorted(window['activeSpeakerVotes'],key=window['activeSpeakerVotes'].get,reverse=True)
        event_type='dialogue' if window['transcript'] else 'context';role='setup';importance=.45
        must=speakers[:1] or people[:min(3,len(people))];summary=window['transcript'][:220] or 'Visual context'
        specialist=window.get('actionEpisodes',[None])[0] if window.get('actionEpisodes') else None
        if specialist:
            event_type='sports_action' if specialist.get('type')=='sports_shot' else 'object_action';role='action';importance=.92 if specialist.get('verification',{}).get('verified') else .8;must=specialist.get('mustShowTrackIds',[]);outcome=specialist.get('outcome',{});summary=f"{specialist.get('type','action')} with {outcome.get('status','unresolved')} outcome"
        elif signals['actionLanguage'] or any(item['class']=='sports ball' for item in window['tracks']):event_type='object_action';role='action';importance=.78;must=list(dict.fromkeys((speakers[:1] or people[:1])+objects[:2]+people[1:2]));summary='Tracked action involving people and an object'
        social_reactions=window.get('social',{}).get('reactions',[]);social_participants=list(dict.fromkeys(track for reaction in social_reactions for track in reaction.get('participants',[])))
        if not specialist and (signals['laughterLanguage'] or signals['simultaneousExpressivePeople']>=2 or signals.get('socialGroupReactions',0)>=1):event_type='group_reaction';role='reaction';importance=.86;must=social_participants or people;summary='Synchronized audio and visual evidence identifies a meaningful group reaction'
        elif not specialist and signals.get('jokePayoffs',0)>=1:event_type='joke';role='trigger';importance=.8;must=speakers[:1] or people[:1];summary='A conversational setup is causally linked to a later reaction payoff'
        event_actors=specialist.get('actorTrackIds',[]) if specialist else speakers[:1];event_reactors=specialist.get('reactorTrackIds',[]) if specialist else (people if event_type=='group_reaction' else []);event_objects=specialist.get('objectTrackIds',[]) if specialist else objects;continuous=event_type in ('object_action','sports_action')
        events.append({'id':f'e{index}','start':window['start'],'end':window['end'],'type':event_type,'narrativeRole':role,'summary':summary,'actors':event_actors,'reactors':event_reactors,'objects':event_objects,'mustShowTrackIds':must,'optionalTrackIds':[track for track in people if track not in must],'importance':importance,'confidence':specialist.get('outcome',{}).get('confidence',.52) if specialist else .52,'simultaneityGroupId':f's{index}' if event_type=='group_reaction' else None,'anticipationSeconds':.7 if continuous else 0,'keepContinuousAction':continuous,'evidence':{'windowStart':window['start'],'windowEnd':window['end'],'actionEpisodeId':specialist.get('id') if specialist else None}});index+=1
    return events

def _api_prompt(evidence):
    compact={'duration':evidence['duration'],'sceneBoundaries':evidence['sceneBoundaries'],'windows':evidence['windows']}
    return f'''You are Stage 1 of a professional AI video director. Your only job is STORY INTELLIGENCE: determine what happens, why it matters, who causes it, who reacts, what is simultaneous, and what must remain visible. Do not choose crops, grids, split-screen templates, camera pans, or rendering effects; later stages will do that.

Research-based editing principles:
- Build cause-and-effect chains: setup -> trigger/joke/action -> outcome -> reaction/payoff.
- A speaker is not automatically the most important subject. Reactions can be the payoff.
- When several people laugh or react to the same trigger, represent one simultaneous group-reaction event and include every narratively meaningful reactor.
- For a dice/cube/board-game action, preserve the actor, object/action area, result, and connected reactions.
- For a penalty or projectile action, anticipate the action, preserve continuous motion, and connect actor -> ball/object -> target/goalkeeper -> outcome.
- Standing by itself is usually background context unless it causes or changes the story.
- Coordinates are normalized to the source: origin top-left, x increases right, y increases down. Read boxes, body-safe boxes, trajectories, screen zones, pairwise distance, co-visibility, union width, and edge risk.
- Narrative importance comes from speech/action/reaction evidence; spatial feasibility comes from coordinates. Never confuse size or visibility with importance.
- Recommend independent regions only for simultaneously important, co-visible, spatially separated subjects. Nearby subjects should share one natural frame.
- A silent bystander must not become primary merely because that person is large or centered.
- Use track IDs exactly as provided. Display labels P17/O4 mean raw IDs "17"/"4".
- Anchor event boundaries to the supplied timestamps. Never invent people, objects, dialogue, or events.

Return strict JSON:
{{
 "globalSummary":"...",
 "entities":[{{"trackId":"raw id","type":"person|object","storyRole":"...","importance":0.0}}],
 "events":[{{"id":"e0","start":0.0,"end":1.0,"type":"dialogue|joke|object_action|sports_action|outcome|reaction|group_reaction|context","narrativeRole":"setup|trigger|action|outcome|reaction|payoff|context","summary":"factual","actors":[],"reactors":[],"objects":[],"targets":[],"mustShowTrackIds":[],"optionalTrackIds":[],"importance":0.0,"confidence":0.0,"simultaneityGroupId":null,"anticipationSeconds":0.0,"keepContinuousAction":false,"evidence":{{"visual":"...","audio":"...","transcript":"..."}}}}],
 "relations":[{{"from":"e0","to":"e1","type":"causes|reacts_to|answers|continues|simultaneous_with|reveals|resolves|contrasts_with|motivates","confidence":0.0}}],
 "storyArcs":[{{"id":"arc0","summary":"...","setupEventIds":[],"actionEventIds":[],"payoffEventIds":[],"importance":0.0}}],
 "directingHints":[{"eventId":"e0","primaryTrackIds":[],"supportingTrackIds":[],"excludeTrackIds":[],"preserveTogether":[],"spatialIntent":"single_subject|shared_region|two_independent_regions|continuous_action|full_source_only_if_no_evidence","holdReason":"...","coordinateReason":"cite numeric boxes/centers/distances/co-visibility"}],
 "uncertainties":["..."]
}}

Evidence package:
{json.dumps(compact,separators=(',',':'))[:180000]}'''

def _text_window_prompt(evidence,windows,batch_index,batch_count):
    compact=[]
    for row in windows:
        compact.append({'start':row.get('start'),'end':row.get('end'),'sceneId':row.get('sceneId'),'transcript':row.get('transcript',''),'activeSpeakerVotes':row.get('activeSpeakerVotes',{}),'signals':row.get('signals',{}),'tracks':row.get('tracks',[]),'actionEpisodes':row.get('actionEpisodes',[]),'coordinateDossier':row.get('coordinateDossier',{})})
    package={'duration':evidence['duration'],'batch':batch_index,'batchCount':batch_count,'windows':compact}
    return f'''You are the coordinate-grounded observation pass for a professional video director. You cannot see pixels, so the supplied geometry is your visual field. Analyze transcript, speakers, actions, trajectories, normalized boxes, bodySafeBox, screen zones, edge risk, pairwise distance, co-visibility, union width, and the sampled coordinate timeline together.
Rules: coordinates use top-left origin and 0..1 units. Never invent a track or position. Do not make a silent bystander primary. Distinguish temporal absence from clipping. Treat two regions as independent only when important people are co-visible and spatially separated. Preserve actor-object continuity through action/outcome.
Return strict JSON with globalSummary, entities, events, relations, directingHints, uncertainties. Each directingHint must use existing event/track IDs, select primary/supporting/excluded tracks, state spatialIntent, and cite concrete numeric coordinate facts in coordinateReason.
EVIDENCE:{json.dumps(package,separators=(',',':'))[:22000]}'''

def _compact_global_evidence(evidence):
    windows=[]
    for row in evidence.get('windows',[]):windows.append({'start':row['start'],'end':row['end'],'transcript':row.get('transcript',''),'activeSpeakerVotes':row.get('activeSpeakerVotes',{}),'signals':row.get('signals',{}),'tracks':row.get('tracks',[]),'coordinateDossier':row.get('coordinateDossier',{})})
    return {'duration':evidence.get('duration'),'sceneBoundaries':evidence.get('sceneBoundaries',[]),'windows':windows}

def _merge_story_drafts(drafts):
    result={'globalSummary':'','entities':[],'events':[],'relations':[],'storyArcs':[],'directingHints':[],'uncertainties':[]};seen_events=set();seen_entities=set()
    for draft in drafts:
        for entity in draft.get('entities',[]) or []:
            track=str(entity.get('trackId'))
            if track and track not in seen_entities:seen_entities.add(track);result['entities'].append(entity)
        id_map={}
        for event in draft.get('events',[]) or []:
            event=dict(event);base=str(event.get('id') or f'e{len(result["events"])}');event_id=base
            while event_id in seen_events:event_id=f'{base}-{len(seen_events)}'
            id_map[base]=event_id;event['id']=event_id;seen_events.add(event_id);result['events'].append(event)
        for relation in draft.get('relations',[]) or []:
            relation=dict(relation);relation['from']=id_map.get(str(relation.get('from')),relation.get('from'));relation['to']=id_map.get(str(relation.get('to')),relation.get('to'));result['relations'].append(relation)
        for hint in draft.get('directingHints',[]) or []:
            hint=dict(hint);hint['eventId']=id_map.get(str(hint.get('eventId')),hint.get('eventId'));result['directingHints'].append(hint)
        result['uncertainties'].extend(draft.get('uncertainties',[]) or [])
        if draft.get('globalSummary'):result['globalSummary']+=' '+str(draft['globalSummary'])
    result['globalSummary']=result['globalSummary'].strip();return result

def _text_grounded_story(provider,model,key,base,evidence,progress):
    windows=evidence.get('windows',[]);batches=[[window] for window in windows] or [[]];drafts=[];errors=[];batch_count=min(len(batches),30);attempted=0;consecutive_failures=0
    for index,batch in enumerate(batches[:30]):
        progress(f'Stage 1 text vision · coordinate batch {index+1}/{batch_count}',52+min(3,index//8));attempted+=1
        try:drafts.append(_chat_generate(provider,model,key,base,_text_window_prompt(evidence,batch,index+1,batch_count),timeout=75,attempts=1));consecutive_failures=0
        except Exception as exc:
            errors.append({'batch':index+1,'start':batch[0].get('start') if batch else None,'error':str(exc)[:300]});consecutive_failures+=1
            if consecutive_failures>=2 and not drafts:break
            if len(errors)>=5 and len(drafts)<2:break
    if not drafts:raise RuntimeError(f'All {attempted} attempted compact coordinate batches failed; first error: {errors[0]["error"] if errors else "unknown"}')
    merged=_merge_story_drafts(drafts);progress('Stage 1 text vision · global causal and spatial verification',56);global_evidence=_compact_global_evidence(evidence)
    prompt=f'''You are the global verification pass for a coordinate-grounded video story graph. Reconcile overlapping batch events, preserve chronology, connect setup/action/outcome/reaction, and return one strict JSON object with globalSummary, entities, events, relations, storyArcs, directingHints, uncertainties. Validate every directingHint against normalized coordinate evidence. Remove invented IDs, spatial claims without co-visibility, duplicate events, silent bystanders promoted without causal evidence, and splits whose regions are not independently meaningful. Keep coordinateReason concise and numeric.
EVIDENCE:{json.dumps(global_evidence,separators=(',',':'))[:45000]}
DRAFT:{json.dumps(merged,separators=(',',':'))[:45000]}'''
    try:result=_chat_generate(provider,model,key,base,prompt,timeout=120,attempts=2)
    except Exception:result=merged;result.setdefault('uncertainties',[]).append('Global API verification timed out; successful coordinate-window decisions were retained and locally validated.')
    result['_textBatchErrors']=errors;return result,{'planned':batch_count,'attempted':attempted,'succeeded':len(drafts),'failed':len(errors),'circuitBreakerStopped':attempted<batch_count,'errors':errors[:8]}

def _critic_prompt(evidence,draft):
    return f'''You are the verification pass for a video story graph. Correct the draft using only the evidence. Remove invented tracks/events, merge duplicated overlap-window events, restore missing simultaneous reactors, and make cause/reaction/outcome links explicit. Preserve continuous sports/object actions. Return the same strict JSON schema and nothing else.
EVIDENCE:{json.dumps(evidence,separators=(',',':'))[:120000]}
DRAFT:{json.dumps(draft,separators=(',',':'))[:100000]}'''

def _extract_json(text):
    text=(text or '').strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    try:return json.loads(text)
    except json.JSONDecodeError:
        start=text.find('{');end=text.rfind('}')
        if start>=0 and end>start:return json.loads(text[start:end+1])
        raise

def _request_json(url,body,headers,parser,timeout=180,attempts=3):
    error=None
    for attempt in range(attempts):
        try:
            response=requests.post(url,json=body,headers=headers,timeout=timeout)
            if response.status_code in (429,500,502,503,504):raise RuntimeError(f'Provider temporarily unavailable ({response.status_code})')
            response.raise_for_status();return _extract_json(parser(response.json()))
        except Exception as exc:
            error=exc
            if attempt==attempts-1:break
            time.sleep(1.5*(attempt+1))
    raise RuntimeError(f"Story API failed after {attempts} bounded {'attempt' if attempts==1 else 'attempts'}: {error}")

def _gemini_generate(model,key,prompt,file_info=None):
    parts=[{'text':prompt}]
    if file_info:parts.insert(0,{'file_data':{'mime_type':file_info['mime_type'],'file_uri':file_info['uri']}})
    url=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}'
    body={'contents':[{'parts':parts}],'generationConfig':{'responseMimeType':'application/json','temperature':.05}}
    return _request_json(url,body,{},lambda data:data['candidates'][0]['content']['parts'][0]['text'],300)

def _gemini_upload(video_path,key,progress):
    path=Path(video_path);mime=mimetypes.guess_type(path.name)[0] or 'video/mp4';size=path.stat().st_size
    progress('Uploading full video to the Stage 1 story brain',51)
    start=requests.post(f'https://generativelanguage.googleapis.com/upload/v1beta/files?key={key}',headers={'X-Goog-Upload-Protocol':'resumable','X-Goog-Upload-Command':'start','X-Goog-Upload-Header-Content-Length':str(size),'X-Goog-Upload-Header-Content-Type':mime,'Content-Type':'application/json'},json={'file':{'display_name':path.name}},timeout=45)
    start.raise_for_status();upload_url=start.headers.get('x-goog-upload-url')
    if not upload_url:raise RuntimeError('Gemini did not return an upload URL')
    with path.open('rb') as handle:
        uploaded=requests.post(upload_url,data=handle,headers={'Content-Length':str(size),'X-Goog-Upload-Offset':'0','X-Goog-Upload-Command':'upload, finalize'},timeout=900)
    uploaded.raise_for_status();file_info=uploaded.json().get('file',uploaded.json());name=file_info.get('name')
    deadline=time.time()+360
    while file_info.get('state','ACTIVE') not in ('ACTIVE','FAILED') and time.time()<deadline:
        time.sleep(3);poll=requests.get(f'https://generativelanguage.googleapis.com/v1beta/{name}?key={key}',timeout=30);poll.raise_for_status();file_info=poll.json()
    if file_info.get('state')!='ACTIVE':raise RuntimeError(f"Gemini video processing did not become ready: {file_info.get('state','timeout')}")
    return {'uri':file_info['uri'],'mime_type':file_info.get('mimeType',file_info.get('mime_type',mime))}

def _chat_generate(provider,model,key,base,prompt,timeout=240,attempts=3):
    if provider=='anthropic':
        url=(base or 'https://api.anthropic.com').rstrip('/')+'/v1/messages';headers={'x-api-key':key,'anthropic-version':'2023-06-01'};body={'model':model,'max_tokens':8192,'temperature':0,'messages':[{'role':'user','content':prompt}]};parser=lambda data:data['content'][0]['text']
    else:
        root=(base or ('https://openrouter.ai/api/v1' if provider=='openrouter' else 'https://api.openai.com/v1')).rstrip('/');url=root+'/chat/completions';headers={'Authorization':'Bearer '+key};body={'model':model,'temperature':0,'response_format':{'type':'json_object'},'messages':[{'role':'user','content':prompt}]};parser=lambda data:data['choices'][0]['message']['content']
    return _request_json(url,body,headers,parser,timeout,attempts)

def _spatial_requirements(event,perception):
    tracks=list(dict.fromkeys(event.get('mustShowTrackIds',[])));frames=[frame for frame in perception.get('frames',[]) if event['start']<=frame.get('time',-1)<event['end']]
    positions=defaultdict(list);classes={}
    for frame in frames:
        for track,detection in _frame_tracks(frame).items():
            if track in tracks:positions[track].append(center(detection['box']));classes[track]=detection.get('class')
    medians={track:[median([point[0] for point in points]),median([point[1] for point in points])] for track,points in positions.items() if points}
    ordered=sorted((point[0],track) for track,point in medians.items());clusters=[]
    for x,track in ordered:
        if not clusters or x-clusters[-1]['lastX']>.24:clusters.append({'trackIds':[track],'lastX':x})
        else:clusters[-1]['trackIds'].append(track);clusters[-1]['lastX']=x
    xs=[point[0] for point in medians.values()];spread=max(xs)-min(xs) if len(xs)>1 else 0
    people=[track for track in tracks if classes.get(track)=='person'];objects=[track for track in tracks if classes.get(track)!='person']
    return {'simultaneousSubjectCount':len(tracks),'personCount':len(people),'objectCount':len(objects),'horizontalSpread':round(spread,3),'importantRegionCount':len(clusters),'regions':[{'trackIds':cluster['trackIds']} for cluster in clusters],'singleVerticalCropFeasible':spread<=.30 and len(clusters)<=1,'requiresContinuousMotion':bool(event.get('keepContinuousAction')),'anticipationSeconds':float(event.get('anticipationSeconds',0) or 0),'evidenceCoverage':round(len(positions)/max(1,len(tracks)),3)}

def validate_story_graph(raw,evidence,perception,duration):
    raw=raw.get('storyGraph',raw) if isinstance(raw,dict) else {};valid_tracks={str(item['trackId']) for frame in perception.get('frames',[]) for item in frame.get('detections',[])};events=[];used=set()
    for index,item in enumerate(raw.get('events',[]) or []):
        try:start=clamp(float(item.get('start',0)),0,duration);end=clamp(float(item.get('end',start+.2)),start,duration)
        except Exception:continue
        if end-start<.12:continue
        event_id=str(item.get('id') or f'e{index}')
        if event_id in used:event_id=f'e{index}'
        used.add(event_id)
        def tracks(field):return list(dict.fromkeys(_strip_label(value,valid_tracks) for value in (item.get(field,[]) or []) if _strip_label(value,valid_tracks) in valid_tracks))
        event={'id':event_id,'start':round(start,3),'end':round(end,3),'type':str(item.get('type','context')),'narrativeRole':str(item.get('narrativeRole','context')),'summary':str(item.get('summary',''))[:500],'actors':tracks('actors'),'reactors':tracks('reactors'),'objects':tracks('objects'),'targets':tracks('targets'),'mustShowTrackIds':tracks('mustShowTrackIds'),'optionalTrackIds':tracks('optionalTrackIds'),'importance':round(clamp(float(item.get('importance',.5) or .5),0,1),3),'confidence':round(clamp(float(item.get('confidence',.5) or .5),0,1),3),'simultaneityGroupId':item.get('simultaneityGroupId'),'anticipationSeconds':round(clamp(float(item.get('anticipationSeconds',0) or 0),0,4),3),'keepContinuousAction':bool(item.get('keepContinuousAction',False)),'evidence':item.get('evidence',{})}
        if not event['mustShowTrackIds']:event['mustShowTrackIds']=list(dict.fromkeys(event['actors']+event['reactors']+event['objects']+event['targets']))
        event['coverageRequirements']=_spatial_requirements(event,perception);events.append(event)
    if not events:events=_local_events(evidence)
    events=sorted(events,key=lambda item:(item['start'],item['end']));event_ids={event['id'] for event in events};allowed_intents={'single_subject','shared_region','two_independent_regions','continuous_action','full_source_only_if_no_evidence'};hints=[]
    for row in raw.get('directingHints',[]) or []:
        event_id=str(row.get('eventId',''))
        if event_id not in event_ids:continue
        def hint_tracks(field):return list(dict.fromkeys(_strip_label(value,valid_tracks) for value in (row.get(field,[]) or []) if _strip_label(value,valid_tracks) in valid_tracks))
        intent=str(row.get('spatialIntent','shared_region'))
        if intent not in allowed_intents:intent='shared_region'
        hints.append({'eventId':event_id,'primaryTrackIds':hint_tracks('primaryTrackIds'),'supportingTrackIds':hint_tracks('supportingTrackIds'),'excludeTrackIds':hint_tracks('excludeTrackIds'),'preserveTogether':hint_tracks('preserveTogether'),'spatialIntent':intent,'holdReason':str(row.get('holdReason',''))[:400],'coordinateReason':str(row.get('coordinateReason',''))[:700]})
    hint_map={row['eventId']:row for row in hints}
    for event in events:
        hint=hint_map.get(event['id'])
        if not hint:continue
        excluded=set(hint['excludeTrackIds']);event['optionalTrackIds']=[track for track in event['optionalTrackIds'] if track not in excluded];event['mustShowTrackIds']=list(dict.fromkeys([track for track in hint['primaryTrackIds']+event['mustShowTrackIds'] if track not in excluded]));event['directingHint']=hint;event['coverageRequirements']=_spatial_requirements(event,perception)
    relations=[]
    for relation in raw.get('relations',[]) or []:
        source=str(relation.get('from',''));target=str(relation.get('to',''));kind=str(relation.get('type','continues'))
        if source in event_ids and target in event_ids and source!=target and kind in ALLOWED_RELATIONS:relations.append({'from':source,'to':target,'type':kind,'confidence':round(clamp(float(relation.get('confidence',.6) or .6),0,1),3)})
    existing={(row['from'],row['to'],row['type']) for row in relations}
    for index,event in enumerate(events):
        if event['narrativeRole'] in ('reaction','payoff') or event['type'] in ('reaction','group_reaction'):
            previous=next((candidate for candidate in reversed(events[:index]) if event['start']-candidate['end']<=5 and candidate['narrativeRole'] not in ('reaction','payoff')),None)
            if previous and (event['id'],previous['id'],'reacts_to') not in existing:relations.append({'from':event['id'],'to':previous['id'],'type':'reacts_to','confidence':.58})
    entities=[]
    supplied={str(entity.get('trackId')):entity for entity in raw.get('entities',[]) or [] if entity.get('trackId') is not None}
    for track in sorted(valid_tracks):
        source=supplied.get(track,{})
        classes=Counter(item.get('class','object') for frame in perception.get('frames',[]) for item in frame.get('detections',[]) if str(item['trackId'])==track)
        entities.append({'trackId':track,'type':'person' if classes and classes.most_common(1)[0][0]=='person' else 'object','storyRole':str(source.get('storyRole','participant')),'importance':round(clamp(float(source.get('importance',.5) or .5),0,1),3)})
    arcs=raw.get('storyArcs',[]) or _build_arcs(events,relations)
    timeline=[{'start':event['start'],'end':event['end'],'dominantEventIds':[event['id']],'storyFocusTrackIds':event['mustShowTrackIds'],'narrativeRole':event['narrativeRole'],'importance':event['importance']} for event in events]
    return {'schemaVersion':SCHEMA_VERSION,'stage':'stage-1-story-intelligence','globalSummary':str(raw.get('globalSummary','Story graph generated from local multimodal evidence')),'entities':entities,'events':events,'relations':relations,'storyArcs':arcs,'timeline':timeline,'directingHints':hints,'uncertainties':raw.get('uncertainties',[]),'provenance':{'apiDraft':bool(raw.get('events')),'evidenceWindows':len(evidence['windows']),'fullVideoAnalyzed':bool(raw.get('_fullVideoAnalyzed')),'renderDecisionsIncluded':False}}

def _build_arcs(events,relations):
    arcs=[];consumed=set()
    for event in events:
        if event['id'] in consumed:continue
        linked={event['id']};changed=True
        while changed:
            changed=False
            for relation in relations:
                if relation['from'] in linked or relation['to'] in linked:
                    before=len(linked);linked|={relation['from'],relation['to']};changed|=len(linked)>before
        members=[item for item in events if item['id'] in linked];consumed|=linked
        arcs.append({'id':f'arc{len(arcs)}','summary':' -> '.join(item['summary'][:80] for item in members[:4]),'setupEventIds':[item['id'] for item in members if item['narrativeRole'] in ('setup','trigger')],'actionEventIds':[item['id'] for item in members if item['narrativeRole']=='action'],'payoffEventIds':[item['id'] for item in members if item['narrativeRole'] in ('outcome','reaction','payoff')],'importance':round(max([item['importance'] for item in members] or [.5]),3)})
    return arcs

def graph_to_semantic(graph,scenes):
    result={}
    for scene in scenes:
        beats=[]
        for event in graph.get('events',[]):
            if event['end']<=scene['start'] or event['start']>=scene['end']:continue
            coverage=event.get('coverageRequirements',{});role=event.get('narrativeRole');event_type=event.get('type')
            mode='action' if event.get('keepContinuousAction') or role=='action' else ('group' if coverage.get('simultaneousSubjectCount',0)>=3 else ('pair' if coverage.get('simultaneousSubjectCount')==2 else 'single'))
            beats.append({'start':max(scene['start'],event['start']),'end':min(scene['end'],event['end']),'eventType':event_type,'compositionMode':mode,'primaryTrackId':(event.get('actors') or event.get('mustShowTrackIds') or [None])[0],'requiredTrackIds':event.get('mustShowTrackIds',[]),'cameraPolicy':'action_follow' if event.get('keepContinuousAction') else ('wide_static' if mode in ('group','pair') else 'locked'),'confidence':event.get('confidence',.5),'reason':event.get('summary','Stage 1 narrative event')})
        result[str(scene['id'])]={'storyBeats':beats,'confidence':round(sum(item['confidence'] for item in beats)/max(1,len(beats)),3)}
    return result

def build_story_graph(video_path,scenes,perception,audio,active,out_dir,provider=None,model=None,api_key=None,base_url=None,progress:Callable[[str,int],None]|None=None,social=None,actions=None):
    progress=progress or (lambda *_:None);duration=max([scene['end'] for scene in scenes] or [0]);evidence=build_evidence(perception,audio,active,scenes,duration,social,actions);out=Path(out_dir);dump(out/'story-evidence.json',evidence);dump(out/'story-coordinate-dossier.json',{'schemaVersion':SCHEMA_VERSION,'duration':evidence['duration'],'windows':[{'start':w['start'],'end':w['end'],'coordinateDossier':w.get('coordinateDossier',{})} for w in evidence['windows']]});draft={'events':_local_events(evidence)};capabilities=_provider_capabilities(provider,model);routing={'schemaVersion':SCHEMA_VERSION,'provider':provider or None,'model':model or None,'capabilities':capabilities,'adapter':'local','called':False,'used':False,'error':None,'textBatches':{'attempted':0,'succeeded':0,'failed':0}}
    if provider and model and api_key:
        try:
            routing['called']=True
            if capabilities['video'] and provider=='gemini':
                routing['adapter']='native_video_plus_coordinates';file_info=_gemini_upload(video_path,api_key,progress);progress('Stage 1 pass 1/2 · video and coordinate observation',53);draft=_gemini_generate(model,api_key,_api_prompt(evidence),file_info);draft['_fullVideoAnalyzed']=True;dump(out/'story-pass-1.json',draft);progress('Stage 1 pass 2/2 · causal graph verification',56);corrected=_gemini_generate(model,api_key,_critic_prompt(evidence,draft));corrected['_fullVideoAnalyzed']=True
            else:
                routing['adapter']='coordinate_text_dossier';corrected,batches=_text_grounded_story(provider,model,api_key,base_url,evidence,progress);routing['textBatches']=batches;draft=corrected;dump(out/'story-pass-1.json',draft);corrected['_fullVideoAnalyzed']=False
            dump(out/'story-pass-2.json',corrected);draft=corrected;routing['used']=True
        except Exception as exc:
            routing['error']=str(exc)[:1200];draft={'events':_local_events(evidence),'uncertainties':[f'API story analysis failed; local evidence graph used: {exc}']}
    dump(out/'story-model-routing.json',routing);graph=validate_story_graph(draft,evidence,perception,duration);graph['provenance']['modelAdapter']=routing['adapter'];graph['provenance']['modelUsed']=routing['used'];graph['provenance']['modelCapabilities']=capabilities;dump(out/'story-graph.json',graph);return graph
