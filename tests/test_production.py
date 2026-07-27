import json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from engine.production import select_runtime_profile,input_fingerprint,resource_budget,ProductionRuntime,redact,write_crash_report

class ProductionHardeningTests(unittest.TestCase):
    def config(self,profile='Podcast'):return {'profile':profile,'model':'yolo11n.pt','whisperModel':'base','language':None,'analysisFps':8,'maxPeople':8,'width':1080,'height':1920,'noSubtitles':False,'provider':'','apiModel':'','apiKeyHash':'','correctionsHash':None,'semanticHash':None}
    def source(self,folder):path=Path(folder)/'input.mp4';path.write_bytes((b'clipperx-production-fixture'*5000));return path
    def test_low_resource_machine_selects_eco_profile(self):
        profile=select_runtime_profile({'cpuCount':4,'memoryGb':6,'gpu':{'available':False,'memoryGb':0}});self.assertEqual(profile['name'],'eco');self.assertFalse(profile['openVocabulary']);self.assertLessEqual(profile['analysisFps'],4)
    def test_capable_gpu_selects_accelerated_profile(self):
        profile=select_runtime_profile({'cpuCount':12,'memoryGb':32,'gpu':{'available':True,'memoryGb':8}});self.assertEqual(profile['name'],'accelerated');self.assertGreaterEqual(profile['analysisFps'],10)
    def test_input_fingerprint_changes_when_source_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            source=self.source(folder);first=input_fingerprint(source);source.write_bytes(source.read_bytes()+b'change');second=input_fingerprint(source)
        self.assertNotEqual(first['contentHash'],second['contentHash']);self.assertNotEqual(first['size'],second['size'])
    def test_resource_guard_rejects_insufficient_free_space(self):
        with tempfile.TemporaryDirectory() as folder:
            source=self.source(folder);budget=resource_budget(source,folder,free_bytes=10)
        self.assertFalse(budget['ok']);self.assertGreater(budget['requiredBytes'],budget['freeBytes'])
    def test_checkpoint_restores_only_verified_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            source=self.source(folder);out=Path(folder)/'out';runtime=ProductionRuntime(source,out,self.config());artifact=out/'stage.json';artifact.write_text('{"ok":true}');runtime.mark('stage',['stage.json']);same=ProductionRuntime(source,out,self.config());self.assertTrue(same.restore('stage',['stage.json']));artifact.write_text('{"ok":false}');self.assertFalse(same.restore('stage',['stage.json']))
    def test_configuration_change_invalidates_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            source=self.source(folder);out=Path(folder)/'out';first=ProductionRuntime(source,out,self.config());(out/'stage.json').write_text('{}');first.mark('stage',['stage.json']);second=ProductionRuntime(source,out,self.config('Sports'))
        self.assertFalse(second.restore('stage',['stage.json']))
    def test_secret_redaction_and_recoverable_crash_report(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'CLIPPERX_API_KEY':'secret-key-value'}):
            report=write_crash_report(folder,'provider rejected secret-key-value','trace secret-key-value');saved=json.loads((Path(folder)/'crash-report.json').read_text())
        self.assertNotIn('secret-key-value',json.dumps(saved));self.assertTrue(report['recoverable'])
    def test_strict_privacy_cleanup_removes_review_and_temporary_media(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'CLIPPERX_PRIVACY_MODE':'strict','CLIPPERX_KEEP_INTERMEDIATES':'0'}):
            source=self.source(folder);out=Path(folder)/'out';runtime=ProductionRuntime(source,out,self.config());(out/'audio.wav').write_bytes(b'a');(out/'quality-contact-sheet.jpg').write_bytes(b'b');(out/'stage3-pass1-silent.mp4').write_bytes(b'c');report=runtime.finalize()
            self.assertFalse((out/'audio.wav').exists());self.assertFalse((out/'quality-contact-sheet.jpg').exists());self.assertFalse((out/'stage3-pass1-silent.mp4').exists());self.assertTrue((out/'performance-report.json').exists());self.assertEqual(report['privacyMode'],'strict')
    def test_auto_tune_never_increases_requested_laptop_load(self):
        with tempfile.TemporaryDirectory() as folder:
            source=self.source(folder);runtime=ProductionRuntime(source,Path(folder)/'out',self.config());runtime.profile={'name':'eco','analysisFps':4,'maxPeople':6,'whisperModel':'tiny','yoloModel':'yolo11n.pt','openVocabulary':False,'workerThreads':2,'estimatedMemoryGb':3.5};args=SimpleNamespace(analysis_fps=8,max_people=8,whisper_model='base');runtime.apply_profile(args)
        self.assertEqual(args.analysis_fps,4);self.assertEqual(args.max_people,6);self.assertEqual(args.whisper_model,'tiny')
if __name__=='__main__':unittest.main()
