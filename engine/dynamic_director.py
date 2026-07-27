from __future__ import annotations
import copy,math
from collections import defaultdict
from statistics import mean,median
from .common import clamp,dump

SCHEMA_VERSION='1.2'
ENTER_ADVANCED=.78
EXIT_ADVANCED=.61
MIN_POLICY_HOLD_SECONDS=1.35
MIN_DIALOGUE_SHOT_SECONDS=2.2
MIN_VISUAL_SHOT_SECONDS=2.6

def _overlap(row,start,end):return float(row.get('end',row.get('start',0)))>start and float(row.get('start',0))<end

def _frames(perception,start,end):return [row for row in perception.get('frames',[]) if start<=float(row.get('time',-1))<end]

def _memory(perception):
    history=defaultdict(list)
    for frame in perception.get('frames',[]):
        for row in frame.get('detections',[]):history[str(row['trackId'])].append((float(frame.get('time',0)),row))
    result={}
    for track,rows in history.items():
        rows.sort(key=lambda item:item[0]);classes=[str(row.get('class','object')) for _,row in rows];result[track]={'firstSeen':rows[0][0],'lastSeen':rows[-1][0],'observationCount':len(rows),'medianConfidence':median(float(row.get('confidence',.6)) for _,row in rows),'class':max(set(classes),key=classes.count),'rows':rows}
    return result

def _predict(memory,track,t,max_gap=.9):
    rows=memory.get(track,{}).get('rows',[]);before=[row for row in rows if row[0]<=t];after=[row for row in rows if row[0]>t];nearest=max(before,key=lambda row:row[0]) if before else (min(after,key=lambda row:row[0]) if after else None)
    if not nearest or abs(nearest[0]-t)>max_gap:return None
    item=copy.deepcopy(nearest[1]);vx,vy=item.get('worldVelocity',item.get('velocity',[0,0]));dt=t-nearest[0];box=item.get('box',[0,0,1,1]);item['box']=[clamp(box[0]+vx*dt,0,1),clamp(box[1]+vy*dt,0,1),clamp(box[2]+vx*dt,0,1),clamp(box[3]+vy*dt,0,1)];item['predicted']=True;item['predictionGap']=abs(dt);return item

def _track_observations(perception,memory,start,end,track_ids=None):
    frames=_frames(perception,start,end);seen=defaultdict(list)
    for frame in frames:
        for row in frame.get('detections',[]):seen[str(row['trackId'])].append(row)
    midpoint=(start+end)/2
    for track in track_ids or []:
        track=str(track)
        if track not in seen:
            predicted=_predict(memory,track,midpoint)
            if predicted:seen[track].append(predicted)
    result={}
    for track,rows in seen.items():
        predicted=sum(bool(row.get('predicted')) for row in rows);current=max(0,len(rows)-predicted);continuity=math.exp(-float(rows[-1].get('predictionGap',0))*1.8) if predicted and not current else 1;visibility=current/max(1,len(frames)) if current else (.45*continuity if predicted else 0);classes=[str(row.get('class','object')) for row in rows];motion=mean(math.hypot(*row.get('worldVelocity',row.get('velocity',[0,0]))) for row in rows);result[track]={'visibility':visibility,'confidence':mean(float(row.get('confidence',.65)) for row in rows)*continuity,'continuityConfidence':continuity,'predicted':bool(predicted and not current),'class':max(set(classes),key=classes.count),'box':rows[-1].get('box'),'motion':motion}
    return result

def _speaker_evidence(active,start,end):
    rows=[row for row in active.get('frames',[]) if start<=float(row.get('time',-1))<end and row.get('personTrackId')];scores=defaultdict(list)
    for row in rows:scores[str(row['personTrackId'])].append(float(row.get('confidence',0)))
    return {track:mean(values) for track,values in scores.items()}

def _phase(episode,t):
    for name,span in episode.get('phases',{}).items():
        if isinstance(span,list) and len(span)==2 and span[0]<=t<=span[1]:return name
    return 'action' if t<float(episode.get('end',t)) else 'outcome'

