from __future__ import annotations
import hashlib,json,os,platform,shutil,subprocess,time,traceback as traceback_module
from pathlib import Path
from .common import dump,load

SCHEMA_VERSION='1.8'

def _memory_gb():
    try:
        if os.name=='nt':
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):_fields_=[('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),('ullAvailExtendedVirtual',ctypes.c_ulonglong)]
            status=MEMORYSTATUSEX();status.dwLength=ctypes.sizeof(status);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status));return status.ullTotalPhys/(1024**3)
        return os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')/(1024**3)
    except Exception:return 8.0

def _gpu_info():
    try:
        result=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3)
        if result.returncode==0 and result.stdout.strip():
            name,memory=[part.strip() for part in result.stdout.splitlines()[0].split(',',1)];return {'available':True,'name':name,'memoryGb':round(float(memory)/1024,2),'backend':'cuda'}
    except Exception:pass
    try:
        import cv2
        count=cv2.cuda.getCudaEnabledDeviceCount()
        if count:return {'available':True,'name':'OpenCV CUDA device','memoryGb':None,'backend':'cuda'}
    except Exception:pass
    return {'available':False,'name':None,'memoryGb':0,'backend':'cpu'}

def detect_hardware(path=None):
    target=Path(path or '.').resolve();disk=shutil.disk_usage(target);return {'platform':platform.system(),'release':platform.release(),'architecture':platform.machine(),'python':platform.python_version(),'cpuCount':os.cpu_count() or 1,'memoryGb':round(_memory_gb(),2),'gpu':_gpu_info(),'diskFreeGb':round(disk.free/(1024**3),2)}

def select_runtime_profile(hardware):
    cpu=int(hardware.get('cpuCount',1));memory=float(hardware.get('memoryGb',8));gpu=hardware.get('gpu',{});gpu_memory=float(gpu.get('memoryGb') or 0)
    if memory<7 or cpu<=4:return {'name':'eco','analysisFps':4.0,'maxPeople':6,'whisperModel':'tiny','yoloModel':'yolo11n.pt','openVocabulary':False,'workerThreads':max(1,min(2,cpu-1)),'estimatedMemoryGb':3.5}
    if gpu.get('available') and gpu_memory>=6 and memory>=16:return {'name':'accelerated','analysisFps':10.0,'maxPeople':10,'whisperModel':'small','yoloModel':'yolo11s.pt','openVocabulary':True,'workerThreads':max(2,min(8,cpu-2)),'estimatedMemoryGb':8.0}
    if memory>=16 and cpu>=8:return {'name':'quality','analysisFps':8.0,'maxPeople':8,'whisperModel':'base','yoloModel':'yolo11n.pt','openVocabulary':True,'workerThreads':max(2,min(6,cpu-2)),'estimatedMemoryGb':6.0}
    return {'name':'balanced','analysisFps':6.0,'maxPeople':8,'whisperModel':'base','yoloModel':'yolo11n.pt','openVocabulary':False,'workerThreads':max(1,min(4,cpu-1)),'estimatedMemoryGb':4.5}

def _file_hash(path):
    path=Path(path);digest=hashlib.sha256();size=path.stat().st_size
    with path.open('rb') as handle:
        digest.update(handle.read(1024*1024))
        if size>1024*1024:handle.seek(max(0,size-1024*1024));digest.update(handle.read(1024*1024))
    digest.update(str(size).encode());return digest.hexdigest()

def input_fingerprint(path):
    target=Path(path).resolve();return {'path':str(target),'size':target.stat().st_size,'mtimeNs':target.stat().st_mtime_ns,'contentHash':_file_hash(target)}

def _config_hash(config):return hashlib.sha256(json.dumps(config,sort_keys=True,default=str).encode()).hexdigest()

def redact(text,secrets=None):
    result=str(text or '')
    for secret in list(secrets or [])+[os.getenv('CLIPPERX_API_KEY',''),os.getenv('HF_TOKEN','')]:
        if secret and len(secret)>=6:result=result.replace(secret,'[REDACTED]')
    return result

def resource_budget(input_path,out_dir,width=1080,height=1920,free_bytes=None):
    source=Path(input_path);free=free_bytes if free_bytes is not None else shutil.disk_usage(Path(out_dir).resolve()).free;required=max(750*1024**2,int(source.stat().st_size*3.2)+int(width*height*12));return {'freeBytes':int(free),'requiredBytes':required,'ok':free>=required,'freeGb':round(free/(1024**3),2),'requiredGb':round(required/(1024**3),2)}

