from __future__ import annotations
import copy
from pathlib import Path
from statistics import mean
from .common import clamp,dump

PROFILES={
 'balanced':{'label':'Balanced','minCutSeconds':1.6,'cropScale':1.0,'smoothingScale':1.1,'reactionHoldSeconds':.7,'gapScale':1.0,'canvasColor':'#18161f','borderColor':'#eeeae0','subtitle':{'fontName':'Arial','fontSize':64,'marginV':250,'marginH':86,'outline':5,'maxWords':5,'primaryColor':'#ffffff','highlightColor':'#ffd700'}},
 'podcast':{'label':'Podcast','minCutSeconds':2.2,'cropScale':.97,'smoothingScale':1.35,'reactionHoldSeconds':.9,'gapScale':.9,'canvasColor':'#17161d','borderColor':'#efe9dc','subtitle':{'fontName':'Arial','fontSize':62,'marginV':255,'marginH':92,'outline':5,'maxWords':6,'primaryColor':'#ffffff','highlightColor':'#ffd166'}},
 'sports':{'label':'Sports','minCutSeconds':1.0,'cropScale':1.02,'smoothingScale':.88,'reactionHoldSeconds':.8,'gapScale':.8,'canvasColor':'#10151b','borderColor':'#f1f4ed','subtitle':{'fontName':'Arial','fontSize':66,'marginV':245,'marginH':82,'outline':5,'maxWords':5,'primaryColor':'#ffffff','highlightColor':'#6ee7ff'}},
 'cinematic':{'label':'Cinematic','minCutSeconds':2.6,'cropScale':1.07,'smoothingScale':1.55,'reactionHoldSeconds':1.15,'gapScale':.75,'canvasColor':'#121116','borderColor':'#d9d2c3','subtitle':{'fontName':'Georgia','fontSize':58,'marginV':260,'marginH':96,'outline':4,'maxWords':6,'primaryColor':'#f7f1e5','highlightColor':'#d8b56d'}},
 'social':{'label':'Social','minCutSeconds':1.1,'cropScale':.9,'smoothingScale':.92,'reactionHoldSeconds':.65,'gapScale':1.1,'canvasColor':'#17151f','borderColor':'#ffffff','subtitle':{'fontName':'Arial','fontSize':68,'marginV':240,'marginH':76,'outline':6,'maxWords':4,'primaryColor':'#ffffff','highlightColor':'#ffdf5d'}}
}

def resolve_profile(name):
    key=str(name or 'balanced').strip().lower()
    if 'sport' in key:return PROFILES['sports']
    if 'podcast' in key or 'interview' in key:return PROFILES['podcast']
    if 'cinema' in key or 'film' in key:return PROFILES['cinematic']
    if 'social' in key or 'viral' in key or 'high' in key:return PROFILES['social']
    return PROFILES['balanced']

def _overlaps(row,start,end):return row.get('end',row.get('start',0))>start and row.get('start',0)<end

def _segment_evidence(segment,story,social,actions):
    start,end=segment['start'],segment['end'];events=[row for row in story.get('events',[]) if _overlaps(row,start,end)];utterances=[row for row in social.get('utterances',[]) if _overlaps(row,start,end)];reactions=[row for row in social.get('reactions',[]) if _overlaps(row,start,end)];episodes=[row for row in actions.get('episodes',[]) if _overlaps(row,start,end)];arousal=mean([row.get('prosody',{}).get('arousal',0) for row in utterances] or [0]);importance=max([row.get('importance',0) for row in events] or [segment.get('importance',.4)]);reaction=max([row.get('confidence',0) for row in reactions] or [0]);verified=max([row.get('outcome',{}).get('confidence',0) if row.get('verification',{}).get('verified') else 0 for row in episodes] or [0]);question=any(row.get('speechAct') in ('question','joke_setup') for row in utterances);energy=clamp(importance*.34+arousal*.22+reaction*.22+verified*.22,0,1)
    if episodes:role='action_payoff' if verified>=.6 else 'action'
    elif reactions:role='reaction_payoff'
    elif question:role='setup_hook'
    elif utterances:role='dialogue'
    else:role='breathe'
    hook_score=clamp(energy+(0.13 if question else 0)+(0.12 if reactions else 0)+(0.15 if verified>=.7 else 0),0,1)
    return {'energy':round(energy,3),'hookScore':round(hook_score,3),'role':role,'eventIds':[row.get('id') for row in events],'utteranceIds':[row.get('id') for row in utterances],'reactionIds':[row.get('id') for row in reactions],'actionIds':[row.get('id') for row in episodes]}