def _episode_roles(episode,phase):
    actor=[str(x) for x in episode.get('actorTrackIds',[])];objects=[str(x) for x in episode.get('objectTrackIds',[])];targets=[str(x) for x in episode.get('targetTrackIds',[])];reactors=[str(x) for x in episode.get('reactorTrackIds',[])]
    if phase in ('anticipation','setup'):return actor+objects
    if phase in ('action','travel','release'):return actor+objects+targets
    if phase in ('outcome','result'):return objects+targets
    if phase=='reaction':return targets+reactors
    return actor+objects+targets

def _independent_required(segment,speakers,episodes,reactions,t):
    proposed=[str(track) for track in segment.get('mustShowTrackIds',[])]
    evidenced=[]
    for track,confidence in speakers.items():
        if confidence>=.58:evidenced.append(track)
    phase_by_episode={row['id']:_phase(row,t) for row in episodes}
    for episode in episodes:evidenced.extend(_episode_roles(episode,phase_by_episode[episode['id']]))
    if any(phase=='reaction' for phase in phase_by_episode.values()):
        for reaction in reactions:evidenced.extend(str(track) for track in reaction.get('participants',[]))
    # Once independent speech/action/reaction evidence exists, it becomes the
    # authority.  Do not preserve an upstream person merely because the first
    # story proposal happened to include a visible silent bystander.
    required=evidenced if evidenced else proposed
    return list(dict.fromkeys(required)),phase_by_episode

def _importance(required,observations,speakers,episodes,reactions,phase_by_episode):
    scores=defaultdict(float);reasons=defaultdict(list)
    for track in required:scores[track]=max(scores[track],.52);reasons[track].append('required by fused evidence')
    for track,confidence in speakers.items():scores[track]=max(scores[track],.70+.25*confidence);reasons[track].append('audible active speaker')
    for episode in episodes:
        phase=phase_by_episode.get(episode['id'],'action')
        for track in episode.get('actorTrackIds',[]):scores[str(track)]=max(scores[str(track)],.94 if phase in ('anticipation','action','release') else .62);reasons[str(track)].append(f'action actor during {phase}')
        for track in episode.get('objectTrackIds',[]):scores[str(track)]=1;reasons[str(track)].append(f'moving object during {phase}')
        for track in episode.get('targetTrackIds',[]):scores[str(track)]=max(scores[str(track)],.98 if phase in ('travel','outcome','result') else .82);reasons[str(track)].append(f'action target during {phase}')
        if phase=='reaction':
            for track in episode.get('reactorTrackIds',[]):scores[str(track)]=max(scores[str(track)],.88);reasons[str(track)].append('outcome reactor')
    for reaction in reactions:
        for track in reaction.get('participants',[]):
            if str(track) in required:scores[str(track)]=max(scores[str(track)],.78);reasons[str(track)].append('verified social reaction')
    for track in list(scores):
        observation=observations.get(track)
        if not observation:scores[track]*=.28;reasons[track].append('missing visual evidence')
        elif observation.get('predicted'):scores[track]*=.72;reasons[track].append('short-term continuity prediction')
        else:scores[track]*=.74+.26*observation['visibility']
    return [{'trackId':track,'score':round(score,4),'reasons':reasons[track],'class':observations.get(track,{}).get('class'),'predicted':observations.get(track,{}).get('predicted',False)} for track,score in sorted(scores.items(),key=lambda item:item[1],reverse=True)]

def _conversation_context(active,memory):
    speech=defaultdict(float);turns=defaultdict(list)
    frames=active.get('frames',[])
    for row in frames:
        if row.get('personTrackId'):speech[str(row['personTrackId'])]+=float(row.get('confidence',0))
    for row in active.get('segments',[]):
        track=str(row.get('personTrackId'));turns[track].append(max(0,float(row.get('end',0))-float(row.get('start',0))))
    positions=[]
    for track,item in memory.items():
        if item.get('class')!='person':continue
        centers=[(row.get('box',[0,0,1,1])[0]+row.get('box',[0,0,1,1])[2])/2 for _,row in item.get('rows',[])];positions.append((median(centers) if centers else .5,track))
    positions.sort();clusters=[]
    for x,track in positions:
        if not clusters or x-clusters[-1]['lastX']>.20:clusters.append({'id':f'cluster-{len(clusters)}','tracks':[],'xs':[],'lastX':x})
        clusters[-1]['tracks'].append(track);clusters[-1]['xs'].append(x);clusters[-1]['lastX']=x
    track_to_cluster={track:cluster['id'] for cluster in clusters for track in cluster['tracks']};cluster_scores={cluster['id']:sum(speech.get(track,0) for track in cluster['tracks']) for cluster in clusters};dominant=max(cluster_scores,key=cluster_scores.get) if cluster_scores and max(cluster_scores.values())>0 else (clusters[0]['id'] if clusters else None);all_turns=[duration for values in turns.values() for duration in values]
    return {'clusters':[{**cluster,'centerX':round(mean(cluster['xs']),4)} for cluster in clusters],'trackToCluster':track_to_cluster,'clusterSpeech':cluster_scores,'dominantClusterId':dominant,'speechByTrack':dict(speech),'turnsByTrack':dict(turns),'medianTurnSeconds':median(all_turns) if all_turns else 99}

