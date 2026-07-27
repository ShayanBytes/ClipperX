import json,tempfile,unittest
from pathlib import Path
from engine.common import start_run_log,status,log_model_use,finish_run_log
from engine.director_orchestrator import orchestrate_direction,_plan_score

class DirectorOrchestratorTests(unittest.TestCase):
    def test_each_run_gets_pasteable_event_and_model_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);pointer=start_run_log(out,{'profile':'Podcast'});status(out,'Perception',10);log_model_use(out,'story_intelligence','gemini','test-model',True);finish_run_log(out,True)
            run=Path(pointer['folder']);self.assertTrue((run/'events.jsonl').exists());self.assertTrue((run/'model-usage.jsonl').exists());self.assertTrue((run/'SHARE-THIS-LOG.txt').exists());summary=json.loads((run/'run-summary.json').read_text());self.assertEqual(summary['status'],'complete');self.assertEqual(summary['events'],1);self.assertEqual(summary['modelCalls'],1)
    def test_local_brain_routes_through_capabilities_and_stops_bounded(self):
        composition={'segments':[{'id':'s','start':0,'end':2,'confidence':.9,'mustShowTrackIds':['p'],'layout':{'layoutType':'single_focus','cells':[{'id':'c','outputRect':[0,0,1,1],'trackIds':['p'],'sourcePolicy':'subject_lock'}]}}]};perception={'width':1920,'height':1080,'frames':[{'time':t,'detections':[{'trackId':'p','class':'person','confidence':.96,'box':[.35,.08,.65,.95]}]} for t in (0,.5,1,1.5)]}
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);start_run_log(out,{});result=orchestrate_direction(composition,perception,{'frames':[],'segments':[]},{'reactions':[]},{'episodes':[]},{'globalSummary':'one person'},out);report=result[-1]
            self.assertEqual(report['routeHistory'][:3],['rethink_direction','reoptimize_sequence','verify_safety']);self.assertLessEqual(len(report['trace']),6);self.assertTrue((out/'orchestrator-report.json').exists());self.assertTrue(report['policy']['dynamicRouting']);self.assertIn('decisionSummary',report)
            self.assertTrue((out/'executive-decision-ledger.json').exists());self.assertTrue(report['planMemory']['rollbackProtection'])
    def test_plan_memory_scores_body_failures_below_clean_plan(self):
        base={'safetyComplete':True,'composition':{'segments':[{'layout':{'layoutType':'stable_subject'}}]},'world':{'situations':[{'evidence':{'mandatoryCoverage':1}}]},'utility':{'decisions':[]},'risk':{'issues':[]}};failed={**base,'risk':{'issues':[{'code':'body_fragment'}]}}
        self.assertGreater(_plan_score(base)['score'],_plan_score(failed)['score'])

if __name__=='__main__':unittest.main()
