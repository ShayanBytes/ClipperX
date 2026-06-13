"""One-off probe: compare what PoseLandmarker vs FaceLandmarker detect, frame by frame,
on a clip — to test the hypothesis that face detection finds the reacting people that pose
misses. Prints per-frame counts and the jawOpen of each detected face.

Usage: python scripts/probe_detectors.py <video> [max_frames]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2, numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from config import CONFIG

inp = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10**9

pose = mp_vision.PoseLandmarker.create_from_options(mp_vision.PoseLandmarkerOptions(
    base_options=mp_python.BaseOptions(model_asset_path=CONFIG["pose_model"]),
    running_mode=mp_vision.RunningMode.VIDEO, num_poses=4,
    min_pose_detection_confidence=0.4, min_tracking_confidence=0.4))
face = mp_vision.FaceLandmarker.create_from_options(mp_vision.FaceLandmarkerOptions(
    base_options=mp_python.BaseOptions(model_asset_path=CONFIG["face_model"]),
    running_mode=mp_vision.RunningMode.VIDEO, num_faces=6,
    output_face_blendshapes=True,
    min_face_detection_confidence=0.4, min_tracking_confidence=0.4))

cap = cv2.VideoCapture(inp)
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"{os.path.basename(inp)}: {W}x{H} @ {fps:.0f}fps")
print(f"{'frame':>5} {'pose':>4} {'face':>4}  face_sizes(%W)        jawOpen")
n = 0
pose_tot = face_tot = 0
while n < limit:
    ret, frame = cap.read()
    if not ret:
        break
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
    ts = int(n * 1000.0 / fps)
    pr = pose.detect_for_video(img, ts)
    fr = face.detect_for_video(img, ts)
    npose = len(pr.pose_landmarks)
    nface = len(fr.face_landmarks)
    pose_tot += npose; face_tot += nface
    sizes, jaws = [], []
    for i, fl in enumerate(fr.face_landmarks):
        xs = [p.x for p in fl]; ys = [p.y for p in fl]
        sizes.append(f"{100*(max(xs)-min(xs)):.0f}")
        jw = 0.0
        if fr.face_blendshapes and i < len(fr.face_blendshapes):
            for c in fr.face_blendshapes[i]:
                if c.category_name == "jawOpen":
                    jw = c.score; break
        jaws.append(f"{jw:.2f}")
    if n % 2 == 0:
        print(f"{n:>5} {npose:>4} {nface:>4}  {','.join(sizes):<20} {','.join(jaws)}")
    n += 1
cap.release()
print(f"\nTotals over {n} frames: pose={pose_tot} ({pose_tot/n:.2f}/frame), "
      f"face={face_tot} ({face_tot/n:.2f}/frame)")