def _current_turn(active,start,end,speakers):
    track=max(speakers,key=speakers.get) if speakers else None;duration=0
    for row in active.get('segments',[]):
        if str(row.get('personTrackId'))==track and _overlap(row,start,end):duration=max(duration,float(row.get('end',0))-float(row.get('start',0)))
    return track,duration

def _cluster_tracks(context,cluster_id):
    return next((list(row['tracks']) for row in context.get('clusters',[]) if row['id']==cluster_id),[])

def _action_role_filter(required,observations,speakers,episodes):
    actors=list(dict.fromkeys(str(track) for episode in episodes for track in episode.get('actorTrackIds',[])));objects=list(dict.fromkeys(str(track) for episode in episodes for track in episode.get('objectTrackIds',[])))
    if len(actors)<2:return required
    object_boxes=[observations.get(track,{}).get('box') for track in objects if observations.get(track,{}).get('box')]
    def score(track):
        row=observations.get(track,{});box=row.get('box')
        if not box:return -99
        cx,cy=(box[0]+box[2])/2,(box[1]+box[3])/2;distance=min((math.hypot(cx-(obj[0]+obj[2])/2,cy-(obj[1]+obj[3])/2) for obj in object_boxes),default=1);return float(row.get('motion',0))*2+(1-distance)
    ranked=sorted(actors,key=score,reverse=True);best=score(ranked[0]);kept={ranked[0],*speakers.keys()}
    for track in ranked[1:]:
        if score(track)>=best-.10:kept.add(track)
    return [track for track in required if track not in actors or track in kept]

