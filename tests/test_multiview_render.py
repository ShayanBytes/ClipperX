import tempfile,unittest
from pathlib import Path
import cv2,numpy as np
from engine.multiview_render import render_silent,evaluate_telemetry,propose_corrections,render_stage3

class MultiViewRenderTests(unittest.TestCase):
    def source(self,folder,frames=20):
        path=Path(folder)/'source.mp4';writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),10,(160,90))
        for index in range(frames):
            frame=np.zeros((90,160,3),dtype=np.uint8);frame[:,:80]=(0,0,240);frame[:,80:]=(0,220,0);writer.write(frame)
        writer.release();return path
    def perception(self,frames=20,moving=False):
        rows=[]
        for index in range(frames):
            shift=index*.01 if moving else 0
            rows.append({'time':index/10,'detections':[{'trackId':'1','class':'person','box':[.08+shift,.12,.32+shift,.9],'velocity':[.1 if moving else 0,0]},{'trackId':'2','class':'person','box':[.68,.12,.92,.9],'velocity':[0,0]}]})
        return {'width':160,'height':90,'frames':rows}
    def split_plan(self):
        return {'segments':[{'id':'s','start':0,'end':2,'mustShowTrackIds':['1','2'],'keepContinuousAction':False,'layout':{'layoutType':'split_2_stack','cells':[{'id':'top','outputRect':[0,0,1,.5],'trackIds':['1'],'sourcePolicy':'subject_lock','viewportHint':{'centerX':.2,'centerY':.5,'cropWidth':.35,'cropHeight':1}},{'id':'bottom','outputRect':[0,.5,1,.5],'trackIds':['2'],'sourcePolicy':'subject_lock','viewportHint':{'centerX':.8,'centerY':.5,'cropWidth':.35,'cropHeight':1}}]}}]}
    def test_split_renderer_places_left_and_right_subjects_in_story_bands(self):
        with tempfile.TemporaryDirectory() as folder:
            source=self.source(folder);output=Path(folder)/'silent.mp4';telemetry=render_silent(str(source),self.split_plan(),self.perception(),output,folder,90,160)
            cap=cv2.VideoCapture(str(output));ok,frame=cap.read();cap.release();self.assertTrue(ok);self.assertGreater(int(frame[35,45,2]),int(frame[35,45,1]));self.assertGreater(int(frame[125,45,1]),int(frame[125,45,2]));evaluation=evaluate_telemetry(telemetry,self.split_plan());self.assertEqual(evaluation['metrics']['requiredCoverageRate'],1)
    def test_predictive_action_camera_moves_without_large_jumps(self):
        plan={'segments':[{'id':'a','start':0,'end':2,'mustShowTrackIds':['1'],'keepContinuousAction':True,'layout':{'layoutType':'action_pan','cells':[{'id':'main','outputRect':[0,0,1,1],'trackIds':['1'],'sourcePolicy':'trajectory_follow','viewportHint':{'centerX':.2,'centerY':.5,'cropWidth':.32,'cropHeight':1}}]}}]}
        with tempfile.TemporaryDirectory() as folder:
            telemetry=render_silent(str(self.source(folder)),plan,self.perception(moving=True),Path(folder)/'action.mp4',folder,90,160);centers=[sample['cells'][0]['view']['centerX'] for sample in telemetry['samples'] if sample['cells']]
        self.assertTrue(all(b>=a-.0001 for a,b in zip(centers,centers[1:])));self.assertLess(max([b-a for a,b in zip(centers,centers[1:])] or [0]),.08)
    def test_quality_failure_produces_bounded_correction_settings(self):
        evaluation={'failures':['requiredCoverageRate','jitterScore']};correction=propose_corrections(evaluation)
        self.assertGreater(correction['extraMargin'],0);self.assertGreater(correction['smoothingScale'],1)
    def test_full_stage3_mux_produces_final_video_and_evaluation(self):
        with tempfile.TemporaryDirectory() as folder:
            source=self.source(folder,10);output=Path(folder)/'final.mp4';result=render_stage3(str(source),self.split_plan(),self.perception(10),output,folder,None,90,160)
            self.assertTrue(output.exists());self.assertGreater(output.stat().st_size,0);self.assertIn('quality',result);self.assertTrue((Path(folder)/'render-evaluation.json').exists())
    def test_missing_first_detection_uses_full_source_not_middle_crop(self):
        plan={'segments':[{'id':'s','start':0,'end':2,'mustShowTrackIds':['missing'],'layout':{'layoutType':'stable_wide','cells':[{'id':'wide','outputRect':[0,0,1,1],'trackIds':['missing'],'sourcePolicy':'cluster_hold'}]}}]};perception={'frames':[{'time':0,'detections':[]},{'time':1,'detections':[]}]}
        with tempfile.TemporaryDirectory() as folder:
            telemetry=render_silent(str(self.source(folder)),plan,perception,Path(folder)/'safe.mp4',folder,90,160);cell=telemetry['samples'][0]['cells'][0]
        self.assertTrue(cell['evidenceFallback']);self.assertFalse(cell['blank']);self.assertEqual(cell['view'],{'centerX':.5,'centerY':.5,'cropWidth':1,'cropHeight':1})
    def test_missing_split_tracks_collapse_to_one_recovery_view_not_duplicate_video(self):
        plan=self.split_plan();perception={'frames':[{'time':0,'detections':[]},{'time':1,'detections':[]}]}
        with tempfile.TemporaryDirectory() as folder:
            telemetry=render_silent(str(self.source(folder)),plan,perception,Path(folder)/'collapsed.mp4',folder,90,160);sample=telemetry['samples'][0]
        self.assertTrue(sample['collapsedDuplicateSplit']);self.assertEqual(len(sample['cells']),1);self.assertTrue(sample['cells'][0]['evidenceFallback'])
if __name__=='__main__':unittest.main()
