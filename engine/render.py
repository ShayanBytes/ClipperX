from __future__ import annotations
import cv2, subprocess
from pathlib import Path
from .crop import interpolate
from .common import clamp, cancelled

def render_dynamic(video_path,keyframes,out_path,out_dir,subtitle_path=None,width=1080,height=1920,progress_callback=None):
    out_dir=Path(out_dir).resolve(); out_dir.mkdir(parents=True,exist_ok=True)
    cap=cv2.VideoCapture(video_path); fps=cap.get(cv2.CAP_PROP_FPS) or 30; sw,sh=int(cap.get(3)),int(cap.get(4)); total=max(1,int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1))
    if sw<=0 or sh<=0: raise RuntimeError('Could not read source video dimensions')
    temp=out_dir/'video_silent.mp4'; writer=cv2.VideoWriter(str(temp),cv2.VideoWriter_fourcc(*'mp4v'),fps,(width,height))
    if not writer.isOpened(): raise RuntimeError('Could not open temporary video writer')
    keys=keyframes['keyframes']; n=0
    while True:
        ok,frame=cap.read()
        if not ok: break
        if cancelled(out_dir): cap.release(); writer.release(); raise RuntimeError('Cancelled')
        k=interpolate(keys,n/fps); cw=max(2,int(k['cropWidth']*sw)//2*2); ch=max(2,int(k['cropHeight']*sh)//2*2)
        cw=min(cw,sw-(sw%2)); ch=min(ch,sh-(sh%2)); cx=int(k['centerX']*sw); cy=int(k['centerY']*sh)
        x=int(clamp(cx-cw/2,0,sw-cw)); y=int(clamp(cy-ch/2,0,sh-ch)); crop=frame[y:y+ch,x:x+cw]
        if crop.size==0: raise RuntimeError(f'Invalid crop at frame {n}')
        writer.write(cv2.resize(crop,(width,height),interpolation=cv2.INTER_LANCZOS4)); n+=1
        if progress_callback and (n==1 or n%max(1,int(fps*2))==0): progress_callback(min(0.92,n/total))
    cap.release(); writer.release()
    # Use a relative ASS filename and cwd. This avoids Windows drive-letter colons
    # being parsed by FFmpeg as the filter's original_size option.
    if progress_callback: progress_callback(0.94)
    cmd=['ffmpeg','-y','-i',temp.name,'-i',str(Path(video_path).resolve())]
    ass=Path(subtitle_path).resolve() if subtitle_path else None
    if ass and ass.exists():
        local_ass=out_dir/'subtitles.ass'
        if ass != local_ass and not local_ass.exists(): local_ass.write_bytes(ass.read_bytes())
        cmd += ['-vf','ass=filename=subtitles.ass']
    cmd += ['-map','0:v','-map','1:a?','-c:v','libx264','-preset','veryfast','-crf','22','-c:a','aac','-shortest','-movflags','+faststart',str(Path(out_path).resolve())]
    result=subprocess.run(cmd,cwd=str(out_dir),capture_output=True,text=True)
    if result.returncode!=0:
        useful='\n'.join((result.stderr or '').splitlines()[-12:])
        raise RuntimeError('Final FFmpeg render failed. '+useful)
    if progress_callback: progress_callback(1.0)
    return {'path':str(Path(out_path).resolve()),'frames':n,'fps':fps,'width':width,'height':height}
