import unittest
import cv2,numpy as np
from engine.action_intelligence import build_trajectories,build_action_intelligence,attach_social_reactions,count_die_pips
from engine.story_graph import build_evidence,_local_events

class ActionIntelligenceTests(unittest.TestCase):
    def perception(self,moving=True):
        frames=[]
        for index in range(6):
            t=index*.25;x=.2+(index*.12 if moving else 0);frames.append({'time':t,'detections':[{'trackId':'shooter','class':'person','box':[.03,.12,.25,.92],'velocity':[0,0]},{'trackId':'ball','class':'sports ball','box':[x-.025,.48,x+.025,.54],'velocity':[.48 if moving else 0,0],'worldVelocity':[.48 if moving else 0,0]},{'trackId':'keeper','class':'person','box':[.76,.18,.96,.9],'velocity':[0,0]}],'faces':[]})
        return {'analysisFps':4,'frames':frames}
    def test_camera_compensated_ball_path_becomes_trajectory(self):
        tracks=build_trajectories(self.perception());self.assertIn('ball',tracks);self.assertGreater(tracks['ball']['displacement'],.4);self.assertGreater(tracks['ball']['peakSpeed'],.3)
    def test_sports_shot_links_shooter_ball_keeper_and_success(self):
        audio={'words':[{'start':.55,'end':.8,'text':'shot','speaker':'A'},{'start':1,'end':1.2,'text':'goal','speaker':'A'}]};actions=build_action_intelligence('unused.mp4',self.perception(),audio,'/tmp/action-test.json');episode=actions['episodes'][0]
        self.assertEqual(episode['type'],'sports_shot');self.assertEqual(episode['outcome']['status'],'success');self.assertIn('shooter',episode['actorTrackIds']);self.assertIn('ball',episode['mustShowTrackIds']);self.assertIn('keeper',episode['targetTrackIds']);self.assertTrue(episode['keepContinuousAction'])
    def test_stationary_object_does_not_create_false_action(self):
        actions=build_action_intelligence('unused.mp4',self.perception(False),{'words':[]},'/tmp/action-still.json');self.assertEqual(actions['episodes'],[])
    def test_die_face_pips_are_counted_only_in_valid_range(self):
        image=np.full((180,180,3),245,dtype=np.uint8)
        for point in ((45,45),(90,90),(135,135)):cv2.circle(image,point,11,(10,10,10),-1)
        result=count_die_pips(image);self.assertIsNotNone(result);self.assertEqual(result['value'],3)
    def test_social_reaction_extends_required_coverage(self):
        actions={'episodes':[{'id':'a0','end':1,'mustShowTrackIds':['shooter','ball'],'reactionIds':[],'reactorTrackIds':[],'phases':{}}]};social={'reactions':[{'id':'r0','start':1.2,'end':1.8,'participants':['p1','p2']}]};attach_social_reactions(actions,social)
        self.assertEqual(actions['episodes'][0]['reactorTrackIds'],['p1','p2']);self.assertIn('p2',actions['episodes'][0]['mustShowTrackIds']);self.assertIn('reaction',actions['episodes'][0]['phases'])
    def test_stage_one_preserves_specialist_continuity_and_outcome(self):
        perception=self.perception();audio={'words':[],'text':''};active={'frames':[]};scenes=[{'id':0,'start':0,'end':2}];actions={'episodes':[{'id':'a0','start':.2,'end':1.2,'type':'sports_shot','actorTrackIds':['shooter'],'objectTrackIds':['ball'],'targetTrackIds':['keeper'],'reactorTrackIds':['p1'],'mustShowTrackIds':['shooter','ball','keeper','p1'],'outcome':{'status':'success','confidence':.9},'verification':{'verified':True}}]};evidence=build_evidence(perception,audio,active,scenes,2,actions=actions);event=_local_events(evidence)[0]
        self.assertEqual(event['type'],'sports_action');self.assertTrue(event['keepContinuousAction']);self.assertEqual(event['evidence']['actionEpisodeId'],'a0');self.assertIn('keeper',event['mustShowTrackIds'])
if __name__=='__main__':unittest.main()
