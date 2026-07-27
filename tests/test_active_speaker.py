import tempfile,unittest
from pathlib import Path
from engine.active_speaker import map_active_speakers

class ActiveSpeakerTests(unittest.TestCase):
    def test_single_visible_body_can_ground_audible_transcript_without_face_landmarks(self):
        perception={"frames":[{"time":t,"detections":[{"trackId":"performer","class":"person","box":[.2,.1,.5,.9],"confidence":.9}],"faces":[]} for t in (0,.25,.5,.75,1.0)]}
        audio={"vad":[{"start":0,"end":1}],"diarization":[],"diarizationSource":"voice-activity-fallback"}
        with tempfile.TemporaryDirectory() as folder:data=map_active_speakers(perception,audio,Path(folder)/"active.json")
        self.assertGreater(data["mappingCoverage"],.9);self.assertTrue(all(row.get("personTrackId")=="performer" for row in data["frames"]));self.assertTrue(data["policy"]["neverGuessAmongMultipleBodies"])

    def test_temporal_mouth_motion_beats_a_larger_silent_face(self):
        frames=[]
        for t in (0,.2,.4,.6):
            frames.append({'time':t,'detections':[{'trackId':'speaker','class':'person','box':[.05,.1,.28,.9]},{'trackId':'large-silent','class':'person','box':[.45,.02,.98,.98]}],'faces':[{'personTrackId':'speaker','box':[.08,.12,.24,.35],'mouthMotion':.035},{'personTrackId':'large-silent','box':[.52,.06,.9,.48],'mouthMotion':.002}]})
        audio={'vad':[{'start':0,'end':.7}],'diarization':[],'diarizationSource':'voice-activity-fallback'}
        with tempfile.TemporaryDirectory() as folder:data=map_active_speakers({'frames':frames},audio,Path(folder)/'active.json')
        self.assertTrue(all(row.get('personTrackId')=='speaker' for row in data['frames']));self.assertTrue(data['policy']['rejectsLargestFaceWithoutMouthEvidence'])

    def test_new_turn_after_silence_reacquires_new_speaker_immediately(self):
        def frame(t,a,b):return {'time':t,'detections':[{'trackId':'a','class':'person','box':[.05,.1,.35,.9]},{'trackId':'b','class':'person','box':[.65,.1,.95,.9]}],'faces':[{'personTrackId':'a','box':[.1,.12,.3,.4],'mouthMotion':a},{'personTrackId':'b','box':[.7,.12,.9,.4],'mouthMotion':b}]}
        perception={'frames':[frame(0,.04,.002),frame(.2,.04,.002),frame(.5,.001,.001),frame(.8,.002,.04),frame(1,.002,.04)]}
        audio={'vad':[{'start':0,'end':.25},{'start':.75,'end':1.1}],'diarization':[],'diarizationSource':'voice-activity-fallback'}
        with tempfile.TemporaryDirectory() as folder:data=map_active_speakers(perception,audio,Path(folder)/'active.json')
        at_new_turn=next(row for row in data['frames'] if row['time']==.8);self.assertEqual(at_new_turn['personTrackId'],'b');self.assertEqual(at_new_turn['mappingEvidence'],'mouth_temporal_dominance')

if __name__=="__main__":unittest.main()