def _situation(segment,perception,memory,active,social,actions,conversation,index):
    start,end=float(segment['start']),float(segment['end']);t=(start+end)/2;speakers=_speaker_evidence(active,start,end);episodes=[row for row in actions.get('episodes',[]) if _overlap(row,start,end)];reactions=[row for row in social.get('reactions',[]) if _overlap(row,start,end)];required,phase_by_episode=_independent_required(segment,speakers,episodes,reactions,t);observations=_track_observations(perception,memory,start,end,required);required=_action_role_filter(required,observations,speakers,episodes);importance=_importance(required,observations,speakers,episodes,reactions,phase_by_episode);visibility=mean([observations.get(track,{}).get('visibility',0) for track in required]) if required else 1;continuity=mean([observations.get(track,{}).get('continuityConfidence',0) for track in required]) if required else 1;detection_conf=mean([observations.get(track,{}).get('confidence',0) for track in required]) if required else .8;speaker_conf=max(speakers.values() or [0]);action_values=[]
    for row in episodes:
        verified=bool(row.get('verification',{}).get('verified'));trajectory=.82 if row.get('objectTrackIds') else .5;outcome=float(row.get('outcome',{}).get('confidence',0));action_values.append(max(trajectory,.55+.4*outcome if verified else .55))
    action_conf=max(action_values or [0]);story_conf=float(segment.get('confidence',.5));physical=bool(episodes or segment.get('detectedPhysicalAction') or segment.get('keepContinuousAction'));mandatory_coverage=sum(int(bool(observations.get(track,{}).get('visibility',0)>=.2 or observations.get(track,{}).get('predicted',False))) for track in required)/max(1,len(required));confidence=.30*visibility+.20*detection_conf+.18*continuity+.17*story_conf+.15*(action_conf if physical else (speaker_conf if speakers else story_conf));confidence=clamp(confidence-(.07 if len(required)>6 else 0),0,1);missing=[track for track in required if track not in observations];weak=[track for track in required if observations.get(track,{}).get('visibility',0)<.2 and not observations.get(track,{}).get('predicted')];level='high' if confidence>=ENTER_ADVANCED and mandatory_coverage>=.9 else ('medium' if confidence>=.50 and mandatory_coverage>=.6 else 'low');cells=segment.get('layout',{}).get('cells',[]);split=len(cells)>1;assigned={str(track) for cell in cells for track in cell.get('trackIds',[])};unassigned=[track for track in required if track not in assigned];reliable=[track for track,row in observations.items() if row.get('confidence',0)>=.3 and (row.get('visibility',0)>=.2 or row.get('predicted'))];person_tracks=[track for track in reliable if observations.get(track,{}).get('class')=='person'];current_speaker,current_turn=_current_turn(active,start,end,speakers);current_cluster=conversation.get('trackToCluster',{}).get(current_speaker);dominant_cluster=conversation.get('dominantClusterId');cluster_scores=conversation.get('clusterSpeech',{});ordered_clusters=sorted(cluster_scores,key=cluster_scores.get,reverse=True);balanced_clusters=len(ordered_clusters)>1 and cluster_scores.get(ordered_clusters[1],0)>=cluster_scores.get(ordered_clusters[0],1)*.45;rapid_dialogue=conversation.get('medianTurnSeconds',99)<1.35;meaningful_reaction=any(len(row.get('participants',[]))>=2 or float(row.get('confidence',0))>=.78 for row in reactions);evidence_void=not reliable;preferred=list(required);conversation_groups=[]
    reaction_tracks=list(dict.fromkeys(str(track) for row in reactions if float(row.get('confidence',0))>=.70 or len(row.get('participants',[]))>=2 for track in row.get('participants',[]) if str(track)!=str(current_speaker)))
    reaction_clusters=defaultdict(list)
    for track in reaction_tracks:
        cluster=conversation.get('trackToCluster',{}).get(track)
        if cluster:reaction_clusters[cluster].append(track)
    reaction_group=max(reaction_clusters.values(),key=len) if reaction_clusters else []
    hurry=(end-start)<1.35 or rapid_dialogue
    if hurry and current_speaker and meaningful_reaction and reaction_group and not physical:
        policy='speaker_reaction_split';reason='A hurried beat holds the active speaker and one nearby reaction group in two persistent views instead of chasing cuts or creating a four-way grid';conversation_groups=[[current_speaker],reaction_group];required=list(dict.fromkeys(required+[current_speaker]+reaction_group));preferred=list(required)
    elif len(conversation.get('clusters',[]))>=2 and speakers and not physical:
        if rapid_dialogue and balanced_clusters:policy='conversation_split';reason='Rapid balanced cross-group dialogue: hold both groups without camera chasing';conversation_groups=[_cluster_tracks(conversation,cluster['id']) for cluster in conversation['clusters'][:2]];preferred=list(dict.fromkeys(track for group in conversation_groups for track in group))
        elif current_cluster and (current_turn>=1.25 or meaningful_reaction):policy='group_hold';reason='A sustained turn keeps the active speaker primary; nearby silent people do not widen the crop';preferred=[current_speaker]
        else:policy='group_hold';reason='A short secondary turn does not justify abandoning the narrative anchor';preferred=_cluster_tracks(conversation,dominant_cluster)
    elif evidence_void:policy='general_safe';reason='No trustworthy person or action region exists'
    elif physical and reliable and unassigned:policy='stable_wide';reason='Action evidence repaired the plan: hold one crop containing performer and object'
    elif physical and reliable:policy='action_camera';reason='Keep the tracked performer and action object instead of falling back to the full source'
    elif len(person_tracks)==1:policy='stable_subject';reason='One reliable person supports a stable crop even when semantic confidence is low';preferred=person_tracks+list(dict.fromkeys(track for row in episodes for track in row.get('objectTrackIds',[])))
    elif level=='low' and reliable:policy='stable_wide';reason='Evidence is uncertain but a reliable subject region exists'
    elif start<.8 and reliable:policy='stable_wide';reason='Acquire visible subjects conservatively without showing the complete horizontal source'
    elif unassigned:policy='stable_wide';reason='Independent evidence found important subjects missing from the proposed layout'
    elif physical:policy='action_camera';reason='Preserve the current action phase and its causal roles'
    elif split and confidence<.84:policy='stable_wide';reason='Split utility is not strong enough for independent cells'
    elif level=='medium':policy='widen_and_hold';reason='Moderate confidence: reduce camera ambition'
    else:policy='execute_plan';reason='Fused evidence supports the validated composition'
    preferred=list(dict.fromkeys(track for track in preferred if track));person_importance=[row['trackId'] for row in importance if row.get('class')=='person' and row['trackId'] in reliable];action_actors=[str(track) for episode in episodes for track in episode.get('actorTrackIds',[]) if str(track) in reliable];anchor=(current_speaker if current_speaker in reliable and speaker_conf>=.58 else None) or (action_actors[0] if action_actors else None) or (person_importance[0] if person_importance else (person_tracks[0] if person_tracks else None));return {'id':f'situation-{index}','segmentId':segment['id'],'start':start,'end':end,'confidence':round(confidence,4),'confidenceLevel':level,'rawPolicy':policy,'policy':policy,'reason':reason,'physicalAction':physical,'requiredTrackIds':required,'preferredTrackIds':preferred,'conversationGroups':conversation_groups,'currentSpeakerTrackId':current_speaker,'currentTurnSeconds':round(current_turn,3),'currentClusterId':current_cluster,'dominantClusterId':dominant_cluster,'visualAnchorTrackId':anchor,'rapidDialogue':rapid_dialogue,'hurriedBeat':hurry,'balancedClusters':balanced_clusters,'meaningfulReaction':meaningful_reaction,'evidenceVoid':evidence_void,'compositionRequiredTrackIds':[str(x) for x in segment.get('mustShowTrackIds',[])],'independentlyAddedTrackIds':unassigned,'missingTrackIds':missing,'weakTrackIds':weak,'reliableTrackIds':reliable,'reliablePersonTrackIds':person_tracks,'reliableRequiredTrackIds':[track for track in required if track in reliable],'reliablePreferredTrackIds':[track for track in preferred if track in reliable],'activeSpeakers':speakers,'actionEpisodeIds':[row['id'] for row in episodes],'actionPhases':phase_by_episode,'reactionIds':[row['id'] for row in reactions],'importance':importance,'evidence':{'mandatoryCoverage':round(mandatory_coverage,4),'visibility':round(visibility,4),'detectionConfidence':round(detection_conf,4),'continuityConfidence':round(continuity,4),'speakerConfidence':round(speaker_conf,4),'actionConfidence':round(action_conf,4),'storyConfidence':round(story_conf,4)}}

