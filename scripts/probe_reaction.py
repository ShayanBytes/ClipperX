"""Measure a candidate REACTION signal: per-face appearance motion (how much each detected
face's pixels change frame-to-frame), alongside head translation. Tells us whether a 2nd
reactor (e.g. a laugher with a still head) is separable from a static onlooker BEFORE we
wire the signal into the engine.

Usage: python scripts/probe_reaction.py <video> [start] [end] [det_width]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2, numpy as np

inp = sys.argv[1]
start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
end = int(sys.argv[3]) if len(sys.argv) > 3 else 27
det_w = int(sys.argv[4]) if len(sys.argv) > 4 else 1920

cap = cv2.VideoCapture(inp)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
scale = det_w / W; det_h = int(round(H * scale))
det = cv2.FaceDetectorYN.create("models/face_detection_yunet_2023mar.onnx", "", (det_w, det_h),
                                score_threshold=0.6)

def face_patch(gray, x, y, w, h, size=48):
    x0 = max(0, int(x)); y0 = max(0, int(y))
    x1 = min(gray.shape[1], int(x + w)); y1 = min(gray.shape[0], int(y + h))
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    return cv2.resize(gray[y0:y1, x0:x1], (size, size))

cap.set(cv2.CAP_PROP_POS_FRAMES, start)
prev = {}   # match by nearest center to last frame's faces -> crude per-face id
print(f"{'frame':>5}  per-face: x%  appear(0-1)  headspd(%W)")
for n in range(start, end):
    ret, frame = cap.read()
    if not ret:
        break
    small = cv2.resize(frame, (det_w, det_h))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    _, faces = det.detect(small)
    rows = []
    cur = {}
    if faces is not None:
        for f in sorted(faces, key=lambda r: r[0]):  # left->right
            x, y, w, h = f[:4]
            cxp = 100 * (x + w / 2) / det_w
            patch = face_patch(gray, x, y, w, h)
            # nearest previous face by x
            key = min(prev.keys(), key=lambda k: abs(k - cxp), default=None)
            appear = 0.0; spd = 0.0
            if key is not None and abs(key - cxp) < 8:
                pp, px = prev[key]
                if patch is not None and pp is not None:
                    appear = float(np.mean(cv2.absdiff(patch, pp))) / 255.0
                spd = abs(cxp - key) / 100.0
            cur[cxp] = (patch, cxp)
            rows.append(f"x={cxp:4.0f} app={appear:.3f} spd={spd:.3f}")
    prev = cur
    print(f"{n:>5}  " + " | ".join(rows))
cap.release()
