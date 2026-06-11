"""
detector.py - per-frame person detection + mouth-openness + motion.

Uses MediaPipe Tasks (the only API available in mediapipe 0.10.x on Python 3.13;
the legacy `mp.solutions` API is gone):

  * PoseLandmarker drives FRAMING. It finds the whole person and works at any
    distance, including wide stage / full-body shots where face detection fails
    (which is exactly where 0.2 broke). The framing target is the head: nose if
    visible, else the shoulder midpoint.

  * FaceLandmarker provides the ACTIVE-SPEAKER signal via the `jawOpen` blendshape.
    It's only run when 2+ people are on screen (single-person never needs it), and
    each detected face is matched to the nearest person so its mouth motion can be
    attributed to that track.

One pass also computes a cheap motion centroid per frame, used as a fallback
framing target when nobody is detected (subject stepped out to show something).
"""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

from backend.models import Detection, FrameDetections, VideoMeta

# Pose landmark indices (MediaPipe 33-point model)
_NOSE = 0
_L_SHOULDER = 11
_R_SHOULDER = 12
# Head landmarks (nose, both eyes, both ears, both mouth corners). The framing anchor is
# their visibility-WEIGHTED mean, not a single point: it doesn't flicker the way a lone
# nose does (which teleports when its visibility crosses a threshold at distance), and it
# stays near the true head centre in profile, where the nose juts to one side.
_HEAD_IDS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)


class FaceAnalyzer:
    def __init__(self, config: dict):
        self.cfg = config
        self.max_people = int(config.get("max_people", 3))
        self.match_dist_ratio = float(config.get("face_match_dist_ratio", 0.15))

        self._pose = mp_vision.PoseLandmarker.create_from_options(
            mp_vision.PoseLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=config["pose_model"]),
                running_mode=mp_vision.RunningMode.VIDEO,
                num_poses=self.max_people,
                min_pose_detection_confidence=float(config["min_pose_confidence"]),
                min_tracking_confidence=float(config["min_tracking_confidence"]),
            )
        )
        self._face = None  # lazily created the first time 2+ people appear

    def _ensure_face(self):
        if self._face is None:
            self._face = mp_vision.FaceLandmarker.create_from_options(
                mp_vision.FaceLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=self.cfg["face_model"]),
                    running_mode=mp_vision.RunningMode.VIDEO,
                    num_faces=self.max_people,
                    output_face_blendshapes=True,
                    min_face_detection_confidence=float(self.cfg["min_face_confidence"]),
                    min_tracking_confidence=float(self.cfg["min_tracking_confidence"]),
                )
            )
        return self._face

    def analyze(
        self,
        meta: VideoMeta,
        progress_cb: Optional[Callable[[float, str], None]] = None,
    ) -> Tuple[List[FrameDetections], List[Optional[Tuple[float, float]]]]:
        cap = cv2.VideoCapture(meta.path)
        W, H = meta.width, meta.height
        fps = meta.fps if meta.fps > 0 else 30.0

        detections: List[FrameDetections] = []
        motion: List[Optional[Tuple[float, float]]] = []
        prev_gray = None
        frame_num = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
            ts = int(frame_num * 1000.0 / fps)

            pose_res = self._pose.detect_for_video(mp_img, ts)
            people = [self._person_from_pose(lms, W, H) for lms in pose_res.pose_landmarks]

            # mouth signal only matters (and only works) with 2+ people
            if len(people) >= 2:
                self._attach_mouth(mp_img, ts, people, W)

            detections.append(FrameDetections(frame_num=frame_num, faces=people))

            small = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            motion.append(self._motion_centroid(prev_gray, gray, W, H))
            prev_gray = gray

            frame_num += 1
            if progress_cb and meta.total_frames > 0 and frame_num % 15 == 0:
                progress_cb(frame_num / meta.total_frames, "Analyzing")

        cap.release()
        return detections, motion

    def _person_from_pose(self, lms, W: int, H: int) -> Detection:
        # Framing anchor = visibility-weighted mean of the head landmarks. Smoothly
        # follows the head as it turns (no nose<->shoulder teleport), and stays centred
        # in profile. Falls back to shoulder midpoint, then raw nose, only if no head
        # landmark is visible at all.
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

    def _attach_mouth(self, mp_img, ts: int, people: List[Detection], W: int):
        face = self._ensure_face()
        res = face.detect_for_video(mp_img, ts)
        if not res.face_landmarks:
            return
        max_dist = self.match_dist_ratio * W
        for i, fl in enumerate(res.face_landmarks):
            xs = [p.x for p in fl]
            ys = [p.y for p in fl]
            fcx = (min(xs) + max(xs)) * 0.5 * W
            fcy = (min(ys) + max(ys)) * 0.5 * H
            jaw = 0.0
            if res.face_blendshapes and i < len(res.face_blendshapes):
                for c in res.face_blendshapes[i]:
                    if c.category_name == "jawOpen":
                        jaw = float(c.score)
                        break
            # attach to nearest person
            best, best_d = None, max_dist
            for person in people:
                d = ((person.cx - fcx) ** 2 + (person.cy - fcy) ** 2) ** 0.5
                if d < best_d:
                    best_d, best = d, person
            if best is not None:
                best.mouth_open = max(best.mouth_open, jaw)

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
        for obj in (self._pose, self._face):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass

    def __del__(self):
        self.close()
