from __future__ import annotations
import cv2, math
from .common import center, dump, cancelled

IMPORTANT_CLASSES={'person','sports ball','cell phone','microphone','cup','bottle','book','laptop','chair'}

def analyze_video(video_path,out_path,out_dir,model_name='yolo11n.pt',analysis_fps=8.0,max_people=8):
    from ultralytics import YOLO
    model=YOLO(model_name);cap=cv2.VideoCapture(video_path);fps=cap.get(cv2.CAP_PROP_FPS) or 30;width,height=int(cap.get(3)),int(cap.get(4));every=max(1,round(fps/analysis_fps))
    frames=[];previous_centers={};smooth_boxes={};frame_no=0;face_detector=_face_detector();face_state={}
    while True:
        ok,frame=cap.read()
        if not ok:break
        if cancelled(out_dir):raise RuntimeError('Cancelled')
        if frame_no%every:frame_no+=1;continue
        timestamp=frame_no/fps;result=model.track(frame,persist=True,tracker='bytetrack.yaml',verbose=False,conf=.22,iou=.5,classes=None)[0];detections=[]
        if result.boxes is not None:
            ids=result.boxes.id.int().cpu().tolist() if result.boxes.id is not None else list(range(len(result.boxes)));boxes=result.boxes.xyxy.cpu().tolist();confs=result.boxes.conf.cpu().tolist();classes=result.boxes.cls.int().cpu().tolist();people=0
            for track,box,confidence,class_id in zip(ids,boxes,confs,classes):
                name=model.names[class_id]
                if name not in IMPORTANT_CLASSES and name!='person':continue
                if name=='person':
                    people+=1
                    if people>max_people:continue
                track=str(track);raw=[box[0]/width,box[1]/height,box[2]/width,box[3]/height];old_box=smooth_boxes.get(track,raw);raw_center=center(raw);old_center=center(old_box);movement=abs(raw_center[0]-old_center[0])+abs(raw_center[1]-old_center[1]);alpha=.62 if movement>.06 else .34
                smooth=[old_box[index]+(raw[index]-old_box[index])*alpha for index in range(4)];smooth_boxes[track]=smooth;current=center(smooth);old=previous_centers.get(track,current);velocity=[(current[0]-old[0])*analysis_fps,(current[1]-old[1])*analysis_fps];previous_centers[track]=current
                entry={'trackId':track,'class':name,'confidence':round(float(confidence),4),'box':[round(x,5) for x in smooth],'rawBox':[round(x,5) for x in raw],'velocity':[round(x,5) for x in velocity]}
                if name=='person':entry['appearance']=_appearance(frame,raw,width,height)
                detections.append(entry)
        faces=_detect_faces(face_detector,frame,width,height,detections,face_state)
        frames.append({'time':round(timestamp,4),'frame':frame_no,'detections':detections,'faces':faces});frame_no+=1
    cap.release();data={'source':video_path,'width':width,'height':height,'fps':fps,'analysisFps':analysis_fps,'frames':frames,'tracking':{'boxSmoothing':True,'mouthMotion':True}}
    dump(out_path,data);return data

def _appearance(frame,box,width,height):
    x1=max(0,int(box[0]*width));y1=max(0,int(box[1]*height));x2=min(width,int(box[2]*width));y2=min(height,int(box[3]*height))
    crop=frame[y1:y2,x1:x2]
    if crop.size==0:return []
    hsv=cv2.cvtColor(cv2.resize(crop,(48,96)),cv2.COLOR_BGR2HSV);hist=cv2.calcHist([hsv],[0,1],None,[8,4],[0,180,0,256]);hist=cv2.normalize(hist,hist).flatten()
    return [round(float(value),5) for value in hist]

def _face_detector():
    try:
        import mediapipe as mp
        return mp.solutions.face_detection.FaceDetection(model_selection=1,min_detection_confidence=.42)
    except Exception:return None

def _detect_faces(detector,frame,width,height,people,state):
    if detector is None:return []
    rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB);result=detector.process(rgb);faces=[]
    for index,detection in enumerate(result.detections or []):
        box_data=detection.location_data.relative_bounding_box;box=[max(0,box_data.xmin),max(0,box_data.ymin),min(1,box_data.xmin+box_data.width),min(1,box_data.ymin+box_data.height)];cx,cy=center(box);owner=None;best=1e9
        for person in people:
            if person['class']!='person':continue
            person_box=person['box']
            if person_box[0]<=cx<=person_box[2] and person_box[1]<=cy<=person_box[3]:
                distance=abs(cx-(person_box[0]+person_box[2])/2)+abs(cy-(person_box[1]+person_box[3])/2)
                if distance<best:best=distance;owner=person['trackId']
        mouth_motion=0.0
        if owner:
            x1=max(0,int(box[0]*width));x2=min(width,int(box[2]*width));y1=max(0,int((box[1]+(box[3]-box[1])*.48)*height));y2=min(height,int(box[3]*height))
            if x2>x1+3 and y2>y1+3:
                patch=cv2.cvtColor(frame[y1:y2,x1:x2],cv2.COLOR_BGR2GRAY);patch=cv2.resize(patch,(32,16));previous=state.get(owner)
                if previous is not None:mouth_motion=float(cv2.absdiff(patch,previous).mean()/255.0)
                state[owner]=patch
        keypoints=list(detection.location_data.relative_keypoints or []);head_yaw=0.0
        if len(keypoints)>=3:
            eye_mid=(keypoints[0].x+keypoints[1].x)/2;eye_distance=max(.01,abs(keypoints[0].x-keypoints[1].x));head_yaw=max(-1,min(1,(keypoints[2].x-eye_mid)/eye_distance))
        faces.append({'faceId':f'f{index}','personTrackId':owner,'box':[round(x,5) for x in box],'confidence':round(float(detection.score[0]),4),'mouthMotion':round(mouth_motion,5),'headYaw':round(head_yaw,4)})
    return faces
