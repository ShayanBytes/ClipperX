"""
detector.py - per-frame face detection + per-face mouth (jaw) + motion centroid.

PRIMARY detector = YuNet (`cv2.FaceDetectorYN`, shipped in opencv-contrib). It finds ALL
visible faces every frame, returning a box + 5 landmarks + a confidence score. This replaced
MediaPipe PoseLandmarker, which under-detected catastrophically on reaction shots (it needs a
torso; in close reaction framing bodies are cropped off, so it found 1 of 2 obvious faces).
YuNet finds them rock-solid. Faces are the subject in reaction content, so they drive framing.

  * YuNet  -> who/where: a `Detection` (box centre + size) per face, capped at `max_people`.
  * FaceLandmarker (MediaPipe) -> the jawOpen "mouth motion" signal, now run PER FACE CROP
    (only on faces big enough to landmark). This is no longer gated behind a 2+ pose count —
    that gating is exactly why the mouth signal was dead before.
  * PoseLandmarker -> FALLBACK only: on frames where YuNet finds no face (everyone turned
    away / distant body shot) we fall back to a single pose so wide shots still track.

One pass also computes a cheap motion centroid per frame, used as a fallback framing target
when nobody is detected (subject stepped out to show something).
"""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

from backend.models import Detection, FrameDetections, VideoMeta

# Pose landmark indices (MediaPipe 33-point model) - used only on the no-face fallback path.
_NOSE = 0
_L_SHOULDER = 11
_R_SHOULDER = 12
_HEAD_IDS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)


