import tempfile,unittest
from pathlib import Path
import cv2,numpy as np
from engine.framing_intelligence import aspect_safe_crop,prepare_moment
from engine.composition import build_composition_plan,candidates_for_moment
from engine.multiview_render import _crop,render_silent
from engine.quality_supervisor import face_and_caption_metrics

class UniversalFramingTests(unittest.TestCase):
    def graph(self,summary,tracks,role='action'):
        return {'events':[{'id':'e','start':0,'end':2,'type':'context','narrativeRole':role,'summary':summary,'mustShowTrackIds':tracks,'optionalTrackIds':[],'importance':.9,'confidence':.8,'keepContinuousAction':False,'coverageRequirements':{}}]}
    def test_crop_solver_preserves_requested_aspect_at_boundaries(self):
        for aspect in (.316,.633,1.2):
            width,height=aspect_safe_crop(.82,.55,aspect);self.assertAlmostEqual(width/height,aspect,places=3);self.assertLessEqual(width,1);self.assertLessEqual(height,1)
    def test_pixel_crop_does_not_squeeze_a_circle(self):
        frame=np.zeros((200,300,3),dtype=np.uint8);cv2.circle(frame,(150,100),40,(255,255,255),-1);result=_crop(frame,{'centerX':.5,'centerY':.5,'cropWidth':1,'cropHeight':1},100,200);mask=cv2.cvtColor(result,cv2.COLOR_BGR2GRAY);points=cv2.findNonZero((mask>100).astype(np.uint8));x,y,w,h=cv2.boundingRect(points)
        self.assertLess(abs(w/h-1),.08)
    def test_cube_motion_becomes_primary_continuous_action(self):
        frames=[]
        for index in range(9):
            x=.25+index*.055;frames.append({'time':index*.25,'detections':[{'trackId':'p','class':'person','box':[.05,.12,.25,.92],'velocity':[0,0]},{'trackId':'cube','class':'cube','box':[x,.46,x+.06,.54],'velocity':[.055,0]}]})
        perception={'width':1920,'height':1080,'frames':frames};moment={'id':'m','start':0,'end':2,'summary':'They toss the cube to see the result','type':'game','narrativeRole':'action','mustShowTrackIds':['p'],'optionalTrackIds':[],'keepContinuousAction':False,'coverageRequirements':{}};prepared=prepare_moment(moment,perception)
        self.assertTrue(prepared['keepContinuousAction']);self.assertIn('cube',prepared['mustShowTrackIds']);self.assertIn(candidates_for_moment(prepared,perception)[0]['layoutType'],('action_pan','action_wide'))
    def test_sports_shot_never_uses_split_or_grid(self):
        frames=[]
        for index in range(9):
            ball=.25+index*.065;frames.append({'time':index*.25,'detections':[{'trackId':'shooter','class':'person','box':[.05,.1,.25,.94],'velocity':[0,0]},{'trackId':'keeper','class':'person','box':[.78,.08,.96,.95],'velocity':[0,0]},{'trackId':'ball','class':'sports ball','box':[ball,.52,ball+.035,.56],'velocity':[.065,0]}]})
        perception={'width':1920,'height':1080,'frames':frames}
        with tempfile.TemporaryDirectory() as folder:plan=build_composition_plan(self.graph('The player shoots the ball at the goalkeeper',['shooter','keeper','ball']),perception,Path(folder)/'plan.json')
        segment=plan['segments'][0];self.assertTrue(segment['keepContinuousAction']);self.assertIn(segment['layout']['layoutType'],('action_pan','action_wide'));self.assertEqual(len(segment['layout']['cells']),1)
    def test_close_speakers_have_no_split_candidate_for_model_to_choose(self):
        detections=[{'trackId':'a','class':'person','box':[.34,.15,.48,.9],'velocity':[0,0]},{'trackId':'b','class':'person','box':[.50,.15,.64,.9],'velocity':[0,0]}];perception={'width':1920,'height':1080,'frames':[{'time':index*.25,'detections':detections} for index in range(8)]};moment={'id':'m','start':0,'end':2,'summary':'two people talking','type':'dialogue','narrativeRole':'dialogue','mustShowTrackIds':['a','b'],'optionalTrackIds':[],'keepContinuousAction':False,'coverageRequirements':{}};prepared=prepare_moment(moment,perception);layouts=[row['layoutType'] for row in candidates_for_moment(prepared,perception)]
        self.assertEqual(layouts,['shared_wide'])
    def test_renderer_tiles_cells_without_white_strokes_or_insets(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.mp4';writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'mp4v'),5,(160,90))
            frame=np.zeros((90,160,3),dtype=np.uint8);frame[:,:80]=(0,0,240);frame[:,80:]=(0,220,0)
            for _ in range(6):writer.write(frame)
            writer.release();perception={'width':160,'height':90,'frames':[{'time':i/5,'detections':[{'trackId':'a','class':'person','box':[.02,.02,.48,.98],'velocity':[0,0]},{'trackId':'b','class':'person','box':[.52,.02,.98,.98],'velocity':[0,0]}]} for i in range(6)]};plan={'segments':[{'id':'s','start':0,'end':2,'transitionIn':'hard_cut','layout':{'layoutType':'split_2_stack','cells':[{'id':'top','outputRect':[0,0,1,.5],'trackIds':['a'],'sourcePolicy':'subject_lock','viewportHint':{}},{'id':'bottom','outputRect':[0,.5,1,.5],'trackIds':['b'],'sourcePolicy':'subject_lock','viewportHint':{}}]}}]};output=Path(folder)/'out.mp4';render_silent(source,plan,perception,output,folder,90,160);cap=cv2.VideoCapture(str(output));ok,image=cap.read();cap.release()
        self.assertTrue(ok);seam=image[78:82];self.assertFalse(np.any(np.all(seam>235,axis=2)));self.assertGreater(float(image[:80].mean()),5);self.assertGreater(float(image[80:].mean()),5)
    def test_opening_without_detection_stays_conservative_and_centered(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.mp4';writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'mp4v'),5,(160,90))
            for _ in range(5):writer.write(np.full((90,160,3),80,dtype=np.uint8))
            writer.release();plan={'segments':[{'id':'s','start':0,'end':1,'transitionIn':'hard_cut','layout':{'layoutType':'single_focus','cells':[{'id':'main','outputRect':[0,0,1,1],'trackIds':['missing'],'sourcePolicy':'subject_lock','viewportHint':{'centerX':.1,'centerY':.1,'cropWidth':.1,'cropHeight':.2}}]}}]};telemetry=render_silent(source,plan,{'width':160,'height':90,'frames':[{'time':0,'detections':[]}]},Path(folder)/'out.mp4',folder,90,160);view=telemetry['samples'][0]['cells'][0]['view']
        self.assertAlmostEqual(view['centerX'],.5);self.assertAlmostEqual(view['centerY'],.5);self.assertEqual(view['cropHeight'],1)
    def test_body_fragment_is_a_quality_failure(self):
        composition={'segments':[{'id':'s','start':0,'end':1,'layout':{'cells':[{'id':'c','outputRect':[0,0,1,1],'trackIds':['keeper']}]}}]};telemetry={'samples':[{'time':.5,'segmentId':'s','cells':[{'cellId':'c','view':{'centerX':.5,'centerY':.25,'cropWidth':.3,'cropHeight':.3}}]}]};perception={'frames':[{'time':.5,'detections':[{'trackId':'keeper','class':'person','box':[.42,.05,.58,.95]}],'faces':[]}]};metrics=face_and_caption_metrics(telemetry,perception,composition)
        self.assertEqual(metrics['bodyClippingRate'],1);self.assertEqual(metrics['bodyChecks'],1)
if __name__=='__main__':unittest.main()