def _general_layout(segment,tracks=None):
    tracks=list(dict.fromkeys(str(track) for track in (tracks or segment.get('mustShowTrackIds',[]))));return {'id':f"{segment['id']}:general_safe",'layoutType':'general_safe','cells':[{'id':'safe','outputRect':[0,0,1,1],'trackIds':tracks,'sourcePolicy':'general_safe','priority':'primary','viewportHint':{'centerX':.5,'centerY':.5,'cropWidth':1,'cropHeight':1,'confidence':1}}],'coverage':1,'baseScore':1,'reason':'Full-source confidence fallback','cameraPolicy':'locked_full_source','hardConstraints':{'allMustShowAssigned':True,'allCellsMeaningful':True,'aspectSafe':True,'preserveContinuousAction':True},'stage3Ready':True}

def _stable_wide_layout(segment,tracks):
    tracks=list(dict.fromkeys(tracks));return {'id':f"{segment['id']}:stable_wide",'layoutType':'stable_wide','cells':[{'id':'wide','outputRect':[0,0,1,1],'trackIds':tracks,'sourcePolicy':'cluster_hold','priority':'primary','viewportHint':{'centerX':.5,'centerY':.5,'cropWidth':.75,'cropHeight':1,'confidence':.8}}],'coverage':1,'baseScore':.9,'reason':'One evidence-complete crop before considering split','cameraPolicy':'locked_cluster','hardConstraints':{'allMustShowAssigned':True,'allCellsMeaningful':True,'aspectSafe':True},'stage3Ready':True}