class ProductionRuntime:
    def __init__(self,input_path,out_dir,config):
        self.input_path=Path(input_path).resolve();self.out_dir=Path(out_dir);self.out_dir.mkdir(parents=True,exist_ok=True);self.hardware=detect_hardware(self.out_dir);self.profile=select_runtime_profile(self.hardware);self.config=config;self.fingerprint=input_fingerprint(self.input_path);self.run_key=_config_hash({'schema':SCHEMA_VERSION,'input':self.fingerprint,'config':config,'profile':self.profile['name']});self.path=self.out_dir/'runtime-checkpoints.json';existing=load(self.path,{}) or {};self.checkpoints=existing.get('checkpoints',{}) if existing.get('runKey')==self.run_key else {};self.started=time.monotonic();self.stage_starts={};self.timings=[];self.resumed=[];self.privacyMode=os.getenv('CLIPPERX_PRIVACY_MODE','local').lower();self.budget=resource_budget(self.input_path,self.out_dir,config.get('width',1080),config.get('height',1920));
        stale=self.out_dir/'CANCEL'
        if stale.exists():stale.unlink()
        threads=str(self.profile['workerThreads']);os.environ.setdefault('OMP_NUM_THREADS',threads);os.environ.setdefault('MKL_NUM_THREADS',threads);os.environ.setdefault('OPENBLAS_NUM_THREADS',threads);os.environ.setdefault('NUMEXPR_NUM_THREADS',threads)
        if not self.budget['ok']:raise RuntimeError(f"Insufficient disk space. ClipperX needs about {self.budget['requiredGb']} GB free but found {self.budget['freeGb']} GB.")
        self._save()
    def _save(self):dump(self.path,{'schemaVersion':SCHEMA_VERSION,'runKey':self.run_key,'input':self.fingerprint,'configHash':_config_hash(self.config),'profile':self.profile,'checkpoints':self.checkpoints,'updatedAt':time.time()})
    def begin(self,name):self.stage_starts[name]=time.monotonic()
    def end(self,name,resumed=False):
        duration=time.monotonic()-self.stage_starts.pop(name,time.monotonic());self.timings.append({'stage':name,'seconds':round(duration,3),'resumed':resumed})
        if resumed:self.resumed.append(name)
    def restore(self,name,files):
        record=self.checkpoints.get(name)
        if not record:return False
        for relative in files:
            path=self.out_dir/relative;expected=record.get('files',{}).get(relative)
            if not path.exists() or not expected:return False
            try:
                if path.stat().st_size!=expected['size'] or _file_hash(path)!=expected['hash']:return False
                if path.suffix=='.json' and load(path,None) is None:return False
            except OSError:return False
        return True
    def mark(self,name,files):
        signatures={}
        for relative in files:
            path=self.out_dir/relative
            if path.exists():signatures[relative]={'size':path.stat().st_size,'hash':_file_hash(path)}
        self.checkpoints[name]={'files':signatures,'completedAt':time.time()};self._save()
    def apply_profile(self,args):
        auto=os.getenv('CLIPPERX_AUTO_TUNE','1').lower() not in ('0','false','off');allow_heavy=os.getenv('CLIPPERX_ALLOW_HEAVY_MODELS','0').lower() in ('1','true','yes')
        if auto:
            args.analysis_fps=min(float(args.analysis_fps),self.profile['analysisFps']);args.max_people=min(int(args.max_people),self.profile['maxPeople'])
            if self.profile['name']=='eco' and args.whisper_model=='base':args.whisper_model='tiny'
            elif allow_heavy and args.whisper_model=='base':args.whisper_model=self.profile['whisperModel']
            if allow_heavy and getattr(args,'model','yolo11n.pt')=='yolo11n.pt':args.model=self.profile['yoloModel']
            if not self.profile['openVocabulary']:os.environ.setdefault('CLIPPERX_OPEN_VOCAB','0')
        self.profile['effectiveAnalysisFps']=float(args.analysis_fps);self.profile['effectiveMaxPeople']=int(args.max_people);self.profile['effectiveWhisperModel']=args.whisper_model;self.profile['effectiveYoloModel']=getattr(args,'model',self.profile['yoloModel'])
        return args
    def finalize(self,success=True):
        report={'schemaVersion':SCHEMA_VERSION,'stage':'stage-9-production-hardening','success':success,'hardware':self.hardware,'runtimeProfile':self.profile,'resourceBudget':self.budget,'privacyMode':self.privacyMode,'resumedCheckpoints':self.resumed,'timings':self.timings,'totalSeconds':round(time.monotonic()-self.started,3),'checkpointRunKey':self.run_key[:16]};dump(self.out_dir/'performance-report.json',report);self.cleanup();return report
    def cleanup(self):
        keep=os.getenv('CLIPPERX_KEEP_INTERMEDIATES','0').lower() in ('1','true','yes')
        if not keep:
            for pattern in ('stage3-*-silent.mp4','stage8-corrected-silent.mp4'):
                for path in self.out_dir.glob(pattern):
                    try:path.unlink()
                    except OSError:pass
        if self.privacyMode=='strict':
            for name in ('quality-contact-sheet.jpg','audio.wav'):
                try:(self.out_dir/name).unlink()
                except OSError:pass

def runtime_config(args):
    correction=Path(args.corrections) if getattr(args,'corrections',None) else None;semantic=Path(args.semantic) if getattr(args,'semantic',None) else None
    return {'profile':args.profile,'model':args.model,'whisperModel':args.whisper_model,'language':args.language,'analysisFps':args.analysis_fps,'maxPeople':args.max_people,'width':args.width,'height':args.height,'noSubtitles':args.no_subtitles,'provider':os.getenv('CLIPPERX_PROVIDER',''),'apiModel':os.getenv('CLIPPERX_MODEL',''),'apiKeyHash':hashlib.sha256(os.getenv('CLIPPERX_API_KEY','').encode()).hexdigest()[:16],'correctionsHash':_file_hash(correction) if correction and correction.exists() else None,'semanticHash':_file_hash(semantic) if semantic and semantic.exists() else None}

def write_crash_report(out_dir,error,traceback_text=None):
    report={'stage':'stage-9-crash-recovery','error':redact(error),'traceback':redact(traceback_text or traceback_module.format_exc()),'recoverable':True,'instruction':'Run the same project again. Verified checkpoints will be reused.','createdAt':time.time()};dump(Path(out_dir)/'crash-report.json',report);return report
