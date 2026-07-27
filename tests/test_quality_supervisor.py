import tempfile,unittest
from pathlib import Path
import cv2,numpy as np
from engine.quality_supervisor import action_phase_coverage,face_and_caption_metrics,inspect_output,correction_plan,patch_composition,benchmark_report,build_contact_sheet,parse_ass_events

class QualitySupervisorTests(unittest.TestCase):
    def composition(self):
        return {'segments':[{'id':'s0','start':0,'end':1,'mustShowTrackIds':['p1'],'layout':{'layoutType':'single_focus','cells':[{'id':'c','outputRect':[0,0,1,1],'trackIds':['p1'],'sourcePolicy':'subject_lock'}]},'editorial':{'cameraTuning':{'cropScale':1,'smoothingScale':1}}},{'id':'s1','start':1,'end':3,'mustShowTrackIds':['p1','ball','keeper'],'keepContinuousAction':True,'layout':{'layoutType':'action_pan','cells':[{'id':'c','outputRect':[0,0,1,1],'trackIds':['p1','ball','keeper'],'sourcePolicy':'trajectory_follow'}]},'editorial':{'cameraTuning':{'cropScale':1.1,'smoothingScale':.9}}}]}
    def test_action_phases_use_phase_specific_required_subjects(self):
        telemetry={'samples':[{'time':.2,'cells':[{'visibleTracks':['actor','ball','target']}]},{'time':.8,'cells':[{'visibleTracks':['actor','ball','target']}]},{'time':1.2,'cells':[{'visibleTracks':['ball','target']}]},{'time':1.8,'cells':[{'visibleTracks':['r1','r2']}]}]};actions={'episodes':[{'id':'a0','mustShowTrackIds':['actor','ball','target','r1','r2'],'actorTrackIds':['actor'],'objectTrackIds':['ball'],'targetTrackIds':['target'],'reactorTrackIds':['r1','r2'],'verification':{'verified':True},'phases':{'anticipation':[0,.4],'action':[.5,1],'outcome':[1,1.4],'reaction':[1.5,2]}}]};result=action_phase_coverage(telemetry,actions)[0]
        self.assertEqual(result['minimumCoverage'],1);self.assertEqual(result['phases']['reaction'],1)
    def test_failed_action_coverage_targets_only_overlapping_segment(self):
        report={'actionCoverage':[{'actionId':'a0','minimumCoverage':.4}],'faceAndCaption':{'segments':{}},'metrics':{'requiredCoverageRate':1,'jitterScore':0},'failures':['actionPhaseCoverage']};actions={'episodes':[{'id':'a0','start':1.2,'end':2.2}]};plan=correction_plan(report,self.composition(),actions)
        self.assertEqual(plan['segmentIds'],['s1']);self.assertTrue(plan['apply'])
    def test_face_clipping_and_caption_collision_are_measured(self):
        composition=self.composition();composition['segments']=composition['segments'][:1];composition['segments'][0]['layout']['cells'][0]['trackIds']=['p1'];telemetry={'samples':[{'time':.5,'segmentId':'s0','cells':[{'cellId':'c','view':{'centerX':.5,'centerY':.5,'cropWidth':.4,'cropHeight':.8}}]}]};perception={'frames':[{'time':.5,'faces':[{'personTrackId':'p1','box':[.1,.72,.28,.9]}]}]};metrics=face_and_caption_metrics(telemetry,perception,composition,[{'start':0,'end':1}])
        self.assertEqual(metrics['faceClippingRate'],1);self.assertEqual(metrics['faceChecks'],1)
    def test_black_and_frozen_output_frames_are_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'black.mp4';writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),5,(80,120));frame=np.zeros((120,80,3),dtype=np.uint8)
            for _ in range(15):writer.write(frame)
            writer.release();result=inspect_output(path)
        self.assertEqual(result['blackFrameRate'],1);self.assertEqual(result['freezeRate'],1)
    def test_targeted_patch_widens_without_changing_required_tracks(self):
        original=self.composition();patched=patch_composition(original,{'segmentIds':['s1'],'widenFactor':1.2,'smoothingFactor':1.3})
        self.assertEqual(patched['segments'][0]['editorial']['cameraTuning']['cropScale'],1);self.assertGreater(patched['segments'][1]['editorial']['cameraTuning']['cropScale'],1.1);self.assertEqual(patched['segments'][1]['mustShowTrackIds'],original['segments'][1]['mustShowTrackIds'])
    def test_benchmark_keeps_deterministic_gates_authoritative(self):
        assessment={'metrics':{'requiredCoverageRate':.8,'actionPhaseCoverage':1,'faceClippingRate':0,'subtitleCollisionRate':0,'jitterScore':0,'blackFrameRate':0,'freezeRate':0,'avDurationDriftSeconds':0},'qualityScore':.9,'passed':False,'failures':['requiredCoverageRate']};report=benchmark_report(assessment,{'used':True,'result':{'overall':'pass'}})
        self.assertFalse(report['passed']);self.assertTrue(report['policy']['deterministicGatesOverrideAiOpinion'])
    def test_contact_sheet_and_ass_parser_create_review_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            video=Path(folder)/'video.mp4';writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),5,(80,120))
            for index in range(20):writer.write(np.full((120,80,3),index*8,dtype=np.uint8))
            writer.release();sheet=Path(folder)/'sheet.jpg';self.assertIsNotNone(build_contact_sheet(video,sheet));self.assertTrue(sheet.exists());ass=Path(folder)/'sub.ass';ass.write_text('Dialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,Hello');events=parse_ass_events(ass)
        self.assertEqual(events,[{'start':1.0,'end':2.5}])
if __name__=='__main__':unittest.main()
