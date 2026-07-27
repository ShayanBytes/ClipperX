import unittest
import numpy as np
from engine.grounding import stitch_identities,enrich_interactions
from engine.perception import _appearance

def person(track,box,appearance=None,velocity=None):
    return {'trackId':track,'class':'person','box':box,'rawBox':box,'confidence':.9,'appearance':appearance or [1,0,0,0],'velocity':velocity or [0,0]}

class GroundingTests(unittest.TestCase):
    def test_non_overlapping_matching_tracklets_receive_one_identity(self):
        data={'analysisFps':4,'frames':[{'time':0,'detections':[person('7',[.1,.1,.3,.9])],'faces':[]},{'time':.5,'detections':[person('7',[.12,.1,.32,.9])],'faces':[]},{'time':1.2,'detections':[person('19',[.13,.1,.33,.9])],'faces':[]}]}
        result=stitch_identities(data);ids={row['trackId'] for frame in data['frames'] for row in frame['detections']}
        self.assertEqual(len(ids),1);self.assertEqual(len(result['identities']),1);self.assertEqual(result['identities'][0]['sourceTrackIds'],['7','19'])
    def test_simultaneous_similar_people_are_never_merged(self):
        data={'analysisFps':4,'frames':[{'time':0,'detections':[person('1',[.1,.1,.3,.9]),person('2',[.7,.1,.9,.9])],'faces':[]},{'time':.5,'detections':[person('1',[.1,.1,.3,.9]),person('2',[.7,.1,.9,.9])],'faces':[]}]}
        result=stitch_identities(data);self.assertEqual(len(result['identities']),2)
    def test_camera_motion_is_removed_from_subject_velocity(self):
        data={'analysisFps':4,'frames':[{'time':0,'detections':[person('1',[.1,.1,.3,.9],velocity=[.1,0])],'faces':[]}]}
        enrich_interactions(data,[{'time':0,'dx':.025,'dy':0,'zoom':1,'rotation':0,'confidence':1}]);velocity=data['frames'][0]['detections'][0]['worldVelocity']
        self.assertAlmostEqual(velocity[0],0,places=4);self.assertAlmostEqual(velocity[1],0,places=4)
    def test_object_manipulation_and_gaze_become_interaction_edges(self):
        data={'analysisFps':4,'frames':[{'time':0,'detections':[person('left',[.05,.1,.35,.9]),person('right',[.62,.1,.92,.9]),{'trackId':'ov-3','class':'dice','box':[.23,.55,.28,.62],'rawBox':[.23,.55,.28,.62],'velocity':[0,0]}],'faces':[{'personTrackId':'left','headYaw':.8}]}]}
        enrich_interactions(data,[]);types={row['type'] for row in data['frames'][0]['interactions']}
        self.assertIn('manipulates',types);self.assertIn('looks_at',types)
    def test_person_appearance_descriptor_is_small_and_normalized(self):
        frame=np.zeros((100,80,3),dtype=np.uint8);frame[:]=(30,120,220);descriptor=_appearance(frame,[.1,.1,.9,.9],80,100)
        self.assertEqual(len(descriptor),32);self.assertAlmostEqual(sum(value*value for value in descriptor),1,places=3)
if __name__=='__main__':unittest.main()
