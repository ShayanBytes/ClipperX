from __future__ import annotations
import argparse,json,subprocess
from pathlib import Path
from statistics import mean
from .common import dump,load

CATEGORIES={
'dialogue':['single-speaker','nearby-pair','separated-pair','three-person-turns','six-person-conversation','overlap','silent-reaction','speaker-exits','occluded-speaker','rapid-turns'],
'sports-action':['penalty-goal','goalkeeper-save','shot-miss','passing-sequence','fast-ball','hidden-ball','camera-shake','wide-field-action','celebration','action-replay'],
'games-objects':['cube-toss','dice-roll','card-reveal','tabletop-token','object-pass','small-object-hands','occluded-object','multiple-moving-objects','result-reveal','game-reaction'],
'group-reactions':['pair-laughter','group-laughter','single-reactor','simultaneous-reactors','irrelevant-background-motion','joke-payoff','surprise','argument','agreement','silent-expression'],
'adversarial':['poor-light','motion-blur','low-resolution','similar-people','edge-subject','fast-cuts','existing-graphics','unusual-aspect','tracker-loss','bad-api-advice']}
TARGETS={'geometricDistortionCount':0,'strokeOrInsetCount':0,'blankOrRedundantSplitCount':0,'bodySafetyRate':.98,'requiredActionCoverage':.95,'openingFocusAccuracy':.90,'splitDecisionAccuracy':.90,'continuousActionAccuracy':.95,'importantObjectCoverage':.95,'cameraCorrectionsPerMinute':1.0,'humanPreferenceRate':.70,'catastrophicFailures':0,'P0Failures':0,'P1Failures':2}
SEVERITY={'P0':'Story is wrong, action/outcome is lost, geometry is distorted, or output is unusable.','P1':'Major framing, split, body-safety, opening-focus, or continuity failure.','P2':'Visible polish problem that does not change story comprehension.'}

def default_manifest():
    cases=[]
    for category,scenarios in CATEGORIES.items():
        for index,scenario in enumerate(scenarios,1):cases.append({'id':f'{category}-{index:02d}','category':category,'scenario':scenario,'source':'input.mp4','candidate':'candidate/output.mp4','baselines':{'center':'baselines/center.mp4','general':'baselines/general.mp4'},'scorecard':'scorecard.json','status':'missing_media'})
    return {'schemaVersion':'1.0','suite':'clipperx-50-take-reliability','releaseGateRequiresCases':50,'targets':TARGETS,'severity':SEVERITY,'cases':cases}

def scorecard_template(case):
    return {'caseId':case['id'],'reviewStatus':'pending','reviewer':'','observations':{'geometricDistortionCount':None,'strokeOrInsetCount':None,'blankOrRedundantSplitCount':None,'openingFocusCorrect':None,'splitDecisionCorrect':None,'continuousActionPreserved':None,'importantObjectCoverage':None,'cameraCorrectionsPerMinute':None,'humanPreference':'unreviewed','catastrophicFailures':[],'issues':[]},'notes':'Compare candidate against source, center baseline and GENERAL baseline before scoring.'}

def init_suite(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);manifest=default_manifest();dump(root/'manifest.json',manifest)
    for case in manifest['cases']:
        folder=root/case['id'];folder.mkdir(exist_ok=True);score=folder/'scorecard.json'
        if not score.exists():dump(score,scorecard_template(case))
    (root/'README.md').write_text('# ClipperX 50-take benchmark\n\nPut each source clip at `<case>/input.mp4`, render ClipperX to `<case>/candidate`, create baselines, review all four views, then run evaluation. A release cannot pass with pending cases.\n')
    return manifest

def _run(command):
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode:raise RuntimeError('\n'.join((result.stderr or result.stdout).splitlines()[-10:]))

def create_baselines(case_dir):
    case_dir=Path(case_dir);source=case_dir/'input.mp4';out=case_dir/'baselines';out.mkdir(exist_ok=True)
    if not source.exists():return {'created':False,'reason':'input.mp4 missing'}
    center=out/'center.mp4';general=out/'general.mp4'
    _run(['ffmpeg','-y','-i',str(source),'-vf',"crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920",'-map','0:v','-map','0:a?','-c:v','libx264','-preset','veryfast','-crf','22','-c:a','aac','-shortest',str(center)])
    graph='[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:12[bg];[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[outv]'
    _run(['ffmpeg','-y','-i',str(source),'-filter_complex',graph,'-map','[outv]','-map','0:a?','-c:v','libx264','-preset','veryfast','-crf','22','-c:a','aac','-shortest',str(general)])
    return {'created':True,'center':str(center),'general':str(general)}

def _automatic_metrics(case_dir):
    candidate=Path(case_dir)/'candidate';quality=load(candidate/'quality-supervisor.json',{}) or {};final=quality.get('final',{});metrics=final.get('metrics',{});composition=load(candidate/'composition-plan.json',{}) or {};segments=composition.get('segments',[]);splits=sum(len(segment.get('layout',{}).get('cells',[]))>1 for segment in segments)
    return {'bodySafetyRate':1-float(metrics.get('bodyClippingRate',0)),'requiredActionCoverage':float(metrics.get('actionPhaseCoverage',0)),'requiredCoverageRate':float(metrics.get('requiredCoverageRate',0)),'jitterScore':float(metrics.get('jitterScore',0)),'splitSegments':splits,'qualityScore':float(final.get('qualityScore',0))}

