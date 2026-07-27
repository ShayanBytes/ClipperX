import tempfile,unittest
from pathlib import Path
from engine.temporal_cadence import build_temporal_cadence
from engine.multiview_render import _segment_at

class TemporalCadenceTests(unittest.TestCase):
    def composition(self,action=False):
        return {'segments':[{'id':'s','start':2,'end':5,'mustShowTrackIds':['performer'],'keepContinuousAction':action,'layout':{'layoutType':'single_focus','cells':[{'id':'c','outputRect':[0,0,1,1],'trackIds':['performer'],'sourcePolicy':'subject_lock'}]}}]}
    def perception(self):
        return {'frames':[{'time':t,'detections':[{'trackId':'performer','class':'person','confidence':.95,'box':[.1,.1,.35,.95]},{'trackId':'speaker','class':'person','confidence':.95,'box':[.65,.1,.9,.95]}]} for t in [0,.5,1,1.5,2,2.5,3,3.5,4,4.5,5,5.5]]}
    def test_inspects_every_second_without_forcing_segment_cuts(self):
        result=build_temporal_cadence(self.composition(),[{'id':0,'start':0,'end':6}],self.perception(),{'frames':[]},6)
        directives=result['temporalCadence']['directives'];self.assertGreaterEqual(len(directives),6);self.assertTrue(all(row['end']-row['start']<=1.001 for row in directives));self.assertEqual(len(result['segments']),1)
    def test_scene_cut_forces_immediate_reacquisition(self):
        result=build_temporal_cadence(self.composition(),[{'id':0,'start':0,'end':3.25},{'id':1,'start':3.25,'end':6}],self.perception(),{'frames':[]},6)
        cut=next(row for row in result['temporalCadence']['directives'] if row['start']==3.25);self.assertTrue(cut['hardAcquire']);self.assertIn('scene boundary',cut['reason'])
    def test_strong_new_speaker_is_fast_but_action_keeps_performer(self):
        active={'frames':[{'time':3.1,'personTrackId':'speaker','confidence':.95},{'time':3.6,'personTrackId':'speaker','confidence':.95}]}
        dialogue=build_temporal_cadence(self.composition(False),[{'id':0,'start':0,'end':6}],self.perception(),active,6);row=next(row for row in dialogue['temporalCadence']['directives'] if row['start']==3);self.assertEqual(row['primaryTrackIds'],['speaker']);self.assertTrue(row['fastAcquire'])
        action=build_temporal_cadence(self.composition(True),[{'id':0,'start':0,'end':6}],self.perception(),active,6);row=next(row for row in action['temporalCadence']['directives'] if row['start']==3);self.assertEqual(row['primaryTrackIds'],['performer'])
    def test_gaps_do_not_borrow_a_future_story_segment(self):
        segment,index=_segment_at(self.composition()['segments'],.5,0);self.assertIsNone(segment);segment,index=_segment_at(self.composition()['segments'],2.5,index);self.assertEqual(segment['id'],'s')

if __name__=='__main__':unittest.main()
