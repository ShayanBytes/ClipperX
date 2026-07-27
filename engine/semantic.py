from __future__ import annotations
import base64,json,urllib.request
from pathlib import Path
import cv2,numpy as np
from .common import dump

WINDOW_SECONDS=9.0

def _nearest_frame(perception,t):
    frames=perception.get('frames',[])
    return min(frames,key=lambda frame:abs(frame['time']-t)) if frames else {'detections':[]}

def _annotate(frame,row):
    height,width=frame.shape[:2]
    colors={'person':(60,230,255),'sports ball':(50,80,255)}
    for detection in row.get('detections',[]):
        x1,y1,x2,y2=detection['box'];p1=(int(x1*width),int(y1*height));p2=(int(x2*width),int(y2*height));color=colors.get(detection.get('class'),(170,255,110))
        cv2.rectangle(frame,p1,p2,color,2);label=('P' if detection.get('class')=='person' else 'O')+str(detection['trackId'])
        cv2.putText(frame,label,(p1[0],max(14,p1[1]-4)),cv2.FONT_HERSHEY_SIMPLEX,.48,color,2,cv2.LINE_AA)
    return frame

def analyze_semantics(video_path,scenes,perception,out_dir,provider=None,model=None,api_key=None,base_url=None,audio=None,active=None):
    if not (provider and model and api_key):return {}
    cap=cv2.VideoCapture(video_path);result={}
    for scene in scenes:
        combined=[];window_start=scene['start'];window_index=0
        while window_start<scene['end']-.05:
            window_end=min(scene['end'],window_start+WINDOW_SECONDS);times=[float(t) for t in np.linspace(window_start,max(window_start,window_end-.04),12)];samples=[];visible=set()
            for timestamp in times:
                cap.set(cv2.CAP_PROP_POS_MSEC,timestamp*1000);ok,frame=cap.read()
                if not ok:continue
                frame=cv2.resize(frame,(400,225));row=_nearest_frame(perception,timestamp)
                visible.update(str(item['trackId']) for item in row.get('detections',[]));samples.append(_annotate(frame,row))
            if samples:
                while len(samples)<12:samples.append(samples[-1].copy())
                sheet=np.vstack([np.hstack(samples[index:index+4]) for index in range(0,12,4)]);path=Path(out_dir,f"semantic-scene-{scene['id']}-window-{window_index}.jpg");cv2.imwrite(str(path),sheet)
                words=[word for word in (audio or {}).get('words',[]) if window_start<=word.get('start',-1)<window_end]
                hints=[{'time':row['time'],'trackId':row.get('personTrackId'),'confidence':row.get('confidence',0)} for row in (active or {}).get('frames',[]) if window_start<=row.get('time',-1)<window_end and row.get('personTrackId')]
                context={'windowStart':round(window_start,3),'windowEnd':round(window_end,3),'sampleTimes':[round(t,3) for t in times],'visibleTrackIds':sorted(visible),'timedTranscript':[{'start':word.get('start'),'end':word.get('end'),'text':word.get('text')} for word in words],'activeSpeakerHints':hints[::max(1,len(hints)//18)]}
                try:
                    answer=_call(provider,model,api_key,base_url,base64.b64encode(path.read_bytes()).decode(),context)
                    for beat in answer.get('storyBeats',answer.get('beats',[])):
                        beat=dict(beat);start=float(beat.get('relativeStart',beat.get('start',0)));end=float(beat.get('relativeEnd',beat.get('end',window_end-window_start)))
                        if start<window_start-.01:start+=window_start
                        if end<=window_end-window_start+.01:end+=window_start
                        beat['start']=max(window_start,start);beat['end']=min(window_end,end);combined.append(beat)
                except Exception as exc:
                    combined.append({'start':window_start,'end':window_end,'compositionMode':'wide','confidence':0.0,'reason':f'Semantic provider failed: {exc}'})
            window_start=window_end;window_index+=1
        result[str(scene['id'])]={'storyBeats':combined,'confidence':round(sum(float(x.get('confidence',0)) for x in combined)/max(1,len(combined)),3)}
    cap.release();dump(Path(out_dir,'semantic.json'),result);return result

def _call(provider,model,key,base,image,context):
    prompt=f'''You are a senior documentary and short-form video editor. Analyze this chronological 4x3 contact sheet. Boxes labeled P are tracked people; O are tracked objects. Context: {json.dumps(context)}.
Return JSON only with storyBeats. Each beat must include relativeStart, relativeEnd, eventType, compositionMode (single|pair|group|action|wide), primaryTrackId, requiredTrackIds, cameraPolicy (locked|wide_static|action_follow|follow_slow), confidence, reason, and optional focusPoint [normalized source x,y].
Editing rules: follow setup -> action -> outcome -> reaction; identify who rolls/throws/shoots and whether the result must stay visible; use transcript and activeSpeakerHints to time speaker cuts; use a direct cut when the speaker changes instead of panning between faces; hold one composition at least 1.2 seconds; keep 3-6 person conversations stable; during fast action include actor, object trajectory, target/outcome; never invent a track ID not shown. Labels add P/O only for display: if the image says P17 or O4, return raw IDs "17" or "4". Prefer calm intentional coverage over constant movement.'''
    if provider=='gemini':
        url='/'.join(['https:','','generativelanguage.googleapis.com','v1beta','models',model+':generateContent'])+'?key='+key
        body={'contents':[{'parts':[{'text':prompt},{'inline_data':{'mime_type':'image/jpeg','data':image}}]}],'generationConfig':{'responseMimeType':'application/json','temperature':.05}};headers={}
    else:
        root=(base or ('https://openrouter.ai/api/v1' if provider=='openrouter' else 'https://api.openai.com/v1')).rstrip('/');url=root+'/chat/completions';headers={'Authorization':'Bearer '+key}
        body={'model':model,'temperature':.05,'response_format':{'type':'json_object'},'messages':[{'role':'user','content':[{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+image}}]}]}
    request=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**headers},method='POST')
    with urllib.request.urlopen(request,timeout=60) as response:data=json.loads(response.read())
    text=data['candidates'][0]['content']['parts'][0]['text'] if provider=='gemini' else data['choices'][0]['message']['content'];text=text.strip().removeprefix('```json').removesuffix('```').strip();return json.loads(text)