def apply_editorial_direction(composition,story,social,actions,profile_name,out_path,progress=None):
    progress=progress or (lambda *_:None);progress('Stage 7 · mapping narrative energy and retention beats',68);profile=copy.deepcopy(resolve_profile(profile_name));directed=copy.deepcopy(composition);segments=directed.get('segments',[]);beats=[]
    for segment in segments:beats.append({'segmentId':segment['id'],'start':segment['start'],'end':segment['end'],**_segment_evidence(segment,story,social,actions)})
    duration=max([segment.get('end',0) for segment in segments] or [0]);hook_pool=[beat for beat in beats if beat['start']<=min(30,max(8,duration*.25))] or beats[:1];hook=max(hook_pool,key=lambda beat:beat['hookScore']) if hook_pool else None;progress('Stage 7 · applying profile camera language and pacing',69);previous=None;last_cut=-999
    for segment,beat in zip(segments,beats):
        layout=segment.get('layout',{}).get('layoutType','single_focus');crop_scale=profile['cropScale']
        if segment.get('keepContinuousAction') or beat['role'].startswith('action'):crop_scale=max(crop_scale,1.12 if profile['label']=='Sports' else 1.07)
        elif beat['role']=='reaction_payoff' and layout in ('single_focus','split_2_stack'):crop_scale=min(crop_scale,.95)
        if layout in ('grid_4','grid_6','bands_2x3','shared_wide','action_wide'):crop_scale=max(crop_scale,1.05)
        transition=segment.get('transitionIn','hard_cut')
        if previous:
            too_soon=segment['start']-last_cut<profile['minCutSeconds'];same_language=previous['role']==beat['role'] and previous['layoutType']==layout
            if segment.get('keepContinuousAction'):transition='action_continuity'
            elif too_soon or same_language:transition='hold'
            else:transition='hard_cut';last_cut=segment['start']
        else:last_cut=segment['start']
        # Safety tuning is produced before editorial styling.  Never overwrite
        # crop widening, last-seen holds, or safety margins with profile defaults.
        existing=segment.get('editorial',{});safety_tuning=existing.get('cameraTuning',{});camera_tuning={**safety_tuning,'cropScale':round(max(crop_scale,float(safety_tuning.get('cropScale',0) or 0)),3),'smoothingScale':round(max(profile['smoothingScale'],float(safety_tuning.get('smoothingScale',0) or 0)),3)}
        segment['transitionIn']=transition;segment['editorial']={**existing,'beatRole':beat['role'],'energy':beat['energy'],'hookScore':beat['hookScore'],'reactionHoldSeconds':profile['reactionHoldSeconds'] if beat['role'] in ('reaction_payoff','action_payoff') else 0,'cameraTuning':camera_tuning,'styleReason':f"{profile['label']} profile · {beat['role']} · energy {beat['energy']}"};previous={'role':beat['role'],'layoutType':layout}
    style={'profile':profile['label'],'canvasColor':profile['canvasColor'],'cellStrokeWidth':0,'cellGap':0,'borderlessCells':True,'subtitleStyle':profile['subtitle'],'chronologyPolicy':'preserve_causal_order','coldOpenReordering':False};directed['editorialStyle']=style;directed['stage7Contract']={'applied':True,'profile':profile['label'],'chronologyPreserved':True,'segmentCountPreserved':len(segments)==len(composition.get('segments',[]))}
    plan={'schemaVersion':'1.0','stage':'stage-7-editorial-style-retention-director','profile':profile['label'],'hook':hook,'beats':beats,'style':style,'pacingPolicy':{'minimumCutSeconds':profile['minCutSeconds'],'reactionHoldSeconds':profile['reactionHoldSeconds'],'causalChronologyPreserved':True,'rapidCutSuppression':True},'validation':{'segmentCountPreserved':len(segments)==len(composition.get('segments',[])),'allRequiredTracksPreserved':all(set(original.get('mustShowTrackIds',[]))==set(updated.get('mustShowTrackIds',[])) for original,updated in zip(composition.get('segments',[]),segments))}}
    dump(out_path,plan);return directed,plan
