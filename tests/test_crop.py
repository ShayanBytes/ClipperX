import unittest,tempfile
from pathlib import Path
from engine.crop import make_crop_keyframes,interpolate

class CropTests(unittest.TestCase):
    def test_subject_is_centered_and_aspect_is_vertical(self):
        perception={'width':1920,'height':1080,'frames':[{'time':0,'detections':[{'trackId':'1','box':[.1,.2,.3,.8],'velocity':[0,0]}]},{'time':1,'detections':[{'trackId':'1','box':[.2,.2,.4,.8],'velocity':[.1,0]}]}]}
        shots={'shots':[{'id':0,'start':0,'end':2,'mode':'single','cameraPolicy':'locked','requiredTrackIds':['1'],'confidence':.9}]}
        with tempfile.TemporaryDirectory() as d: result=make_crop_keyframes(perception,shots,Path(d)/'crops.json')
        self.assertEqual(len(result['keyframes']),2);self.assertGreater(result['keyframes'][0]['centerX'],.15);self.assertLessEqual(result['keyframes'][0]['cropWidth'],1)
    def test_interpolation(self):
        keys=[{'time':0,'centerX':0,'centerY':0,'cropWidth':.3,'cropHeight':1},{'time':2,'centerX':1,'centerY':1,'cropWidth':.5,'cropHeight':.8}]
        self.assertAlmostEqual(interpolate(keys,1)['centerX'],.5)
    def test_editorial_cut_never_becomes_a_pan(self):
        keys=[{'time':0,'centerX':.2,'centerY':.5,'cropWidth':.3,'cropHeight':1,'shotId':1},{'time':2,'centerX':.8,'centerY':.5,'cropWidth':.3,'cropHeight':1,'shotId':2}]
        self.assertAlmostEqual(interpolate(keys,1.99)['centerX'],.2);self.assertAlmostEqual(interpolate(keys,2)['centerX'],.8)
    def test_locked_dialogue_shot_does_not_chase_detection_jitter(self):
        perception={'width':1920,'height':1080,'frames':[{'time':i*.25,'detections':[{'trackId':'1','box':[.15+i*.005,.2,.35+i*.005,.8],'velocity':[.02,0]}]} for i in range(8)]}
        shots={'shots':[{'id':1,'start':0,'end':2,'mode':'single','cameraPolicy':'locked','requiredTrackIds':['1'],'confidence':.9}]}
        with tempfile.TemporaryDirectory() as d: result=make_crop_keyframes(perception,shots,Path(d)/'crops.json')
        self.assertLess(max(k['centerX'] for k in result['keyframes'])-min(k['centerX'] for k in result['keyframes']),.00001)
if __name__=='__main__':unittest.main()