class FaceAnalyzer:
    def __init__(self, config: dict):
        self.cfg = config
        self.max_people = int(config.get("max_people", 4))
        self.det_width = int(config.get("det_width", 1280))
        self.min_face_score = float(config.get("min_face_score", 0.6))
        self.pose_fallback = bool(config.get("pose_fallback", True))
        self.jaw_on_crop = bool(config.get("jaw_on_crop", True))
        self.jaw_min_px = float(config.get("jaw_min_face_px", 90))

        # YuNet is created lazily in analyze(), once we know the frame size (its input size must
        # match the (downscaled) frame we feed it). model + thresholds captured here.
        self._yunet = None
        self._face = None   # MediaPipe FaceLandmarker (IMAGE mode), lazily, for per-crop jawOpen
        self._pose = None   # MediaPipe PoseLandmarker (IMAGE mode), lazily, for the no-face fallback

    # ---- lazy model builders ----
    def _ensure_yunet(self, det_w: int, det_h: int):
        if self._yunet is None:
            self._yunet = cv2.FaceDetectorYN.create(
                self.cfg["face_detector_model"], "", (det_w, det_h),
                score_threshold=self.min_face_score,
            )
        return self._yunet

    def _ensure_face(self):
        if self._face is None:
            self._face = mp_vision.FaceLandmarker.create_from_options(
                mp_vision.FaceLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=self.cfg["face_model"]),
                    running_mode=mp_vision.RunningMode.IMAGE,
                    num_faces=1,
                    output_face_blendshapes=True,
                    min_face_detection_confidence=float(self.cfg["min_face_confidence"]),
                )
            )
        return self._face

    def _ensure_pose(self):
        if self._pose is None:
            self._pose = mp_vision.PoseLandmarker.create_from_options(
                mp_vision.PoseLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=self.cfg["pose_model"]),
                    running_mode=mp_vision.RunningMode.IMAGE,
                    num_poses=1,
                    min_pose_detection_confidence=float(self.cfg["min_pose_confidence"]),
                )
            )
        return self._pose

    def analyze(
        self,
        meta: VideoMeta,
        progress_cb: Optional[Callable[[float, str], None]] = None,
    ) -> Tuple[List[FrameDetections], List[Optional[Tuple[float, float]]]]:
        cap = cv2.VideoCapture(meta.path)
        W, H = meta.width, meta.height

        # YuNet detects on a copy downscaled to det_width (faster; boxes scaled back to source).
        det_w = min(self.det_width, W)
        scale = det_w / W
        det_h = max(1, int(round(H * scale)))
        yunet = self._ensure_yunet(det_w, det_h)
        yunet.setInputSize((det_w, det_h))
        inv = 1.0 / scale

        detections: List[FrameDetections] = []
        motion: List[Optional[Tuple[float, float]]] = []
        prev_gray = None
        prev_det_gray = None
        frame_num = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            small = cv2.resize(frame, (det_w, det_h))
            det_gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            _, faces = yunet.detect(small)
            people = self._people_from_yunet(faces, inv, frame, det_gray, prev_det_gray, W, H)
            prev_det_gray = det_gray

            if not people and self.pose_fallback:
                people = self._people_from_pose(frame, W, H)

            detections.append(FrameDetections(frame_num=frame_num, faces=people))

            small_g = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            gray = cv2.cvtColor(small_g, cv2.COLOR_BGR2GRAY)
            motion.append(self._motion_centroid(prev_gray, gray, W, H))
            prev_gray = gray

            frame_num += 1
            if progress_cb and meta.total_frames > 0 and frame_num % 15 == 0:
                progress_cb(frame_num / meta.total_frames, "Analyzing")

        cap.release()
        return detections, motion

    def _people_from_yunet(self, faces, inv: float, frame, det_gray, prev_det_gray,
                           W: int, H: int) -> List[Detection]:
        if faces is None or len(faces) == 0:
            return []
        # rows: [x, y, w, h, 5x(lmx,lmy), score]; strongest first
        rows = sorted(faces, key=lambda f: float(f[-1]), reverse=True)
        # DEDUP: YuNet can double-detect one face (e.g. a hand splitting it into two partials),
        # which would invent a phantom extra "reactor". Drop a box whose centre sits within
        # ~0.6*size of an already-kept, higher-score box. Real distinct faces are far apart.
        kept = []
        for f in rows:
            dx, dy, dw, dh = float(f[0]), float(f[1]), float(f[2]), float(f[3])
            cxd, cyd = dx + dw / 2, dy + dh / 2
            dup = False
            for g in kept:
                gx, gy, gw, gh = float(g[0]), float(g[1]), float(g[2]), float(g[3])
                dist = ((cxd - (gx + gw / 2)) ** 2 + (cyd - (gy + gh / 2)) ** 2) ** 0.5
                if dist < 0.6 * max(dw, dh, gw, gh):
                    dup = True
                    break
            if not dup:
                kept.append(f)
            if len(kept) >= self.max_people:
                break

        people: List[Detection] = []
        for f in kept:
            dx, dy, dw, dh = float(f[0]), float(f[1]), float(f[2]), float(f[3])
            x, y, w, h = dx * inv, dy * inv, dw * inv, dh * inv
            cx = x + w / 2.0
            cy = y + h / 2.0
            react = self._appearance(det_gray, prev_det_gray, dx, dy, dw, dh)
            jaw = 0.0
            if self.jaw_on_crop and w >= self.jaw_min_px:
                jaw = self._jaw_from_crop(frame, x, y, w, h, W, H)
            people.append(Detection(cx=cx, cy=cy, w=max(40.0, w), h=max(40.0, h),
                                    mouth_open=jaw, react=react))
        return people

    @staticmethod
    def _appearance(det_gray, prev_det_gray, x: float, y: float, w: float, h: float,
                    size: int = 48) -> float:
        """Per-face reaction cue: mean abs pixel change of the face region since last frame,
        normalised 0..1. A laughing / talking / expressive face changes a lot in place; a static
        onlooker barely changes. Computed at detection resolution (cheap)."""
        if prev_det_gray is None:
            return 0.0
        gh, gw = det_gray.shape[:2]
        x0 = max(0, int(x)); y0 = max(0, int(y))
        x1 = min(gw, int(x + w)); y1 = min(gh, int(y + h))
        if x1 - x0 < 6 or y1 - y0 < 6:
            return 0.0
        cur = cv2.resize(det_gray[y0:y1, x0:x1], (size, size))
        prv = cv2.resize(prev_det_gray[y0:y1, x0:x1], (size, size))
        return float(np.mean(cv2.absdiff(cur, prv))) / 255.0

    def _jaw_from_crop(self, frame, x: float, y: float, w: float, h: float, W: int, H: int) -> float:
        # Pad the face box (jaw/expression needs chin + brow), clamp, hand the crop to the
        # FaceLandmarker. Big, isolated faces are exactly where the landmarker is reliable.
        pad_x = 0.35 * w
        pad_y = 0.45 * h
        x0 = int(max(0, x - pad_x))
        y0 = int(max(0, y - pad_y))
        x1 = int(min(W, x + w + pad_x))
        y1 = int(min(H, y + h + pad_y))
        if x1 - x0 < 16 or y1 - y0 < 16:
            return 0.0
        crop = frame[y0:y1, x0:x1]
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        try:
            res = self._ensure_face().detect(mp_img)
        except Exception:
            return 0.0
        if res.face_blendshapes:
            for c in res.face_blendshapes[0]:
                if c.category_name == "jawOpen":
                    return float(c.score)
        return 0.0

    def _people_from_pose(self, frame, W: int, H: int) -> List[Detection]:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        try:
            res = self._ensure_pose().detect(mp_img)
        except Exception:
            return []
        return [self._person_from_pose(lms, W, H) for lms in res.pose_landmarks]

    def _person_from_pose(self, lms, W: int, H: int) -> Detection:
        # Framing anchor = visibility-weighted mean of the head landmarks (smooth, stays centred
        # in profile). Falls back to shoulder midpoint, then raw nose. (Fallback path only.)
        sx = sy = wsum = 0.0
        for idx in _HEAD_IDS:
            lm = lms[idx]
            if lm.visibility > 0.3:
                sx += lm.x * lm.visibility
                sy += lm.y * lm.visibility
                wsum += lm.visibility
        if wsum > 0.0:
            cx, cy = (sx / wsum) * W, (sy / wsum) * H
        else:
            ls, rs = lms[_L_SHOULDER], lms[_R_SHOULDER]
            if ls.visibility > 0.3 and rs.visibility > 0.3:
                cx, cy = (ls.x + rs.x) * 0.5 * W, (ls.y + rs.y) * 0.5 * H
            else:
                cx, cy = lms[_NOSE].x * W, lms[_NOSE].y * H

        xs = [lm.x for lm in lms if lm.visibility > 0.3]
        ys = [lm.y for lm in lms if lm.visibility > 0.3]
        if xs and ys:
            bw = (max(xs) - min(xs)) * W
            bh = (max(ys) - min(ys)) * H
        else:
            bw, bh = 0.2 * W, 0.4 * H
        return Detection(cx=cx, cy=cy, w=max(40.0, bw), h=max(40.0, bh), mouth_open=0.0)

    def _motion_centroid(self, prev_gray, gray, W, H) -> Optional[Tuple[float, float]]:
        if prev_gray is None or prev_gray.shape != gray.shape:
            return None
        diff = cv2.absdiff(prev_gray, gray)
        _, mask = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
        m = cv2.moments(mask, binaryImage=True)
        if m["m00"] < 200:
            return None
        sx = W / gray.shape[1]
        sy = H / gray.shape[0]
        return (m["m10"] / m["m00"] * sx, m["m01"] / m["m00"] * sy)

    def close(self):
        for obj in (self._face, self._pose):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass

    def __del__(self):
        self.close()
