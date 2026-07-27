import tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from engine.story_graph import build_evidence,validate_story_graph,graph_to_semantic,_request_json,_gemini_generate,_provider_capabilities

class StoryGraphTests(unittest.TestCase):
    def sample(self):
        detections=[{'trackId':'1','class':'person','box':[.02,.1,.2,.9],'velocity':[0,0]},{'trackId':'2','class':'person','box':[.42,.1,.58,.9],'velocity':[0,0]},{'trackId':'3','class':'person','box':[.8,.1,.98,.9],'velocity':[0,0]}]
        frames=[]
        for index in range(16):
            faces=[{'personTrackId':track,'box':[0,0,.1,.1],'mouthMotion':.03 if index>6 else .005} for track in ('1','2','3')]
            frames.append({'time':index*.25,'detections':detections,'faces':faces})
        perception={'width':1920,'height':1080,'frames':frames}
        audio={'text':'That was a joke haha','words':[{'start':1,'end':1.2,'text':'joke'},{'start':2,'end':2.3,'text':'haha'}]}
        active={'frames':[{'time':i*.25,'personTrackId':'1','confidence':.8} for i in range(16)]}
        scenes=[{'id':0,'start':0,'end':4}]
        return perception,audio,active,scenes
    def test_group_laughter_keeps_every_reactor_as_story_evidence(self):
        perception,audio,active,scenes=self.sample();evidence=build_evidence(perception,audio,active,scenes,4)
        raw={'events':[{'id':'laugh','start':1.5,'end':3.5,'type':'group_reaction','narrativeRole':'reaction','summary':'Three people laugh','actors':[],'reactors':['P1','P2','P3'],'mustShowTrackIds':['P1','P2','P3'],'importance':.9,'confidence':.9}]}
        graph=validate_story_graph(raw,evidence,perception,4);event=graph['events'][0]
        self.assertEqual(set(event['mustShowTrackIds']),{'1','2','3'});self.assertEqual(event['coverageRequirements']['importantRegionCount'],3);self.assertFalse(event['coverageRequirements']['singleVerticalCropFeasible'])
    def test_action_reaction_causal_link_is_recovered(self):
        perception,audio,active,scenes=self.sample();evidence=build_evidence(perception,audio,active,scenes,4)
        raw={'events':[{'id':'roll','start':.5,'end':1.5,'type':'object_action','narrativeRole':'action','summary':'Person rolls die','actors':['1'],'mustShowTrackIds':['1'],'importance':.8,'confidence':.8},{'id':'laugh','start':1.7,'end':3,'type':'group_reaction','narrativeRole':'reaction','summary':'Group laughs','reactors':['1','2','3'],'mustShowTrackIds':['1','2','3'],'importance':.9,'confidence':.8}]}
        graph=validate_story_graph(raw,evidence,perception,4)
        self.assertTrue(any(row['from']=='laugh' and row['to']=='roll' and row['type']=='reacts_to' for row in graph['relations']))
    def test_invented_tracks_are_removed_and_stage_two_adapter_is_bounded(self):
        perception,audio,active,scenes=self.sample();evidence=build_evidence(perception,audio,active,scenes,4)
        raw={'events':[{'id':'e','start':-8,'end':40,'type':'dialogue','narrativeRole':'setup','actors':['P1','P999'],'mustShowTrackIds':['P1','P999'],'importance':2,'confidence':2}]}
        graph=validate_story_graph(raw,evidence,perception,4);event=graph['events'][0]
        self.assertEqual(event['mustShowTrackIds'],['1']);self.assertEqual((event['start'],event['end']),(0,4));self.assertEqual(event['importance'],1)
        semantic=graph_to_semantic(graph,scenes);self.assertEqual(semantic['0']['storyBeats'][0]['requiredTrackIds'],['1'])
    def test_text_model_receives_coordinate_trajectories_and_pairwise_geometry(self):
        perception,audio,active,scenes=self.sample();evidence=build_evidence(perception,audio,active,scenes,4);dossier=evidence['windows'][0]['coordinateDossier']
        self.assertEqual(dossier['coordinateSystem']['origin'],'top-left');self.assertEqual(dossier['coordinateSystem']['units'],'normalized 0..1');self.assertGreaterEqual(len(dossier['timeline']),2)
        track=next(row for row in dossier['tracks'] if row['trackId']=='1');self.assertIn('medianBox',track);self.assertIn('edgeRisk',track);self.assertIn('motionDirection',track)
        pair=next(row for row in dossier['pairwiseRelations'] if {row['trackA'],row['trackB']}=={'1','2'});self.assertGreater(pair['coVisibleRate'],.9);self.assertIn('meanCenterDistance',pair);self.assertIn('singleVerticalCropLikely',pair)
    def test_coordinate_hint_is_grounded_without_invented_tracks(self):
        perception,audio,active,scenes=self.sample();evidence=build_evidence(perception,audio,active,scenes,4)
        raw={'events':[{'id':'talk','start':0,'end':4,'type':'dialogue','narrativeRole':'setup','mustShowTrackIds':['1','2'],'optionalTrackIds':['3'],'importance':.8,'confidence':.8}],'directingHints':[{'eventId':'talk','primaryTrackIds':['2','999'],'excludeTrackIds':['3'],'spatialIntent':'two_independent_regions','coordinateReason':'P2 x=.50 and P1 x=.11 are co-visible'}]}
        graph=validate_story_graph(raw,evidence,perception,4);event=graph['events'][0]
        self.assertEqual(event['mustShowTrackIds'][0],'2');self.assertEqual(event['optionalTrackIds'],[]);self.assertEqual(event['directingHint']['primaryTrackIds'],['2']);self.assertEqual(graph['directingHints'][0]['spatialIntent'],'two_independent_regions')
    def test_capability_router_uses_text_for_deepseek_and_video_for_gemini(self):
        self.assertEqual(_provider_capabilities('custom','DeepSeek-V4-Pro')['mode'],'text');self.assertFalse(_provider_capabilities('custom','DeepSeek-V4-Pro')['video']);self.assertTrue(_provider_capabilities('gemini','gemini-2.5-flash')['video'])
    def test_provider_retry_is_bounded_to_three_attempts(self):
        with patch('engine.story_graph.requests.post',side_effect=RuntimeError('offline')) as request,patch('engine.story_graph.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'after 3 bounded attempts'):_request_json('https://example.invalid',{}, {},lambda data:data)
        self.assertEqual(request.call_count,3)
    def test_gemini_generate_uses_a_valid_provider_url(self):
        with patch('engine.story_graph._request_json',side_effect=lambda url,*args,**kwargs:{'url':url}): result=_gemini_generate('gemini-test','secret','prompt')
        self.assertEqual(result['url'],'https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent?key=secret')
if __name__=='__main__':unittest.main()