def _focus_layout(segment,tracks,kind='stable_subject',cluster_id=None):
    tracks=list(dict.fromkeys(tracks));cell_id=f"focus-{cluster_id or '-'.join(tracks[:2]) or 'center'}";return {'id':f"{segment['id']}:{kind}",'layoutType':kind,'cells':[{'id':cell_id,'outputRect':[0,0,1,1],'trackIds':tracks,'sourcePolicy':'cluster_hold','priority':'primary','viewportHint':{'centerX':.5,'centerY':.5,'cropWidth':.55,'cropHeight':1,'confidence':.85}}],'coverage':1,'baseScore':.94,'reason':'Stable narrative focus with no low-confidence full-source fallback','cameraPolicy':'locked_cluster','hardConstraints':{'allMustShowAssigned':True,'allCellsMeaningful':True,'aspectSafe':True},'stage3Ready':True}

def _conversation_split_layout(segment,groups):
    groups=[list(dict.fromkeys(group)) for group in groups if group][:2]
    if len(groups)<2:return _stable_wide_layout(segment,[track for group in groups for track in group])
    cells=[]
    for index,group in enumerate(groups):cells.append({'id':f'dialogue-group-{index}','outputRect':[0,index*.5,1,.5],'trackIds':group,'sourcePolicy':'cluster_hold','priority':'primary','viewportHint':{'centerX':.5,'centerY':.5,'cropWidth':.55,'cropHeight':1,'confidence':.9}})
    return {'id':f"{segment['id']}:conversation_split",'layoutType':'conversation_split','cells':cells,'coverage':1,'baseScore':.96,'reason':'Borderless persistent group coverage for rapid cross-group dialogue','cameraPolicy':'locked_groups','hardConstraints':{'allCellsMeaningful':True,'aspectSafe':True,'cellGap':0,'cellStroke':0},'stage3Ready':True}

def _speaker_reaction_split_layout(segment,groups):
    layout=_conversation_split_layout(segment,groups);layout['id']=f"{segment['id']}:speaker_reaction_split";layout['layoutType']='speaker_reaction_split';layout['reason']='Two persistent body-safe views for the active speaker and the meaningful reaction group';return layout

def _stabilize(situations):
    last_policy=None;last_start=0;last_action=None;last_cluster=None;last_preferred=[];last_anchor=None;last_anchor_start=0
    for row in situations:
        raw=row['rawPolicy'];episode=tuple(row['actionEpisodeIds'])
        if episode and episode==last_action and last_policy=='action_camera':row['policy']='action_camera';row['reason']='Continue the same causal action without a policy switch'
        elif last_policy in ('execute_plan','action_camera','stable_wide') and raw=='general_safe' and row['confidence']>=EXIT_ADVANCED and row['start']-last_start<MIN_POLICY_HOLD_SECONDS:row['policy']='stable_wide';row['reason']='Hysteresis prevents a one-segment confidence collapse'
        elif last_policy=='general_safe' and raw in ('execute_plan','action_camera') and row['confidence']<.84:row['policy']='stable_wide';row['reason']='Reacquire with a stable wide frame before returning to advanced direction'
        if raw=='group_hold' and last_policy=='group_hold' and row.get('currentClusterId')!=last_cluster and row.get('currentTurnSeconds',0)<1.25 and row['start']-last_start<MIN_DIALOGUE_SHOT_SECONDS:
            row['preferredTrackIds']=list(last_preferred or row['preferredTrackIds']);row['reason']='Minimum dialogue shot duration suppresses a hurried cross-group switch'
        candidate=row.get('visualAnchorTrackId');anchor_change=bool(last_anchor and candidate and candidate!=last_anchor);elapsed=row['start']-last_anchor_start;duration=row['end']-row['start'];speaker_trigger=bool(row.get('currentSpeakerTrackId')==candidate and row.get('currentTurnSeconds',0)>=1.25 and row.get('evidence',{}).get('speakerConfidence',0)>=.62);action_trigger=bool(row.get('actionEpisodeIds') and row.get('evidence',{}).get('actionConfidence',0)>=.82 and duration>=1.35)
        if anchor_change and elapsed<MIN_VISUAL_SHOT_SECONDS and not (speaker_trigger or action_trigger):
            if last_anchor in row.get('reliablePersonTrackIds',[]):row['policy']='stable_subject';row['preferredTrackIds']=[last_anchor];row['visualAnchorTrackId']=last_anchor;row['reason']='Sequence hold keeps the previous visible narrative anchor instead of making a hurried cut'
            else:row['policy']='stable_wide';row['reason']='Sequence hold widens rather than cutting to an unstable short-lived subject'
        elif duration<1.1 and last_anchor and not (speaker_trigger or action_trigger):
            if last_anchor in row.get('reliablePersonTrackIds',[]):row['policy']='stable_subject';row['preferredTrackIds']=[last_anchor];row['visualAnchorTrackId']=last_anchor;row['reason']='Sub-second story fragment inherits the established visible subject'
            else:row['policy']='stable_wide';row['reason']='Sub-second story fragment uses one stable region instead of a new crop'
        if row['policy']!=last_policy:last_start=row['start']
        if row.get('visualAnchorTrackId') and row.get('visualAnchorTrackId')!=last_anchor:last_anchor=row['visualAnchorTrackId'];last_anchor_start=row['start']
        last_preferred=list(row.get('preferredTrackIds',[]));last_policy=row['policy'];last_action=episode or last_action;last_cluster=row.get('currentClusterId') or last_cluster
    return situations

