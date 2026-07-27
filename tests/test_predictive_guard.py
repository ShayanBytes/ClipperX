import tempfile,unittest
from pathlib import Path
from engine.predictive_guard import predictive_preflight

class PredictiveGuardTests(unittest.TestCase):
    def codes(self,risk):return {row['code'] for row in risk.get('detectedIssues',[])+risk.get('issues',[])}
    def run_guard(self,composition,perception,world=None,actions=None,calibration=None):
        with tempfile.TemporaryDirectory() as folder:
            result=predictive_preflight(composition,perception,world or {'situations':[]},actions or {'episodes':[]},Path(folder)/'risk.json',Path(folder)/'tests.json',calibration=calibration)
            self.assertTrue((Path(folder)/'risk.json').exists());self.assertTrue((Path(folder)/'tests.json').exists());return result
    def segment(self,segment_id='s',start=0,end=2,track='p'):
        return {'id':segment_id,'start':start,'end':end,'mustShowTrackIds':[track],'layout':{'layoutType':'single_focus','cells':[{'id':'c','outputRect':[0,0,1,1],'trackIds':[track],'sourcePolicy':'subject_lock'}]},'dynamicDirector':{'actionEpisodeIds':[]}}
    def perception(self,positions):
        return {'source':{'width':1920,'height':1080},'frames':[{'time':index*.5,'detections':[{'trackId':'p','class':'person','confidence':.95,'box':[x,.1,min(1,x+.18),.9],'velocity':[.15,0]}]} for index,x in enumerate(positions)]}
    def test_predicts_camera_travel_before_render_and_stabilizes_it(self):
        composition={'segments':[self.segment()]};repaired,risk,tests=self.run_guard(composition,self.perception((.05,.25,.55,.78)));codes=self.codes(risk);self.assertTrue({'camera_travel_spike','predicted_subject_exit'}&codes);tuning=repaired['segments'][0]['editorial']['cameraTuning'];self.assertTrue(tuning['holdLastSeen']);self.assertGreaterEqual(tuning['cropScale'],1.22);self.assertGreater(tests['trials'][0].get('coverage',-1),-1)
    def test_counterfactual_suite_runs_many_cases_from_one_real_segment(self):
        composition={'segments':[self.segment()]};_,risk,tests=self.run_guard(composition,self.perception((.3,.31)));self.assertGreaterEqual(risk['summary']['simulatedTrials'],40);self.assertEqual(risk['summary']['simulatedTrials'],len(tests['trials']))
    def test_predicts_misused_general_fallback_and_restores_stable_crop(self):
        segment=self.segment();segment['layout']={'layoutType':'general_safe','cells':[{'id':'safe','outputRect':[0,0,1,1],'trackIds':['p'],'sourcePolicy':'general_safe'}]};composition={'segments':[segment]};world={'situations':[{'segmentId':'s','evidenceVoid':False}]};repaired,risk,_=self.run_guard(composition,self.perception((.3,.31)),world);self.assertIn('fallback_overuse',self.codes(risk));self.assertEqual(repaired['segments'][0]['layout']['layoutType'],'stable_wide')
    def test_predicts_hurried_dialogue_switch_and_holds_previous_shot(self):
        first=self.segment('a',0,1,'left');second=self.segment('b',1,2,'right');first['layout']['cells'][0]['trackIds']=['left'];second['layout']['cells'][0]['trackIds']=['right'];perception={'frames':[]};calibration={'turnDuration':{'lowerQuartile':1.6,'median':1.8},'segmentDuration':{'median':1},'subjectArea':{'lowerQuartile':.01}};world={'situations':[{'segmentId':'a','currentSpeakerTrackId':'left','activeSpeakers':{'left':.9}},{'segmentId':'b','currentSpeakerTrackId':'right','activeSpeakers':{'right':.9}}]};repaired,risk,_=self.run_guard({'segments':[first,second]},perception,world=world,calibration=calibration);self.assertIn('hurried_dialogue_switch',self.codes(risk));self.assertEqual(repaired['segments'][1]['layout'],repaired['segments'][0]['layout'])
    def test_missing_turn_reference_does_not_mark_every_scene_hurried_dialogue(self):
        first=self.segment('a',0,2,'left');second=self.segment('b',2,4,'right');calibration={'turnDuration':{'lowerQuartile':99,'median':99},'segmentDuration':{'median':2},'subjectArea':{'lowerQuartile':.01}}
        _,risk,_=self.run_guard({'segments':[first,second]},{'frames':[]},calibration=calibration)
        self.assertNotIn('hurried_dialogue_switch',self.codes(risk))
    def test_predicts_redundant_split_before_pixels_are_rendered(self):
        segment=self.segment();segment['mustShowTrackIds']=['p'];segment['layout']={'layoutType':'split_2_stack','cells':[{'id':'a','outputRect':[0,0,1,.5],'trackIds':['p']},{'id':'b','outputRect':[0,.5,1,.5],'trackIds':['p']}]};repaired,risk,_=self.run_guard({'segments':[segment]},self.perception((.3,.31)));self.assertIn('redundant_split',self.codes(risk));self.assertEqual(repaired['segments'][0]['layout']['layoutType'],'stable_wide')
    def test_dropout_fragility_enables_last_seen_hold(self):
        segment=self.segment();repaired,risk,_=self.run_guard({'segments':[segment]},self.perception((.3,)));codes=self.codes(risk);self.assertIn('detector_dropout_fragility',codes);self.assertTrue(repaired['segments'][0]['editorial']['cameraTuning']['holdLastSeen'])
    def test_real_perception_source_path_uses_top_level_dimensions(self):
        perception=self.perception((.3,.31));perception['source']='C:/videos/input.mp4';perception['width']=1280;perception['height']=720
        repaired,risk,tests=self.run_guard({'segments':[self.segment()]},perception)
        self.assertEqual(len(repaired['segments']),1);self.assertGreater(len(tests['trials']),0);self.assertIn('summary',risk)
    def test_scene_is_rejected_and_widened_when_people_would_be_half_visible(self):
        segment=self.segment();segment['mustShowTrackIds']=['left','right'];segment['layout']['cells'][0]['trackIds']=['left','right'];perception={'width':1920,'height':1080,'frames':[{'time':t,'detections':[{'trackId':'left','class':'person','confidence':.96,'box':[.02,.05,.28,.98]},{'trackId':'right','class':'person','confidence':.96,'box':[.72,.05,.98,.98]}]} for t in (0,.5,1,1.5)]}
        repaired,risk,_=self.run_guard({'segments':[segment]},perception);self.assertIn('body_fragment',self.codes(risk));self.assertEqual(repaired['segments'][0]['layout']['layoutType'],'conversation_split');self.assertEqual(len(repaired['segments'][0]['layout']['cells']),2);self.assertFalse(risk['summary']['releaseBlocked']);self.assertFalse(risk['issues']);self.assertEqual(risk['policy']['minimumHumanBodyVisibility'],.82)
    def test_missing_action_object_does_not_force_full_source_body_fallback(self):
        segment=self.segment();segment['mustShowTrackIds']=['person-1','ball-7'];segment['layout']['cells'][0]['trackIds']=['person-1','ball-7']
        perception={'width':1920,'height':1080,'frames':[{'time':t,'detections':[{'trackId':'person-1','class':'person','confidence':.95,'box':[.35,.08,.65,.96]}]} for t in (0,.5,1,1.5)]}
        world={'situations':[{'segmentId':'s','evidenceVoid':False,'reliableTrackIds':['person-1'],'reliableRequiredTrackIds':['person-1'],'reliablePreferredTrackIds':['person-1'],'preferredTrackIds':['person-1','ball-7'],'missingTrackIds':['ball-7']}]}
        repaired,risk,_=self.run_guard({'segments':[segment]},perception,world)
        self.assertNotEqual(repaired['segments'][0]['layout']['layoutType'],'general_safe');self.assertNotIn('required_subject_missing',{row['code'] for row in risk['issues']})
    def test_fragmented_people_that_are_never_coviewable_do_not_create_duplicate_split(self):
        segment=self.segment();segment['mustShowTrackIds']=['old','new'];segment['layout']['cells'][0]['trackIds']=['old','new']
        perception={'width':1920,'height':1080,'frames':[{'time':0,'detections':[{'trackId':'old','class':'person','box':[.1,.1,.35,.95]}]},{'time':.5,'detections':[{'trackId':'old','class':'person','box':[.1,.1,.35,.95]}]},{'time':1,'detections':[{'trackId':'new','class':'person','box':[.7,.1,.95,.95]}]},{'time':1.5,'detections':[{'trackId':'new','class':'person','box':[.7,.1,.95,.95]}]}]}
        repaired,_,_=self.run_guard({'segments':[segment]},perception,{'situations':[{'segmentId':'s','evidenceVoid':False}]})
        self.assertNotEqual(repaired['segments'][0]['layout']['layoutType'],'conversation_split');self.assertNotEqual(repaired['segments'][0]['layout']['layoutType'],'general_safe')
if __name__=='__main__':unittest.main()
