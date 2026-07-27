import tempfile,unittest
from pathlib import Path
from engine.adaptive_intelligence import apply_adaptive_intelligence,learn_video_calibration,optimize_sequence

class AdaptiveIntelligenceTests(unittest.TestCase):
    def segment(self,tracks=('p',),layout='single_focus'):
        return {'id':'s','start':0,'end':2,'mustShowTrackIds':list(tracks),'layout':{'layoutType':layout,'cells':[{'id':'c','outputRect':[0,0,1,1],'trackIds':list(tracks),'sourcePolicy':'subject_lock'}]}}
    def perception(self,confidence=.9,box=None,tracks=('p',)):
        box=box or [.35,.1,.65,.9];return {'frames':[{'time':t,'detections':[{'trackId':track,'class':'person' if track!='ball' else 'sports ball','confidence':confidence,'box':box,'velocity':[.02,0]} for track in tracks]} for t in (0,.5,1,1.5)]}
    def world(self,required=('p',),evidence_void=False,physical=False):
        return {'situations':[{'segmentId':'s','requiredTrackIds':list(required),'preferredTrackIds':list(required),'importance':[{'trackId':track,'score':1} for track in required],'evidenceVoid':evidence_void,'physicalAction':physical,'activeSpeakers':{},'evidence':{'mandatoryCoverage':0 if evidence_void else 1,'visibility':0 if evidence_void else 1,'detectionConfidence':0 if evidence_void else .9,'continuityConfidence':0 if evidence_void else 1,'storyConfidence':.8,'actionConfidence':.9 if physical else 0}}]}
    def run_adaptive(self,composition,perception,world,active=None):
        with tempfile.TemporaryDirectory() as folder:return apply_adaptive_intelligence(composition,perception,active or {'segments':[]},world,Path(folder)/'calibration.json',Path(folder)/'utility.json')
    def test_calibration_changes_with_each_video_distribution(self):
        low=learn_video_calibration(self.perception(.45),{'segments':[]},{'segments':[self.segment()]},self.world());high=learn_video_calibration(self.perception(.95),{'segments':[]},{'segments':[self.segment()]},self.world());self.assertNotEqual(low['detectionConfidence']['median'],high['detectionConfidence']['median']);self.assertFalse(low['policy']['fixedConfidenceCutoff'])
    def test_clear_single_subject_beats_complete_source_without_cutoff(self):
        result,calibration,report=self.run_adaptive({'segments':[self.segment()]},self.perception(.92),self.world());decision=report['decisions'][0];self.assertNotEqual(decision['selected'],'complete_source');self.assertNotEqual(result['segments'][0]['layout']['layoutType'],'general_safe');self.assertEqual(decision['selected'],max(decision['candidates'],key=lambda row:row['utility'])['name'])
    def test_true_evidence_void_allows_complete_source_to_win_utility(self):
        result,_,report=self.run_adaptive({'segments':[self.segment()]},{'frames':[]},self.world(evidence_void=True));decision=report['decisions'][0];self.assertEqual(decision['selected'],'complete_source');self.assertEqual(result['segments'][0]['layout']['layoutType'],'general_safe');self.assertTrue(result['segments'][0]['adaptiveIntelligence']['fallbackSelectedBecauseBestUtility'])
    def test_complex_tracked_action_is_not_forced_to_fallback(self):
        segment=self.segment(('p','ball'),'action_pan');perception=self.perception(.86,[.3,.15,.7,.9],('p','ball'));result,_,report=self.run_adaptive({'segments':[segment]},perception,self.world(('p','ball'),physical=True));self.assertNotEqual(report['decisions'][0]['selected'],'complete_source');self.assertNotEqual(result['segments'][0]['layout']['layoutType'],'general_safe')
    def test_fallback_has_no_bonus_and_must_win_same_candidate_utility(self):
        _,_,report=self.run_adaptive({'segments':[self.segment()]},self.perception(.8),self.world());decision=report['decisions'][0];self.assertNotIn('complete_source',{row['name'] for row in decision['candidates']});winner=max(decision['candidates'],key=lambda row:row['utility']);self.assertEqual(decision['selected'],winner['name']);self.assertTrue(report['policy']['fallbackHasNoSpecialPriority'])
    def test_candidate_weights_are_renormalized_from_context(self):
        _,_,report=self.run_adaptive({'segments':[self.segment()]},self.perception(.9),self.world());weights=report['decisions'][0]['weights'];self.assertAlmostEqual(sum(weights.values()),1,places=5);self.assertGreater(len(set(weights.values())),1)
    def graph_candidate(self,name,utility,track='p',layout='stable_subject'):
        return {'name':name,'layoutType':layout,'riskAdjustedUtility':utility,'layout':{'layoutType':layout,'cells':[{'trackIds':[track]}]}}
    def test_sequence_graph_prevents_one_segment_fallback_flicker(self):
        layers=[]
        for index,(crop,fallback) in enumerate(((.82,.7),(.72,.75),(.82,.7))):layers.append({'segmentId':str(index),'weights':{'temporal':.3},'candidates':[self.graph_candidate('crop',crop),self.graph_candidate('complete_source',fallback,layout='general_safe')]})
        situations=[{'requiredTrackIds':['p']} for _ in layers];path,report=optimize_sequence(layers,situations);self.assertEqual(path,[0,0,0]);self.assertEqual(len(report['transitions']),2)
    def test_story_change_permits_motivated_camera_change(self):
        layers=[{'segmentId':'a','weights':{'temporal':.4},'candidates':[self.graph_candidate('left',.8,'left'),self.graph_candidate('right',.5,'right')]},{'segmentId':'b','weights':{'temporal':.4},'candidates':[self.graph_candidate('left',.5,'left'),self.graph_candidate('right',.8,'right')]}];situations=[{'requiredTrackIds':['left']},{'requiredTrackIds':['right']}];path,_=optimize_sequence(layers,situations);self.assertEqual(path,[0,1])
    def test_report_records_global_path_and_local_greedy_difference(self):
        first=self.segment(('p',));first['id']='a';first['start']=0;first['end']=1;second=self.segment(('p',));second['id']='b';second['start']=1;second['end']=2;world={'situations':[]}
        for segment in (first,second):world['situations'].append({'segmentId':segment['id'],'requiredTrackIds':['p'],'preferredTrackIds':['p'],'importance':[{'trackId':'p','score':1}],'evidence':{'mandatoryCoverage':1,'visibility':1,'detectionConfidence':.9,'continuityConfidence':1,'storyConfidence':.9}})
        with tempfile.TemporaryDirectory() as folder:
            sequence=Path(folder)/'sequence.json';_,_,report=apply_adaptive_intelligence({'segments':[first,second]},self.perception(.9),{'segments':[]},world,Path(folder)/'cal.json',Path(folder)/'utility.json',sequence);self.assertTrue(sequence.exists());self.assertTrue(report['policy']['riskAdjustedMultiHypothesisScoring']);self.assertFalse(report['policy']['greedySegmentSelection']);self.assertEqual(len(report['sequenceOptimization']['selectedPath']),2)
if __name__=='__main__':unittest.main()
