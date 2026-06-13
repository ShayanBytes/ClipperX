"""Decisive probe: YuNet (cv2.FaceDetectorYN) face count per frame, vs the MediaPipe results.
Detects at a downscaled width for speed, scales boxes back. Prints count + sizes + scores.

Usage: python scripts/probe_yunet.py <video> [start] [end] [det_width] [conf]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2, numpy as np

inp = sys.argv[1]
start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
end = int(sys.argv[3]) if len(sys.argv) > 3 else 30
det_w = int(sys.argv[4]) if len(sys.argv) > 4 else 1280
conf = float(sys.argv[5]) if len(sys.argv) > 5 else 0.6

cap = cv2.VideoCapture(inp)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
scale = det_w / W
dh = int(round(H * scale))
det = cv2.FaceDetectorYN.create("models/face_detection_yunet_2023mar.onnx", "", (det_w, dh),
                                score_threshold=conf)
print(f"{os.path.basename(inp)}: {W}x{H} -> detect at {det_w}x{dh}, conf>={conf}")
print(f"{'frame':>5} {'nface':>5}  faces: x%,size%W,score")
cap.set(cv2.CAP_PROP_POS_FRAMES, start)
counts = []
for n in range(start, end):
    ret, frame = cap.read()
    if not ret:
        break
    small = cv2.resize(frame, (det_w, dh))
    _, faces = det.detect(small)
    rows = []
    if faces is not None:
        for f in faces:
            x, y, w, h = f[:4]
            rows.append(f"({100*x/det_w:.0f}%,{100*w/det_w:.0f},{f[-1]:.2f})")
    counts.append(0 if faces is None else len(faces))
    print(f"{n:>5} {counts[-1]:>5}  {' '.join(rows)}")
cap.release()
c = np.array(counts)
print(f"\nover {len(c)} frames: mean={c.mean():.2f}  max={c.max()}  "
      f">=2 in {100*(c>=2).mean():.0f}% frames  >=3 in {100*(c>=3).mean():.0f}%  >=4 in {100*(c>=4).mean():.0f}%")
