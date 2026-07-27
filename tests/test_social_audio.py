import math,tempfile,unittest,wave
from pathlib import Path
import numpy as np
from engine.social_audio import acoustic_timeline,build_utterances,add_prosody,conversation_edges,diarization_overlaps,detect_reactions,joke_chains,attach_visible_people

class SocialAudioTests(unittest.TestCase):
    def words(self):
        return [{'start':0,'end':.45,'text':'Why did the chicken','speaker':'A'},{'start':.46,'end':.9,'text':'cross the road?','speaker':'A'},{'start':.78,'end':1.2,'text':'Because it was funny','speaker':'B'}]
    def test_pitch_energy_and_rhythm_are_extracted_locally(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tone.wav';rate=16000;t=np.arange(rate)/rate;signal=(np.sin(2*math.pi*220*t)*12000).astype('<i2')
            with wave.open(str(path),'wb') as target:target.setnchannels(1);target.setsampwidth(2);target.setframerate(rate);target.writeframes(signal.tobytes())
            timeline=acoustic_timeline(path);pitches=[row['pitch'] for row in timeline if row['pitch']>0]
        self.assertGreater(len(timeline),10);self.assertAlmostEqual(sorted(pitches)[len(pitches)//2],220,delta=12)
    def test_speaker_overlap_becomes_an_interruption_edge(self):
        utterances=build_utterances(self.words());edges=conversation_edges(utterances)
        self.assertEqual(len(utterances),2);self.assertTrue(any(edge['type']=='interrupts' for edge in edges))
    def test_raw_diarization_overlap_is_preserved(self):
        overlaps=diarization_overlaps([{'start':0,'end':1,'speaker':'A'},{'start':.7,'end':1.4,'speaker':'B'}])
        self.assertEqual(overlaps[0]['speakers'],['A','B']);self.assertAlmostEqual(overlaps[0]['duration'],.3)
    def test_visual_and_transcript_laughter_form_one_group_reaction(self):
        audio={'words':[{'start':1,'end':1.25,'text':'hahaha','speaker':'B'}]};perception={'frames':[{'time':1.1,'faces':[{'personTrackId':'p1','mouthMotion':.03},{'personTrackId':'p2','mouthMotion':.04}]}]}
        reactions=detect_reactions(audio,perception,[])
        self.assertEqual(len(reactions),1);self.assertTrue(reactions[0]['groupReaction']);self.assertEqual(set(reactions[0]['participants']),{'p1','p2'});self.assertIn('transcript',reactions[0]['sources'])
    def test_joke_setup_is_linked_to_reaction_payoff(self):
        utterances=build_utterances(self.words()[:2]);reactions=[{'id':'r0','start':1.1,'end':1.5,'confidence':.85}];chains=joke_chains(utterances,reactions)
        self.assertEqual(chains[0]['setupUtteranceId'],'u0');self.assertEqual(chains[0]['reactionId'],'r0')
    def test_voice_turn_is_attached_to_visible_persistent_person(self):
        social={'utterances':[{'id':'u0','start':0,'end':1,'speaker':'A'}]};active={'mapping':{},'frames':[{'time':.2,'personTrackId':'person-002'},{'time':.5,'personTrackId':'person-002'}]}
        attach_visible_people(social,active);self.assertEqual(social['utterances'][0]['personTrackId'],'person-002');self.assertEqual(social['speakerPersonMap']['A'],'person-002')
if __name__=='__main__':unittest.main()