def apply_dynamic_direction(composition,perception,active,social,actions,world_path,decisions_path,progress=None):
    progress=progress or (lambda *_:None);progress('Dynamic director · reconstructing independent world state',64);directed=copy.deepcopy(composition);memory=_memory(perception);conversation=_conversation_context(active,memory);situations=_stabilize([_situation(segment,perception,memory,active,social,actions,conversation,index) for index,segment in enumerate(directed.get('segments',[]))]);decisions=[]
    for index,(segment,situation) in enumerate(zip(directed.get('segments',[]),situations)):
        before=segment.get('layout',{}).get('layoutType');policy=situation['policy'];segment['mustShowTrackIds']=situation['requiredTrackIds']
        if policy=='general_safe':segment['layout']=_general_layout(segment,situation['requiredTrackIds']);segment['transitionIn']='hold' if index else 'safe_open';segment['confidenceFallback']=True
        elif policy=='stable_wide':segment['layout']=_stable_wide_layout(segment,situation['requiredTrackIds']);segment['transitionIn']='hold'
        elif policy=='stable_subject':segment['layout']=_focus_layout(segment,situation['preferredTrackIds'],'stable_subject');segment['transitionIn']='hold'
        elif policy=='group_hold':segment['layout']=_focus_layout(segment,situation['preferredTrackIds'],'group_hold',situation.get('currentClusterId') or situation.get('dominantClusterId'));segment['transitionIn']='editorial_cut'
        elif policy=='conversation_split':segment['layout']=_conversation_split_layout(segment,situation['conversationGroups']);segment['transitionIn']='hold'
        elif policy=='speaker_reaction_split':segment['layout']=_speaker_reaction_split_layout(segment,situation['conversationGroups']);segment['transitionIn']='hold'
        elif policy=='widen_and_hold':segment['transitionIn']='hold';segment.setdefault('editorial',{}).setdefault('cameraTuning',{})['cropScale']=max(1.18,float(segment.get('editorial',{}).get('cameraTuning',{}).get('cropScale',1)))
        elif policy=='action_camera':segment['keepContinuousAction']=True;segment['transitionIn']='action_continuity'
        segment['dynamicDirector']={'situationId':situation['id'],'confidence':situation['confidence'],'rawPolicy':situation['rawPolicy'],'policy':policy,'reason':situation['reason'],'actionEpisodeIds':situation['actionEpisodeIds'],'actionPhases':situation['actionPhases']};after=segment.get('layout',{}).get('layoutType');decisions.append({'segmentId':segment['id'],'before':before,'after':after,'rawPolicy':situation['rawPolicy'],'policy':policy,'confidence':situation['confidence'],'reason':situation['reason']})
    world={'schemaVersion':SCHEMA_VERSION,'stage':'closed-loop-world-model','trackMemory':{track:{key:value for key,value in row.items() if key!='rows'} for track,row in memory.items()},'conversationTopology':conversation,'situations':situations,'policy':{'independentEvidenceFusion':True,'phaseAwareActionRoles':True,'shortOcclusionPredictionSeconds':.9,'confidenceHysteresis':True,'minimumPolicyHoldSeconds':MIN_POLICY_HOLD_SECONDS,'minimumDialogueShotSeconds':MIN_DIALOGUE_SHOT_SECONDS,'minimumVisualShotSeconds':MIN_VISUAL_SHOT_SECONDS,'visualNarrativeAnchorMemory':True,'transcriptSpeakerGrounding':True,'nonSpeakerActionAnchors':True,'fullSourceFallbackRequiresEvidenceVoid':True,'dominanceUsesNarrativeAndSpeechNotBodySize':True,'silentBystandersAreNotPromoted':True,'hurriedSpeakerReactionUsesTwoViews':True,'apiMayOverrideSafety':False}};decision_report={'schemaVersion':SCHEMA_VERSION,'stage':'confidence-temporal-director','decisions':decisions,'summary':{'segments':len(decisions),'advanced':sum(row['policy'] in ('execute_plan','action_camera') for row in decisions),'stableSubjects':sum(row['policy']=='stable_subject' for row in decisions),'groupHolds':sum(row['policy']=='group_hold' for row in decisions),'conversationSplits':sum(row['policy']=='conversation_split' for row in decisions),'speakerReactionSplits':sum(row['policy']=='speaker_reaction_split' for row in decisions),'stableWide':sum(row['policy']=='stable_wide' for row in decisions),'widened':sum(row['policy']=='widen_and_hold' for row in decisions),'safeFallbacks':sum(row['policy']=='general_safe' for row in decisions),'hysteresisOverrides':sum(row['rawPolicy']!=row['policy'] for row in decisions),'sequenceHoldOverrides':sum('Sequence hold' in row.get('reason','') or 'Sub-second' in row.get('reason','') for row in situations)}};dump(world_path,world);dump(decisions_path,decision_report);progress('Dynamic director · story-weighted conversation camera',66);return directed,world,decision_report

