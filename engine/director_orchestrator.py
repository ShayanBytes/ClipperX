from __future__ import annotations
import copy,json
from statistics import mean
from pathlib import Path
from .common import dump,log_event,log_model_use
from .story_graph import _gemini_generate,_chat_generate
from .dynamic_director import apply_dynamic_direction
from .adaptive_intelligence import apply_adaptive_intelligence
from .predictive_guard import predictive_preflight

SCHEMA_VERSION='1.2'
MAX_REASONING_ROUNDS=6
SAFETY_ISSUES={'body_fragment','required_subject_missing','predicted_subject_exit','detector_dropout_fragility'}
STRUCTURE_ISSUES={'fallback_overuse','redundant_split','hurried_dialogue_switch'}

def _issue_codes(risk):return sorted({str(row.get('code')) for row in risk.get('issues',[]) if row.get('code')})

def _plan_score(state):
    if not state.get('safetyComplete'):return None
    weights={'body_fragment':18,'required_subject_missing':14,'predicted_subject_exit':10,'detector_dropout_fragility':6,'hurried_dialogue_switch':7,'redundant_split':7,'fallback_overuse':5,'camera_travel_spike':4};issue_rows=state.get('risk',{}).get('issues',[]);issues=_issue_codes(state.get('risk',{}));penalty=min(95,sum(weights.get(str(row.get('code')),3) for row in issue_rows));situations=(state.get('world') or {}).get('situations',[]);coverage=mean([float(row.get('evidence',{}).get('mandatoryCoverage',0)) for row in situations] or [0]);segments=state.get('composition',{}).get('segments',[]);fallback=sum(row.get('layout',{}).get('layoutType')=='general_safe' for row in segments)/max(1,len(segments));selected=[]
    for decision in (state.get('utility') or {}).get('decisions',[]):
        choice=next((row for row in decision.get('candidates',[]) if row.get('name')==decision.get('selected')),None)
        if choice:selected.append(float(choice.get('riskAdjustedUtility',0)))
    utility=mean(selected or [0]);score=max(0,100-penalty-12*fallback+10*coverage+8*utility);return {'score':round(score,6),'issuePenalty':penalty,'mandatoryCoverage':round(coverage,6),'fallbackRate':round(fallback,6),'meanRiskAdjustedUtility':round(utility,6),'issues':issues}

def _restore_best(state,best):
    for key in ('composition','world','calibration','utility','risk','counterfactuals','adaptiveComplete','safetyComplete'):state[key]=copy.deepcopy(best[key])

def _route_options(state):
    if not state.get('world'):return ['rethink_direction']
    if not state.get('adaptiveComplete'):return ['reoptimize_sequence']
    if not state.get('safetyComplete'):return ['verify_safety']
    codes=set(_issue_codes(state.get('risk',{})))
    if codes&SAFETY_ISSUES:return ['verify_safety','reoptimize_sequence']
    if codes&STRUCTURE_ISSUES:return ['rethink_direction','reoptimize_sequence','verify_safety']
    return ['accept','reoptimize_sequence']

def _local_route(options,history):
    for route in ('rethink_direction','reoptimize_sequence','verify_safety','accept'):
        if route in options and (route not in history[-2:] or route=='accept'):return route
    return options[0]

def _brain_prompt(state,options,story):
    situations=[]
    for row in (state.get('world') or {}).get('situations',[])[:80]:situations.append({'segmentId':row.get('segmentId'),'policy':row.get('policy'),'reason':row.get('reason'),'confidence':row.get('confidence'),'requiredTrackIds':row.get('requiredTrackIds'),'speaker':row.get('currentSpeakerTrackId'),'hurried':row.get('hurriedBeat'),'physicalAction':row.get('physicalAction')})
    package={'allowedRoutes':options,'storySummary':story.get('globalSummary',''),'issueCodes':_issue_codes(state.get('risk',{})),'currentPlanScore':_plan_score(state),'bestPlanScore':state.get('bestScore'),'scoreHistory':state.get('scoreHistory',[]),'situations':situations,'history':state.get('history',[])}
    return '''You are the bounded executive director for a video reframing system. Decide which available reasoning capability should run next. Think counterfactually: what can fail if the current path is accepted, and which route is most likely to improve it? You may select only one supplied route. Never override geometry, body-visibility, track-existence, or deterministic safety checks. Return JSON only: {"route":"one allowed route","confidence":0.0,"reason":"short factual reason","predictedBenefit":"short consequence comparison"}.\nSTATE:'''+json.dumps(package,separators=(',',':'))[:120000]

