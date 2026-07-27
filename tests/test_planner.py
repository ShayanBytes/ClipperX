import unittest,tempfile
from pathlib import Path
from engine.planner import build_shot_plans

class PlannerTests(unittest.TestCase):
    def test_ball_selects_action_mode(self):
        scenes=[{'id':0,'start':0,'end':2}]
        perception={'frames':[{'time':1,'detections':[{'trackId':'p','class':'person','box':[.1,.1,.3,.9]},{'trackId':'b','class':'sports ball','box':[.4,.4,.45,.45]}]}]}
        with tempfile.TemporaryDirectory() as d: result=build_shot_plans(scenes,perception,{}, {'frames':[]},Path(d)/'s.json','Action')
        actions=[shot for shot in result['shots'] if shot['mode']=='action'];self.assertTrue(actions);self.assertIn('b',actions[0]['requiredTrackIds'])
    def test_group_conversation_uses_stable_speaker_cuts(self):
        scenes=[{'id':0,'start':0,'end':7}];detections=[{'trackId':'p1','class':'person','box':[.05,.1,.25,.9]},{'trackId':'p2','class':'person','box':[.38,.1,.58,.9]},{'trackId':'p3','class':'person','box':[.7,.1,.9,.9]}]
        perception={'frames':[{'time':i*.25,'detections':detections} for i in range(28)]};active={'frames':[{'time':i*.25,'personTrackId':'p1' if i<9 else ('p2' if i<18 else 'p3'),'confidence':.9} for i in range(28)]}
        with tempfile.TemporaryDirectory() as d: result=build_shot_plans(scenes,perception,{},active,Path(d)/'s.json','Podcast')
        dialogue=[shot for shot in result['shots'] if shot.get('eventType')=='dialogue'];self.assertGreaterEqual(len(dialogue),2);self.assertTrue(all(shot['cameraPolicy']=='locked' and shot['transition']=='cut' for shot in dialogue));self.assertEqual(result['editorialPolicy']['speakerChanges'],'hard_cut')
    def test_semantic_display_labels_are_mapped_to_raw_tracks(self):
        scenes=[{'id':0,'start':0,'end':3}];perception={'frames':[{'time':1,'detections':[{'trackId':'17','class':'person','box':[.1,.1,.3,.9]}]}]}
        semantic={'0':{'storyBeats':[{'start':0,'end':3,'compositionMode':'single','primaryTrackId':'P17','requiredTrackIds':['P17'],'cameraPolicy':'locked','confidence':.9,'reason':'Speaker'}]}}
        with tempfile.TemporaryDirectory() as d: result=build_shot_plans(scenes,perception,{}, {'frames':[]},Path(d)/'s.json','Podcast',semantic)
        self.assertEqual(result['shots'][0]['requiredTrackIds'],['17'])
if __name__=='__main__':unittest.main()