def safety_fallback_plan(report,composition):
    severe={'requiredCoverageRate','actionPhaseCoverage','faceClippingRate','bodyClippingRate','blankCellRate','jitterScore'};failures=severe&set(report.get('failures',[]));segments=set()
    for segment_id,values in report.get('faceAndCaption',{}).get('segments',{}).items():
        if values.get('bodyClipped',0)>0 or values.get('clipped',0)>0:segments.add(segment_id)
    action_ids={row['actionId'] for row in report.get('actionCoverage',[]) if row.get('minimumCoverage',1)<.90}
    if action_ids:
        for segment in composition.get('segments',[]):
            if set(segment.get('dynamicDirector',{}).get('actionEpisodeIds',[]))&action_ids:segments.add(segment['id'])
    if failures and not segments:segments={row['id'] for row in composition.get('segments',[])}
    metrics=report.get('metrics',{});catastrophic=float(metrics.get('requiredCoverageRate',1))<.70 or float(metrics.get('actionPhaseCoverage',1))<.65;mode='general_safe' if catastrophic else 'stable_wide'
    return {'apply':bool(segments),'segmentIds':sorted(segments),'reasonCodes':sorted(failures),'mode':mode,'policy':'replace only failed segments with the safest evidence-complete view'}

def apply_safety_fallback(composition,plan):
    result=copy.deepcopy(composition)
    for segment in result.get('segments',[]):
        if segment['id'] in plan.get('segmentIds',[]):segment['layout']=_general_layout(segment) if plan.get('mode')=='general_safe' else _stable_wide_layout(segment,[str(x) for x in segment.get('mustShowTrackIds',[])]);segment['transitionIn']='hold';segment['closedLoopFallback']=True
    return result

def safety_risk_score(report):
    metrics=report.get('metrics',{});penalty=0
    penalty+=max(0,.94-float(metrics.get('requiredCoverageRate',1)))/.94*4
    penalty+=max(0,.90-float(metrics.get('actionPhaseCoverage',1)))/.90*5
    penalty+=max(0,float(metrics.get('faceClippingRate',0))-.10)*5
    penalty+=max(0,float(metrics.get('bodyClippingRate',0))-.08)*7
    penalty+=max(0,float(metrics.get('blankCellRate',0))-.12)*3
    penalty+=max(0,float(metrics.get('jitterScore',0))-.34)*2
    penalty+=max(0,float(metrics.get('blackFrameRate',0))-.01)*8
    return round(penalty,6)
