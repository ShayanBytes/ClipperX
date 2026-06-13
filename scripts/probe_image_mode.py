"""IMAGE-mode probe: run pose + face detection with FRESH full detection on every frame
(no VIDEO tracking that clings to one subject). Tests whether the under-detection is a
tracking artifact or a true detector limit. Reaction segment only by default.

Usage: python scripts/probe_image_mode.py <video> [start] [end]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2, numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from config import CONFIG

inp = sys.argv[1]
start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
end = int(sys.argv[3]) if len(sys.argv) > 3 else 30

def mk_pose(conf):
    return mp_vision.PoseLandmarker.create_from_options(mp_vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=CONFIG["pose_model"]),
        running_mode=mp_vision.RunningMode.IMAGE, num_poses=6,
        min_pose_detection_confidence=conf))

def mk_face(conf):
    return mp_vision.FaceLandmarker.create_from_options(mp_vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=CONFIG["face_model"]),
        running_mode=mp_vision.RunningMode.IMAGE, num_faces=6,
        min_face_detection_confidence=conf))

pose = mk_pose(0.4)
face_hi = mk_face(0.4)
face_lo = mk_face(0.2)

cap = cv2.VideoCapture(inp)
print(f"{'frame':>5} {'pose':>4} {'face@.4':>7} {'face@.2':>7}  face_sizes(%W)")
cap.set(cv2.CAP_PROP_POS_FRAMES, start)
for n in range(start, end):
    ret, frame = cap.read()
    if not ret:
        break
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
    npose = len(pose.detect(img).pose_landmarks)
    fr = face_hi.detect(img)
    flo = face_lo.detect(img)
    sizes = []
    for fl in fr.face_landmarks:
        xs = [p.x for p in fl]
        sizes.append(f"{100*(max(xs)-min(xs)):.0f}")
    print(f"{n:>5} {npose:>4} {len(fr.face_landmarks):>7} {len(flo.face_landmarks):>7}  {','.join(sizes)}")
cap.release()
