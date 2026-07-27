import tempfile,unittest
from pathlib import Path
from engine.editorial import apply_editorial_direction,resolve_profile
from engine.multiview_render import _desired_view,_bgr
from engine.subtitles import make_ass

class EditorialDirectorTests(unittest.TestCase):
    def composition(self):
        segments=[]
        for index,(start,end,tracks) in enumerate(((0,1,['p1']),(1,2,['p1','p2']),(2,4,['p1','ball','keeper']))):
            layout='action_pan' if index==2 else ('split_2_stack' if index==1 else 'single_focus');cells=[{'id':'c','outputRect':[0,0,1,1],'trackIds':tracks,'sourcePolicy':'trajectory_follow' if index==2 else 'subject_lock','viewportHint':{'centerX':.5,'centerY':.5,'cropWidth':.3,'cropHeight':.7}}]
            segments.append({'id':f's{index}','start':start,'end':end,'importance':.5,'mustShowTrackIds':tracks,'keepContinuousAction':index==2,'transitionIn':'hard_cut','layout':{'layoutType':layout,'cells':cells}})
        return {'segments':segments}
    def evidence(self):
        story={'events':[{'id':'e0','start':0,'end':1,'importance':.4},{'id':'e1','start':1,'end':2,'importance':.8},{'id':'e2','start':2,'end':4,'importance':.95}]};social={'utterances':[{'id':'u0','start':0,'end':.8,'speechAct':'question','prosody':{'arousal':.5}}],'reactions':[{'id':'r0','start':1.1,'end':1.8,'confidence':.9}]};actions={'episodes':[{'id':'a0','start':2,'end':3.5,'outcome':{'confidence':.92},'verification':{'verified':True}}]};return story,social,actions
    def direct(self,profile='Podcast'):
        story,social,actions=self.evidence();folder=tempfile.TemporaryDirectory();directed,plan=apply_editorial_direction(self.composition(),story,social,actions,profile,Path(folder.name)/'editorial.json');return folder,directed,plan
    def test_verified_action_has_more_energy_than_dialogue(self):
        folder,directed,plan=self.direct();self.addCleanup(folder.cleanup);self.assertGreater(plan['beats'][2]['energy'],plan['beats'][0]['energy']);self.assertEqual(plan['beats'][2]['role'],'action_payoff')
    def test_sports_profile_widens_continuous_action_camera(self):
        folder,directed,plan=self.direct('Sports');self.addCleanup(folder.cleanup);self.assertGreaterEqual(directed['segments'][2]['editorial']['cameraTuning']['cropScale'],1.12);self.assertEqual(directed['segments'][2]['transitionIn'],'action_continuity')
    def test_required_tracks_and_chronology_are_preserved(self):
        original=self.composition();story,social,actions=self.evidence()
        with tempfile.TemporaryDirectory() as folder:directed,plan=apply_editorial_direction(original,story,social,actions,'Social',Path(folder)/'plan.json')
        self.assertEqual([(s['start'],s['end']) for s in directed['segments']],[(s['start'],s['end']) for s in original['segments']]);self.assertTrue(plan['validation']['allRequiredTracksPreserved']);self.assertFalse(plan['style']['coldOpenReordering'])
    def test_podcast_profile_suppresses_rapid_unnecessary_cut(self):
        folder,directed,plan=self.direct('Podcast');self.addCleanup(folder.cleanup);self.assertEqual(directed['segments'][1]['transitionIn'],'hold');self.assertGreater(plan['pacingPolicy']['minimumCutSeconds'],2)
    def test_hook_candidate_is_selected_from_early_high_value_beats(self):
        folder,directed,plan=self.direct();self.addCleanup(folder.cleanup);self.assertIn(plan['hook']['segmentId'],{'s0','s1','s2'});self.assertGreater(plan['hook']['hookScore'],.5)
    def test_profile_subtitle_style_is_encoded_in_ass(self):
        style=resolve_profile('Cinematic')['subtitle'];words=[{'start':0,'end':.4,'text':'Hello'}]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'captions.ass';make_ass(words,path,1080,1920,style=style);text=path.read_text()
        self.assertIn('Georgia,58',text);self.assertIn(',96,96,260,1',text)
    def test_renderer_crop_scale_and_palette_are_executable(self):
        cell={'outputRect':[0,0,1,1],'trackIds':['p1'],'sourcePolicy':'subject_lock','viewportHint':{}};detection={'trackId':'p1','box':[.4,.2,.6,.8],'velocity':[0,0]};base=_desired_view(cell,[detection],1920,1080,{'cropScale':1});wide=_desired_view(cell,[detection],1920,1080,{'cropScale':1.2})
        self.assertGreater(wide['cropWidth'],base['cropWidth']);self.assertGreaterEqual(wide['cropHeight'],base['cropHeight']);self.assertEqual(_bgr('#112233',(0,0,0)),(51,34,17))
    def test_editorial_profile_cannot_erase_predictive_safety_tuning(self):
        composition=self.composition();composition['segments'][0]['editorial']={'cameraTuning':{'cropScale':1.65,'smoothingScale':1.8,'holdLastSeen':True,'minimumBodyVisibility':.82}};story,social,actions=self.evidence()
        with tempfile.TemporaryDirectory() as folder:directed,_=apply_editorial_direction(composition,story,social,actions,'Social',Path(folder)/'plan.json')
        tuning=directed['segments'][0]['editorial']['cameraTuning'];self.assertEqual(tuning['cropScale'],1.65);self.assertEqual(tuning['smoothingScale'],1.8);self.assertTrue(tuning['holdLastSeen']);self.assertEqual(tuning['minimumBodyVisibility'],.82)
if __name__=='__main__':unittest.main()
