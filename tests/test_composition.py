import tempfile,unittest
from pathlib import Path
from engine.composition import build_composition_plan,validate_composition

class CompositionTests(unittest.TestCase):
    def perception(self,count=6,close=False):
        detections=[]
        for index in range(count):
            x=.35+index*.06 if close else .02+index*(.94/max(1,count-1))
            detections.append({'trackId':str(index+1),'class':'person','box':[max(0,x-.04),.15,min(1,x+.04),.85],'velocity':[0,0]})
        return {'width':1920,'height':1080,'frames':[{'time':t*.25,'detections':detections} for t in range(16)]}
    def graph(self,tracks,role='reaction',continuous=False,spread=.8):
        return {'events':[{'id':'e1','start':1,'end':3,'type':'sports_action' if continuous else 'group_reaction','narrativeRole':'action' if continuous else role,'summary':'Important simultaneous moment','mustShowTrackIds':tracks,'optionalTrackIds':[],'importance':.9,'confidence':.9,'keepContinuousAction':continuous,'anticipationSeconds':.75 if continuous else 0,'coverageRequirements':{'singleVerticalCropFeasible':spread<=.3,'simultaneousSubjectCount':len(tracks),'horizontalSpread':spread}}]}
    def plan(self,graph,perception):
        with tempfile.TemporaryDirectory() as folder:return build_composition_plan(graph,perception,Path(folder)/'composition.json')
    def test_three_separated_reactors_choose_four_grid(self):
        plan=self.plan(self.graph(['1','2','3']),self.perception(3));segment=plan['segments'][0]
        self.assertEqual(segment['layout']['layoutType'],'grid_4');self.assertEqual({track for cell in segment['layout']['cells'] for track in cell['trackIds']},{'1','2','3'})
    def test_three_close_reactors_remain_in_one_natural_frame(self):
        plan=self.plan(self.graph(['1','2','3'],spread=.12),self.perception(3,close=True))
        self.assertEqual(plan['segments'][0]['layout']['layoutType'],'shared_wide')
    def test_six_people_use_two_story_bands_before_tiny_six_grid(self):
        plan=self.plan(self.graph([str(i) for i in range(1,7)]),self.perception(6));layout=plan['segments'][0]['layout']
        self.assertEqual(layout['layoutType'],'bands_2x3');self.assertEqual([len(cell['trackIds']) for cell in layout['cells']],[3,3])
    def test_continuous_penalty_action_uses_predictive_pan(self):
        plan=self.plan(self.graph(['1','2','3'],role='action',continuous=True),self.perception(3));segment=plan['segments'][0]
        self.assertEqual(segment['layout']['layoutType'],'action_pan');self.assertEqual(segment['transitionIn'],'action_continuity');self.assertAlmostEqual(segment['start'],.25)
    def test_every_selected_layout_covers_required_subjects(self):
        plan=self.plan(self.graph(['1','2','3','4']),self.perception(4))
        self.assertEqual(validate_composition(plan),[]);self.assertTrue(plan['validation']['valid']);self.assertFalse(plan['stage3Contract']['rendererImplemented'])
if __name__=='__main__':unittest.main()