def _model_route(state,options,story,provider,model,key,base,out_dir):
    if not (provider and model and key) or len(options)<2:return None
    try:
        prompt=_brain_prompt(state,options,story);answer=_gemini_generate(model,key,prompt) if provider=='gemini' else _chat_generate(provider,model,key,base,prompt);route=str(answer.get('route',''))
        if route not in options:raise ValueError('model selected a route outside the bounded option set')
        decision={'route':route,'confidence':max(0,min(1,float(answer.get('confidence',0) or 0))),'reason':str(answer.get('reason',''))[:500],'predictedBenefit':str(answer.get('predictedBenefit',''))[:500]};log_model_use(out_dir,'executive_director',provider,model,True,route=route,confidence=decision['confidence'],reason=decision['reason'],predictedBenefit=decision['predictedBenefit']);return decision
    except Exception as exc:log_model_use(out_dir,'executive_director',provider,model,False,error=str(exc)[:800]);return None

def _route(state,options,story,provider,model,key,base,out_dir):
    local=_local_route(options,state['history']);model_decision=_model_route(state,options,story,provider,model,key,base,out_dir);selected=model_decision['route'] if model_decision else local
    safety_override=False
    if set(_issue_codes(state.get('risk',{})))&SAFETY_ISSUES and selected=='accept':selected='verify_safety';safety_override=True
    return selected,local,model_decision,'model' if model_decision else 'local',safety_override

