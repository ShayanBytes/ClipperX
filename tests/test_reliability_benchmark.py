import tempfile,unittest
from pathlib import Path
import cv2,numpy as np
from engine.reliability_benchmark import default_manifest,init_suite,evaluate_suite,aggregate,create_baselines

class ReliabilityBenchmarkTests(unittest.TestCase):
    def perfect_results(self):
        rows=[]
        for case in default_manifest()['cases']:
            human={'geometricDistortionCount':0,'strokeOrInsetCount':0,'blankOrRedundantSplitCount':0,'openingFocusCorrect':True,'splitDecisionCorrect':True,'continuousActionPreserved':True,'importantObjectCoverage':1,'cameraCorrectionsPerMinute':0,'humanPreference':'candidate','catastrophicFailures':[],'issues':[]};rows.append({'id':case['id'],'complete':True,'humanPreferred':1,'human':human,'automatic':{'bodySafetyRate':1,'requiredActionCoverage':1},'failures':[]})
        return rows
    def test_manifest_has_fifty_balanced_cases(self):
        manifest=default_manifest();self.assertEqual(len(manifest['cases']),50);counts={category:sum(row['category']==category for row in manifest['cases']) for category in {row['category'] for row in manifest['cases']}};self.assertEqual(set(counts.values()),{10})
    def test_initialization_creates_fifty_pending_scorecards(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=init_suite(folder);cards=list(Path(folder).glob('*/scorecard.json'))
        self.assertEqual(len(manifest['cases']),50);self.assertEqual(len(cards),50)
    def test_pending_cases_block_release_instead_of_fake_passing(self):
        with tempfile.TemporaryDirectory() as folder:
            init_suite(folder);report=evaluate_suite(folder)
        self.assertFalse(report['passed']);self.assertIn('completedCases',report['blockingGates']);self.assertEqual(report['metrics']['completedCases'],0)
    def test_perfect_fifty_case_result_passes_all_gates(self):
        report=aggregate(self.perfect_results());self.assertTrue(report['passed']);self.assertEqual(report['blockingGates'],[])
    def test_single_catastrophic_issue_blocks_release(self):
        rows=self.perfect_results();rows[0]['human']['catastrophicFailures']=['missed_outcome'];rows[0]['failures']=[{'severity':'P0','code':'missed_outcome'}];report=aggregate(rows)
        self.assertFalse(report['passed']);self.assertIn('catastrophicFailures',report['blockingGates']);self.assertIn('P0Failures',report['blockingGates'])
    def test_human_preference_is_a_release_gate(self):
        rows=self.perfect_results()
        for row in rows[:20]:row['humanPreferred']=0;row['human']['humanPreference']='general'
        report=aggregate(rows);self.assertFalse(report['passed']);self.assertIn('humanPreferenceRate',report['blockingGates'])
    def test_center_and_general_baselines_are_real_videos(self):
        with tempfile.TemporaryDirectory() as folder:
            case=Path(folder);source=case/'input.mp4';writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'mp4v'),5,(160,90))
            for index in range(5):writer.write(np.full((90,160,3),40+index*20,dtype=np.uint8))
            writer.release();result=create_baselines(case)
            self.assertTrue(result['created']);self.assertGreater((case/'baselines'/'center.mp4').stat().st_size,0);self.assertGreater((case/'baselines'/'general.mp4').stat().st_size,0)
if __name__=='__main__':unittest.main()