def evaluate_case(root,case):
    folder=Path(root)/case['id'];score=load(folder/case['scorecard'],{}) or {};source=folder/case['source'];candidate=folder/case['candidate'];complete=source.exists() and candidate.exists() and score.get('reviewStatus')=='complete';automatic=_automatic_metrics(folder) if candidate.exists() else {};obs=score.get('observations',{});human_preference=obs.get('humanPreference');failures=[]
    for issue in obs.get('issues',[]):
        if issue.get('severity') in ('P0','P1','P2'):failures.append(issue)
    if obs.get('catastrophicFailures'):failures.extend({'severity':'P0','code':code} for code in obs['catastrophicFailures'])
    return {'id':case['id'],'category':case['category'],'scenario':case['scenario'],'complete':complete,'status':'complete' if complete else ('needs_review' if source.exists() and candidate.exists() else 'missing_media'),'automatic':automatic,'human':obs,'humanPreferred':1 if human_preference=='candidate' else (0 if human_preference in ('center','general','source') else None),'failures':failures}

def aggregate(results):
    complete=[row for row in results if row['complete']];human=[row['humanPreferred'] for row in complete if row['humanPreferred'] is not None];obs=[row['human'] for row in complete];auto=[row['automatic'] for row in complete];sum_field=lambda key:sum(int(row.get(key,0) or 0) for row in obs);bool_rate=lambda key:mean([bool(row.get(key)) for row in obs if row.get(key) is not None]) if any(row.get(key) is not None for row in obs) else 0;object_values=[float(row.get('importantObjectCoverage')) for row in obs if row.get('importantObjectCoverage') is not None];camera=[float(row.get('cameraCorrectionsPerMinute')) for row in obs if row.get('cameraCorrectionsPerMinute') is not None];metrics={'completedCases':len(complete),'geometricDistortionCount':sum_field('geometricDistortionCount'),'strokeOrInsetCount':sum_field('strokeOrInsetCount'),'blankOrRedundantSplitCount':sum_field('blankOrRedundantSplitCount'),'bodySafetyRate':mean([row.get('bodySafetyRate',0) for row in auto]) if auto else 0,'requiredActionCoverage':mean([row.get('requiredActionCoverage',0) for row in auto]) if auto else 0,'openingFocusAccuracy':bool_rate('openingFocusCorrect'),'splitDecisionAccuracy':bool_rate('splitDecisionCorrect'),'continuousActionAccuracy':bool_rate('continuousActionPreserved'),'importantObjectCoverage':mean(object_values) if object_values else 0,'cameraCorrectionsPerMinute':mean(camera) if camera else 999,'humanPreferenceRate':mean(human) if human else 0,'catastrophicFailures':sum(len(row.get('catastrophicFailures',[])) for row in obs)};gates={'completedCases':metrics['completedCases']>=50,'geometricDistortionCount':metrics['geometricDistortionCount']==0,'strokeOrInsetCount':metrics['strokeOrInsetCount']==0,'blankOrRedundantSplitCount':metrics['blankOrRedundantSplitCount']==0,'bodySafetyRate':metrics['bodySafetyRate']>=TARGETS['bodySafetyRate'],'requiredActionCoverage':metrics['requiredActionCoverage']>=TARGETS['requiredActionCoverage'],'openingFocusAccuracy':metrics['openingFocusAccuracy']>=TARGETS['openingFocusAccuracy'],'splitDecisionAccuracy':metrics['splitDecisionAccuracy']>=TARGETS['splitDecisionAccuracy'],'continuousActionAccuracy':metrics['continuousActionAccuracy']>=TARGETS['continuousActionAccuracy'],'importantObjectCoverage':metrics['importantObjectCoverage']>=TARGETS['importantObjectCoverage'],'cameraCorrectionsPerMinute':metrics['cameraCorrectionsPerMinute']<=TARGETS['cameraCorrectionsPerMinute'],'humanPreferenceRate':metrics['humanPreferenceRate']>=TARGETS['humanPreferenceRate'],'catastrophicFailures':metrics['catastrophicFailures']==0};severity={level:sum(issue.get('severity')==level for row in results for issue in row['failures']) for level in SEVERITY};gates['P0Failures']=severity['P0']==0;gates['P1Failures']=severity['P1']<=TARGETS['P1Failures'];return {'metrics':metrics,'gates':gates,'passed':all(gates.values()),'blockingGates':[key for key,value in gates.items() if not value],'severityCounts':severity}

def markdown_report(report,results):
    lines=['# ClipperX 50-take reliability report','',f"**Release gate:** {'PASS' if report['passed'] else 'BLOCKED'}",f"**Completed:** {report['metrics']['completedCases']}/50",'', '## Blocking gates']+[f"- {gate}" for gate in report['blockingGates']]+['','## Metrics']+[f"- {key}: {value}" for key,value in report['metrics'].items()]+['','## Case status']+[f"- {row['id']} — {row['status']}" for row in results];return '\n'.join(lines)+'\n'

def evaluate_suite(root):
    root=Path(root);manifest=load(root/'manifest.json',None) or init_suite(root);results=[evaluate_case(root,case) for case in manifest['cases']];aggregate_report=aggregate(results);report={'schemaVersion':'1.0','suite':manifest['suite'],'targets':TARGETS,'results':results,**aggregate_report};dump(root/'benchmark-report.json',report);(root/'benchmark-report.md').write_text(markdown_report(report,results));return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('init','evaluate','baselines'));parser.add_argument('--root',default='benchmark-50');parser.add_argument('--case');args=parser.parse_args()
    if args.command=='init':result=init_suite(args.root)
    elif args.command=='evaluate':result=evaluate_suite(args.root)
    else:
        if not args.case:raise SystemExit('--case is required for baselines')
        result=create_baselines(Path(args.root)/args.case)
    print(json.dumps(result if args.command!='init' else {'cases':len(result['cases'])},indent=2))
if __name__=='__main__':main()