def orchestrate_direction(composition,perception,active,social,actions,story,out_dir,provider=None,model=None,api_key=None,base_url=None,progress=None):
    progress=progress or (lambda *_:None);out=Path(out_dir);state={'composition':copy.deepcopy(composition),'world':None,'calibration':None,'utility':None,'risk':{},'counterfactuals':{},'adaptiveComplete':False,'safetyComplete':False,'history':[],'bestScore':None,'scoreHistory':[]};trace=[];best=None;stagnant=0
    for round_index in range(MAX_REASONING_ROUNDS):
        options=_route_options(state);selected,local,model_decision,decision_source,safety_override=_route(state,options,story,provider,model,api_key,base_url,out);before=_issue_codes(state.get('risk',{}));progress(f'Executive director · {selected.replace("_"," ")}',64+round_index);event={'round':round_index+1,'allowedRoutes':options,'selectedRoute':selected,'decisionSource':decision_source,'safetyOverride':safety_override,'localRecommendation':local,'modelDecision':model_decision,'issuesBefore':before};log_event(out,event,'orchestrator_route')
        if selected=='accept':event['outcome']='accepted';trace.append(event);break
        if selected=='rethink_direction':
            state['composition'],state['world'],_=apply_dynamic_direction(state['composition'],perception,active,social,actions,out/'world-model.json',out/'directing-decisions.json',progress);state['adaptiveComplete']=False;state['safetyComplete']=False
        elif selected=='reoptimize_sequence':
            if not state.get('world'):state['composition'],state['world'],_=apply_dynamic_direction(state['composition'],perception,active,social,actions,out/'world-model.json',out/'directing-decisions.json',progress)
            state['composition'],state['calibration'],state['utility']=apply_adaptive_intelligence(state['composition'],perception,active,state['world'],out/'adaptive-calibration.json',out/'candidate-utility.json',out/'sequence-optimization.json',progress);state['adaptiveComplete']=True;state['safetyComplete']=False
        elif selected=='verify_safety':
            if not state.get('world'):state['composition'],state['world'],_=apply_dynamic_direction(state['composition'],perception,active,social,actions,out/'world-model.json',out/'directing-decisions.json',progress)
            if not state.get('calibration'):state['composition'],state['calibration'],state['utility']=apply_adaptive_intelligence(state['composition'],perception,active,state['world'],out/'adaptive-calibration.json',out/'candidate-utility.json',out/'sequence-optimization.json',progress);state['adaptiveComplete']=True
            state['composition'],state['risk'],state['counterfactuals']=predictive_preflight(state['composition'],perception,state['world'],actions,out/'predictive-risk-report.json',out/'counterfactual-tests.json',progress,state['calibration']);state['safetyComplete']=True
        state['history'].append(selected);event['issuesAfter']=_issue_codes(state.get('risk',{}));score=_plan_score(state);event['planScore']=score
        if score:
            state['scoreHistory'].append({'round':round_index+1,'route':selected,**score});current=float(score['score']);best_value=float(state['bestScore']['score']) if state.get('bestScore') else None
            if best_value is None or current>best_value+.001:best=copy.deepcopy(state);state['bestScore']=copy.deepcopy(score);best['bestScore']=copy.deepcopy(score);event['candidateOutcome']='new_best';stagnant=0
            elif current<best_value-.001 and best is not None:_restore_best(state,best);event['candidateOutcome']='rolled_back';event['outcome']='rejected_regression';trace.append(event);log_event(out,event,'orchestrator_rollback');break
            else:event['candidateOutcome']='no_material_gain';stagnant+=1
        event.setdefault('outcome','completed');trace.append(event)
        if stagnant>=2 and best is not None:_restore_best(state,best);event['stoppedForStagnation']=True;log_event(out,{'round':round_index+1,'bestScore':state.get('bestScore')},'orchestrator_stagnation');break
    else:
        if best is not None:_restore_best(state,best)
        log_event(out,{'message':'Maximum reasoning rounds reached; restored the best verified plan','rounds':MAX_REASONING_ROUNDS,'bestScore':state.get('bestScore')},'orchestrator_bound')
    if best is not None and not state.get('safetyComplete'):_restore_best(state,best)
    report={'schemaVersion':SCHEMA_VERSION,'stage':'non-linear-executive-director','maximumRounds':MAX_REASONING_ROUNDS,'routeHistory':state['history'],'trace':trace,'finalIssues':_issue_codes(state.get('risk',{})),'planMemory':{'bestScore':state.get('bestScore'),'scoreHistory':state.get('scoreHistory',[]),'rollbackProtection':True,'stagnationProtection':True},'decisionSummary':{'modelDecisions':sum(row.get('decisionSource')=='model' for row in trace),'localDecisions':sum(row.get('decisionSource')=='local' for row in trace),'safetyOverrides':sum(bool(row.get('safetyOverride')) for row in trace),'rollbacks':sum(row.get('candidateOutcome')=='rolled_back' for row in trace),'accepted':any(row.get('selectedRoute')=='accept' for row in trace)},'model':{'configured':bool(provider and model and api_key),'provider':provider or None,'model':model or None},'policy':{'stagesAreCallableCapabilities':True,'dynamicRouting':True,'counterfactualConsequenceReasoning':True,'boundedLoops':True,'bestVerifiedPlanMemory':True,'regressionRollback':True,'stagnationStop':True,'safetyOverridesModel':True,'modelCannotInventTracksOrGeometry':True}};dump(out/'orchestrator-report.json',report);dump(out/'executive-decision-ledger.json',trace);dump(out/'predictive-risk-report.json',state['risk']);log_event(out,{'routeHistory':state['history'],'finalIssues':report['finalIssues'],'decisionSummary':report['decisionSummary'],'bestScore':state.get('bestScore')},'orchestrator_complete');return state['composition'],state['world'] or {},state['calibration'] or {},state['utility'] or {},state['risk'],state['counterfactuals'],report
