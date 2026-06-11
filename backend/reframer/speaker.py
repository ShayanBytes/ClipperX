"""
speaker.py - identity tracking, active-speaker selection, and joint-moment split.

Consumes per-frame face detections + scene cuts; produces a per-frame framing
*intent*: either FOCUS on one subject, or SPLIT between two people. The crop
planner turns these intents into actual (smoothed / snapped) crop boxes.

Active speaker = the tracked face whose mouth is *moving* (std-dev of mouth
openness over a short window). Hysteresis prevents flicker on rapid exchanges:
a challenger must lead for `speaker_switch_hold_frames` before we hard-cut to it.

Joint moment (-> split screen) = both top tracks "speaking" at once (laughing /
talking together), sustained for `joint_hold_frames`, with a separate release
debounce so it doesn't toggle.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

import numpy as np

from backend.models import FrameDetections, FramingKind, SceneMode

Target = Tuple[float, float, float, float]  # (cx, cy, w, h)

# per-frame velocity damping applied while a track is coasting (undetected)
_DR_DAMP = 0.85
# only believe a track's velocity if the detection gap that produced it was this small
_VEL_TRUST_GAP = 3
# velocity EMA weight (higher = smoother / laggier)
_VEL_SMOOTH = 0.6
# busy-ness rank: a higher rank = more people on screen (used by mode hysteresis)
_MODE_RANK = {SceneMode.HOLD: 0, SceneMode.SOLO: 1, SceneMode.DUAL: 2, SceneMode.GROUP: 3}


@dataclass
class FrameIntent:
    frame_num: int
    kind: FramingKind
    focus_target: Optional[Target] = None          # FOCUS: subject center (None = absent)
    split_targets: Optional[List[Target]] = None    # SPLIT: two targets, ordered left->right
    active_id: Optional[int] = None                  # which track is focused (for snap detection)
    is_cut: bool = False                             # True on the first frame of a new shot
    allow_snap: bool = False                         # camera may hard-jump (cut / deliberate switch / split)
    confidence: float = 1.0                          # 1.0 = fresh detection, decays while target is coasted
    mode: SceneMode = SceneMode.HOLD                 # committed scene mode this frame (L2)
    target_zoom: float = 1.0                          # requested crop scale (1.0 = base/widest; <1 = punch in)


@dataclass
class _Track:
    tid: int
    cx: float                           # best estimate fed to the planner (detected, or coasted)
    cy: float
    w: float
    h: float
    vx: float = 0.0                     # smoothed per-frame velocity (from clean detections only)
    vy: float = 0.0
    det_cx: float = 0.0                 # last ACTUALLY-detected position: the anchor we coast from
    det_cy: float = 0.0
    coast: int = 0                      # consecutive undetected frames since last detection
    mouth: Deque[float] = field(default_factory=lambda: deque(maxlen=64))
    last_seen: int = 0

    def speaking_score(self, window: int) -> float:
        if len(self.mouth) < 3:
            return 0.0
        vals = list(self.mouth)[-window:]
        return float(np.std(vals))


class SpeakerTracker:
    def __init__(self, config: dict, frame_width: int, frame_height: Optional[int] = None):
        self.cfg = config
        self.W = frame_width
        self.match_dist = config["track_match_max_dist_ratio"] * frame_width
        self.window = int(config["mouth_window_frames"])
        self.speak_thr = float(config["speaking_score_threshold"])
        self.switch_hold = int(config["speaker_switch_hold_frames"])
        self.both_thr = float(config["both_active_threshold"])
        self.joint_hold = int(config["joint_hold_frames"])
        self.joint_release = int(config["joint_release_frames"])
        self.recovery_decay = int(config.get("recovery_decay_frames", 24))
        self.drift_min_speed = float(config.get("recovery_min_drift_speed_px", 1.5))
        self.drift_max = float(config.get("recovery_max_drift_ratio", 0.05)) * frame_width
        self.mode_enter = int(config.get("mode_enter_frames", 18))
        self.mode_collapse = int(config.get("mode_collapse_frames", 36))
        self.two_shot_margin = float(config.get("two_shot_margin_ratio", 0.12))
        self.exchange_window = int(config.get("exchange_window_frames", 45))
        self.exchange_count = int(config.get("exchange_switch_count", 2))
        # emphasis punch-in (first consumer of the zoom primitive): a sustained solo shot
        # slowly pushes in. Dwell-based; resets to wide on cut / switch / mode change.
        self.emphasis_on = bool(config.get("emphasis_punch_in", True))
        self.emphasis_zoom = float(config.get("emphasis_zoom", 0.92))
        self.emphasis_after = int(config.get("emphasis_after_frames", 90))
        # keep a lost track alive long enough to coast it through the full decay window
        self.coast_frames = max(self.recovery_decay, self.window, 12)

        # Width of the 9:16 focus crop in SOURCE pixels - needed to decide whether two
        # heads can co-fit in one frame (two-shot) or must be stacked (split). Mirrors the
        # planner's geometry; falls back to a 16:9 estimate if height isn't supplied.
        out_w, out_h = config["output_width"], config["output_height"]
        H = frame_height if frame_height else int(round(frame_width * 9 / 16))
        cw = round(H * out_w / out_h)
        self.crop_w = float(min(cw, frame_width))

        self._tracks: List[_Track] = []
        self._next_id = 0
        # active-speaker hysteresis state
        self._active_id: Optional[int] = None
        self._cand_id: Optional[int] = None
        self._cand_streak = 0
        self._just_switched = False  # set for one frame when a deliberate hysteresis switch fires (-> snap)
        self._switch_frames: Deque[int] = deque(maxlen=32)  # recent switch times (rapid-exchange)
        # scene-mode state machine (L2)
        self._mode = SceneMode.HOLD
        self._pending_mode: Optional[SceneMode] = None
        self._pending_streak = 0
        # DUAL "show both" (two-shot / split) machine
        self._wide = False        # currently showing both (two-shot or split)
        self._wide_on = 0
        self._wide_off = 0
        self._cofit = False       # latched: the two heads fit in one crop (-> two-shot vs split)
        # emphasis punch-in dwell: frames the current subject has been held in SOLO focus
        self._focus_dwell = 0
        self._dwell_id: Optional[int] = None

    def run(self, frames: List[FrameDetections], scene_cuts: List[int]) -> List[FrameIntent]:
        cut_set = set(scene_cuts)
        intents: List[FrameIntent] = []
        for fd in frames:
            is_cut = fd.frame_num in cut_set
            if is_cut:
                self._reset_shot()
            self._update_tracks(fd)
            intents.append(self._decide(fd.frame_num, is_cut))
        return intents

    # ---- tracking ----
    def _reset_shot(self):
        self._tracks = []
        self._active_id = None
        self._cand_id = None
        self._cand_streak = 0
        self._mode = SceneMode.HOLD
        self._pending_mode = None
        self._pending_streak = 0
        self._switch_frames.clear()
        self._wide = False
        self._wide_on = 0
        self._wide_off = 0
        self._cofit = False

    def _update_tracks(self, fd: FrameDetections):
        # Greedy nearest-centroid matching of detections to existing tracks.
        unmatched = list(range(len(fd.faces)))
        used_tracks = set()
        pairs = []
        for di in unmatched:
            d = fd.faces[di]
            best_t, best_dist = None, self.match_dist
            for t in self._tracks:
                if t.tid in used_tracks:
                    continue
                dist = ((t.cx - d.cx) ** 2 + (t.cy - d.cy) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist, best_t = dist, t
            if best_t is not None:
                pairs.append((di, best_t))
                used_tracks.add(best_t.tid)

        matched_dets = set()
        for di, t in pairs:
            d = fd.faces[di]
            # Velocity is measured from the last DETECTED anchor over the actual gap, and
            # only trusted across short gaps. Measuring from t.cx (which may have been
            # coasted away) is what caused the crop to hunt - it fed its own error back in.
            gap = fd.frame_num - t.last_seen
            if 0 < gap <= _VEL_TRUST_GAP:
                inst_vx = (d.cx - t.det_cx) / gap
                inst_vy = (d.cy - t.det_cy) / gap
                t.vx = _VEL_SMOOTH * t.vx + (1.0 - _VEL_SMOOTH) * inst_vx
                t.vy = _VEL_SMOOTH * t.vy + (1.0 - _VEL_SMOOTH) * inst_vy
            else:
                t.vx = t.vy = 0.0  # lost too long: stale motion is not to be trusted
            t.det_cx, t.det_cy = d.cx, d.cy
            t.cx, t.cy, t.w, t.h = d.cx, d.cy, d.w, d.h
            t.mouth.append(d.mouth_open)
            t.coast = 0
            t.last_seen = fd.frame_num
            matched_dets.add(di)

        for di, d in enumerate(fd.faces):
            if di in matched_dets:
                continue
            self._tracks.append(_Track(
                tid=self._next_id, cx=d.cx, cy=d.cy, w=d.w, h=d.h,
                det_cx=d.cx, det_cy=d.cy, last_seen=fd.frame_num,
            ))
            self._tracks[-1].mouth.append(d.mouth_open)
            self._next_id += 1

        # Coast tracks that exist but weren't seen this frame. A near-stationary subject
        # is HELD at its last detected spot (no phantom wander); a genuinely-moving one is
        # extrapolated from that fixed anchor with a decelerating, hard-capped offset, so a
        # bad velocity guess can never snowball into the back-and-forth hunting we saw.
        for t in self._tracks:
            if t.last_seen == fd.frame_num:        # detected or freshly created this frame
                continue
            if fd.frame_num - t.last_seen > self.coast_frames:
                continue
            t.coast += 1
            speed = (t.vx * t.vx + t.vy * t.vy) ** 0.5
            if speed < self.drift_min_speed:
                t.cx, t.cy = t.det_cx, t.det_cy
                continue
            damp = _DR_DAMP ** t.coast
            dx = max(-self.drift_max, min(self.drift_max, t.vx * t.coast * damp))
            dy = max(-self.drift_max, min(self.drift_max, t.vy * t.coast * damp))
            t.cx, t.cy = t.det_cx + dx, t.det_cy + dy

        # drop stale tracks
        self._tracks = [t for t in self._tracks if fd.frame_num - t.last_seen <= self.coast_frames]

    def _confidence(self, t: _Track, frame_num: int) -> float:
        """1.0 while detected, decaying linearly to 0 across the recovery window."""
        if self.recovery_decay <= 0:
            return 1.0
        gap = frame_num - t.last_seen
        return max(0.0, 1.0 - gap / self.recovery_decay)

    # ---- scene-mode machine (L2) ----
    @staticmethod
    def _raw_mode(n_live: int) -> SceneMode:
        """The mode the current head-count implies, before hysteresis."""
        if n_live <= 0:
            return SceneMode.HOLD
        if n_live == 1:
            return SceneMode.SOLO
        if n_live == 2:
            return SceneMode.DUAL
        return SceneMode.GROUP

    def _commit_mode(self, raw: SceneMode, instant: bool) -> SceneMode:
        """Adopt `raw` through asymmetric hysteresis. `instant` (scene cut / appearing from
        an empty frame) commits immediately; otherwise a busier mode must persist
        `mode_enter` frames and a quieter one `mode_collapse` frames before we switch."""
        if instant or raw == self._mode or self._mode == SceneMode.HOLD:
            # cut, no change, or framing a subject the instant one appears
            self._mode = raw
            self._pending_mode, self._pending_streak = None, 0
            return self._mode

        if self._pending_mode != raw:
            self._pending_mode, self._pending_streak = raw, 1
        else:
            self._pending_streak += 1

        need = self.mode_enter if _MODE_RANK[raw] > _MODE_RANK[self._mode] else self.mode_collapse
        if self._pending_streak >= need:
            self._mode = raw
            self._pending_mode, self._pending_streak = None, 0
        return self._mode

    # ---- decision ----
    def _decide(self, frame_num: int, is_cut: bool) -> FrameIntent:
        self._just_switched = False
        live = [t for t in self._tracks if frame_num - t.last_seen <= self.coast_frames]

        # Classify the scene from CURRENTLY-DETECTED tracks only: coasting ghosts (a brief
        # flicker recovery keeps alive) must not vote DUAL, or a 4-frame intrusion that
        # out-lives the enter-dwell would flip the layout. Hysteresis covers real subjects'
        # single-frame detection gaps. Coasting tracks still drive the focus target below.
        detected = sum(1 for t in self._tracks if t.last_seen == frame_num)
        raw = self._raw_mode(detected)
        mode = self._commit_mode(raw, instant=is_cut or self._mode == SceneMode.HOLD)

        if not live:
            # HOLD: nobody to follow -> hold + drift (handled downstream). Easing back in
            # when a subject reappears is intentional; only a cut may snap from empty.
            self._reset_wide()
            return FrameIntent(frame_num, FramingKind.FOCUS, focus_target=None,
                               active_id=None, is_cut=is_cut, allow_snap=is_cut,
                               confidence=0.0, mode=SceneMode.HOLD)

        scored = sorted(live, key=lambda t: t.speaking_score(self.window), reverse=True)

        # ----- DUAL: show BOTH (two-shot if they co-fit, else split) or punch-in -----
        left_wide = False
        if mode == SceneMode.DUAL and len(scored) >= 2:
            was_wide = self._wide
            kind, focus_t, split_t = self._dual_framing(frame_num, scored)
            left_wide = was_wide and not self._wide
            if kind == "split":
                return FrameIntent(frame_num, FramingKind.SPLIT, split_targets=split_t,
                                   active_id=None, is_cut=is_cut, allow_snap=True,
                                   mode=SceneMode.DUAL)
            if kind == "two_shot":
                # Smooth pan into / within a two-shot (no snap); the midpoint eases.
                return FrameIntent(frame_num, FramingKind.FOCUS, focus_target=focus_t,
                                   active_id=None, is_cut=is_cut, allow_snap=is_cut,
                                   confidence=1.0, mode=SceneMode.DUAL)
            # kind == "punch" -> fall through to single-speaker focus
        else:
            # "show both" only exists inside DUAL; clear it so it can't linger
            if self._wide:
                left_wide = True
            self._reset_wide()

        # ----- SOLO / GROUP / DUAL-punch-in: follow one subject (the active speaker) -----
        # GROUP focuses the dominant speaker for now; centroid-fit is roadmap #6.
        active = self._select_active(frame_num, scored)
        t = next((x for x in live if x.tid == active), scored[0])
        # Snap on a cut, a deliberate speaker switch, or a hard cut from a two-shot to the
        # one person now talking. A re-acquired target after a dropout eases back smoothly.
        return FrameIntent(frame_num, FramingKind.FOCUS,
                           focus_target=(t.cx, t.cy, t.w, t.h),
                           active_id=t.tid, is_cut=is_cut,
                           allow_snap=(is_cut or self._just_switched or left_wide),
                           confidence=self._confidence(t, frame_num), mode=mode)

    def _reset_wide(self):
        self._wide = False
        self._wide_on = self._wide_off = 0

    def _rapid_exchange(self, frame_num: int) -> bool:
        """True when speakers have been trading lines fast (>= N switches in the window)."""
        while self._switch_frames and frame_num - self._switch_frames[0] > self.exchange_window:
            self._switch_frames.popleft()
        return len(self._switch_frames) >= self.exchange_count

    def _dual_framing(self, frame_num: int, scored: List[_Track]):
        """Decide the DUAL layout -> ('two_shot', focus_target, None) | ('split', None,
        split_targets) | ('punch', None, None). 'Show both' (two-shot/split) engages when
        both are talking or trading lines rapidly; two-shot vs split is set by whether the
        two heads can co-fit one crop (latched with hysteresis so it can't flicker)."""
        a, b = scored[0], scored[1]
        ax = a.det_cx if a.last_seen == frame_num else a.cx
        bx = b.det_cx if b.last_seen == frame_num else b.cx
        sep = abs(ax - bx)

        # latched co-fit: enter when they fit with margin, leave only once they exceed the
        # full crop width -> a dead-band that stops two-shot<->split flicker at the boundary
        margin = self.two_shot_margin * self.crop_w
        if not self._cofit and sep + 2.0 * margin <= self.crop_w:
            self._cofit = True
        elif self._cofit and sep > self.crop_w:
            self._cofit = False

        both = (a.speaking_score(self.window) >= self.both_thr
                and b.speaking_score(self.window) >= self.both_thr)
        want_wide = both or self._rapid_exchange(frame_num)
        if want_wide:
            self._wide_on += 1
            self._wide_off = 0
        else:
            self._wide_off += 1
            self._wide_on = 0
        if not self._wide and self._wide_on >= self.joint_hold:
            self._wide = True
        elif self._wide and self._wide_off >= self.joint_release:
            self._wide = False

        if not self._wide:
            return "punch", None, None
        if self._cofit:
            mx = (a.cx + b.cx) * 0.5
            my = (a.cy + b.cy) * 0.5
            w = sep + (a.w + b.w) * 0.5
            h = max(a.h, b.h)
            return "two_shot", (mx, my, w, h), None
        two = sorted((a, b), key=lambda t: t.cx)  # left -> right
        return "split", None, [(t.cx, t.cy, t.w, t.h) for t in two]

    def _select_active(self, frame_num: int, scored: List[_Track]) -> int:
        best = scored[0]
        # If no current active, or the active track has fully expired (coasted past the
        # recovery window), adopt the best WITHOUT flagging a switch: this is a recovery,
        # not a deliberate cut, so the camera should ease over - not snap.
        if self._active_id is None or all(t.tid != self._active_id for t in scored):
            self._active_id = best.tid
            self._cand_id, self._cand_streak = None, 0
            return self._active_id

        best_score = best.speaking_score(self.window)
        # only consider switching to a meaningfully-speaking challenger
        if best.tid != self._active_id and best_score >= self.speak_thr:
            if self._cand_id == best.tid:
                self._cand_streak += 1
            else:
                self._cand_id, self._cand_streak = best.tid, 1
            if self._cand_streak >= self.switch_hold:
                self._active_id = best.tid
                self._cand_id, self._cand_streak = None, 0
                self._just_switched = True  # deliberate, score-driven switch -> hard cut
                self._switch_frames.append(frame_num)  # feeds rapid-exchange -> two-shot
        else:
            self._cand_id, self._cand_streak = None, 0

        return self._active_id
