from __future__ import annotations
import json, math, os, tempfile, threading, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_dump_lock=threading.RLock()

def _replace_with_retry(source: str, target: Path) -> None:
    # Windows can briefly deny os.replace while Node, antivirus, or indexing has
    # the status file open. Retry the atomic rename instead of failing the job.
    delay=0.005
    for attempt in range(30):
        try:
            os.replace(source,target)
            return
        except PermissionError:
            if attempt == 29: raise
            time.sleep(delay)
            delay=min(0.1,delay*1.6)

def dump(path: str | Path, value: Any) -> None:
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    # One Python writer at a time plus a unique temp file keeps status JSON valid.
    # The atomic rename is retried for transient Windows file-sharing contention.
    with _dump_lock:
        fd,temp_name=tempfile.mkstemp(prefix=target.name+'.',suffix='.tmp',dir=str(target.parent))
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as handle:
                json.dump(value,handle,indent=2); handle.flush(); os.fsync(handle.fileno())
            _replace_with_retry(temp_name,target)
        finally:
            if os.path.exists(temp_name):
                for attempt in range(5):
                    try: os.unlink(temp_name); break
                    except PermissionError:
                        if attempt == 4: break
                        time.sleep(0.01*(attempt+1))

def load(path: str | Path, default=None):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError): return default

def clamp(v,lo,hi): return max(lo,min(hi,v))
def center(box): return ((box[0]+box[2])/2,(box[1]+box[3])/2)
def area(box): return max(0,box[2]-box[0])*max(0,box[3]-box[1])
def iou(a,b):
    x1,y1,x2,y2=max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3]); inter=max(0,x2-x1)*max(0,y2-y1)
    return inter/max(1e-9,area(a)+area(b)-inter)
def union_box(boxes):
    boxes=[b for b in boxes if b]
    return [min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)] if boxes else None

def cancelled(out_dir: str | Path) -> bool: return Path(out_dir,'CANCEL').exists()

def _utc():return datetime.now(timezone.utc).isoformat()

def start_run_log(out_dir,metadata=None):
    out=Path(out_dir);run_id=os.getenv('CLIPPERX_RUN_ID') or datetime.now(timezone.utc).strftime('run-%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6];folder=Path(os.getenv('CLIPPERX_LOG_DIR') or out/'logs'/run_id);folder.mkdir(parents=True,exist_ok=True);pointer={'runId':run_id,'folder':str(folder),'startedAt':_utc()};dump(out/'logs'/'current-run.json',pointer);dump(folder/'run-summary.json',{'schemaVersion':'1.0','status':'running',**pointer,'metadata':metadata or {},'events':0,'modelCalls':0});(folder/'events.jsonl').touch(exist_ok=True);(folder/'model-usage.jsonl').touch(exist_ok=True);return pointer

def _run_folder(out_dir):
    pointer=load(Path(out_dir)/'logs'/'current-run.json',{}) or {};folder=pointer.get('folder');return Path(folder) if folder else None

def log_event(out_dir,event,event_type='event'):
    folder=_run_folder(out_dir)
    if not folder:return
    row={'time':_utc(),'type':event_type,**(event if isinstance(event,dict) else {'message':str(event)})}
    with _dump_lock:
        with (folder/'events.jsonl').open('a',encoding='utf-8') as handle:handle.write(json.dumps(row,ensure_ascii=False)+'\n')

def log_model_use(out_dir,stage,provider,model,used,**details):
    folder=_run_folder(out_dir)
    if not folder:return
    row={'time':_utc(),'stage':stage,'provider':provider or None,'model':model or None,'used':bool(used),**details}
    with _dump_lock:
        with (folder/'model-usage.jsonl').open('a',encoding='utf-8') as handle:handle.write(json.dumps(row,ensure_ascii=False)+'\n')

def finish_run_log(out_dir,success=True,**details):
    folder=_run_folder(out_dir)
    if not folder:return
    previous=load(folder/'run-summary.json',{}) or {}
    with (folder/'events.jsonl').open(encoding='utf-8') as handle:events=sum(1 for _ in handle)
    with (folder/'model-usage.jsonl').open(encoding='utf-8') as handle:models=sum(1 for _ in handle)
    summary={**previous,'status':'complete' if success else 'failed','finishedAt':_utc(),'events':events,'modelCalls':models,**details};dump(folder/'run-summary.json',summary)
    lines=['ClipperX diagnostic summary',f"Run: {summary.get('runId','unknown')}",f"Status: {summary['status']}",f"Started: {summary.get('startedAt','unknown')}",f"Finished: {summary['finishedAt']}",f"Recorded events: {events}",f"AI model calls: {models}"]
    if summary.get('finalStage'):lines.append(f"Final stage: {summary['finalStage']}")
    if summary.get('error'):lines.append(f"Error: {summary['error']}")
    lines+=['','Share run-summary.json, model-usage.jsonl, events.jsonl, orchestrator-report.json, and the end of engine-console.log for diagnosis.','API keys and credentials are never written to these files.'];(folder/'SHARE-THIS-LOG.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')

def status(out_dir,stage,progress,**extra):
    value={'stage':stage,'progress':progress,'updatedAt':_utc(),**extra};dump(Path(out_dir,'status.json'),value);log_event(out_dir,value,'status')
