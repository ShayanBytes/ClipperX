"""
speaker.py - identity tracking, reaction scoring, and the "show every reactor" layout.

Consumes per-frame face detections + scene cuts; produces a per-frame framing *intent*:
FOCUS on one subject, or SPLIT across 2-4 people. The crop planner turns these into boxes.

The core decision is REACTION-COUNT driven (this is the 4-person fix):

  reaction_score(track) = jaw-motion std (mouth) + head/box MOTION. On reaction footage the
  mouth signal is often weak (faces turned, hands over mouth), so motion is the spine — a
  "reaction" is visible movement (laugh / shout / gesture / lean), not lip-sync.

  Each track latches a REACTING state with hold/release hysteresis. Then, by how many people
  are reacting at once (R):
    * R >= 3 -> SPLIT into a grid (3 = two-on-top + one wide; 4 = 2x2 quad), one reactor / cell.
    * R == 2 -> two-shot (one crop, if they co-fit) else a 2-way split.
    * R == 1 -> punch in on that single reactor (a reaction cut).
    * R == 0 -> calm follow of the primary subject, or (in a 3+ scene) the group centroid-fit.

This replaces the old "always pick ONE dominant reactor" GROUP logic (which dropped the other
reactors) and the jaw-only DUAL "show both" gate (which never fired when mouths were occluded).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

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
    split_targets: Optional[List[Target]] = None    # SPLIT: 2-4 targets, slot order (left->right)
    active_id: Optional[int] = None                  # which track is focused (for snap detection)
    is_cut: bool = False                             # True on the first frame of a new shot
    allow_snap: bool = False                         # camera may hard-jump (cut / switch / split)
    confidence: float = 1.0                          # 1.0 = fresh detection, decays while coasted
    mode: SceneMode = SceneMode.HOLD                 # committed scene mode this frame (L2)
    target_zoom: float = 1.0                          # requested crop scale (1.0 = base/widest)


@dataclass
class _Track:
    tid: int
    cx: float
    cy: float
    w: float
    h: float
    vx: float = 0.0
    vy: float = 0.0
    det_cx: float = 0.0
    det_cy: float = 0.0
    coast: int = 0
    mouth: Deque[float] = field(default_factory=lambda: deque(maxlen=64))
    react: Deque[float] = field(default_factory=lambda: deque(maxlen=64))
    last_seen: int = 0

    def speaking_score(self, window: int) -> float:
        if len(self.mouth) < 3:
            return 0.0
        vals = list(self.mouth)[-window:]
        return float(np.std(vals))

    def react_level(self, window: int) -> float:
        """Recent mean of the per-face appearance-motion cue (the reaction spine)."""
        if not self.react:
            return 0.0
        return float(np.mean(list(self.react)[-window:]))


class SpeakerTracker:
    def __init__(self, config: dict, frame_width: int, frame_height: Optional[int] = None):
        self.cfg = config
        self.W = frame_width
        self.match_dist = config["track_match_max_dist_ratio"] * frame_width
        self.window = int(config["mouth_window_frames"])
        self.speak_thr = float(config["speaking_score_threshold"])
        self.switch_hold = int(config["speaker_switch_hold_frames"])
        self.recovery_decay = int(config.get("recovery_decay_frames", 24))
        self.drift_min_speed = float(config.get("recovery_min_drift_speed_px", 1.5))
        self.drift_max = float(config.get("recovery_max_drift_ratio", 0.05)) * frame_width
        self.mode_enter = int(config.get("mode_enter_frames", 18))
        self.mode_collapse = int(config.get("mode_collapse_frames", 36))
        self.mode_hc_window = max(1, int(config.get("mode_headcount_window", 12)))
        self.two_shot_margin = float(config.get("two_shot_margin_ratio", 0.12))
        # emphasis punch-in (sustained solo shot slowly pushes in)
        self.emphasis_on = bool(config.get("emphasis_punch_in", True))
        self.emphasis_zoom = float(config.get("emphasis_zoom", 0.92))
        self.emphasis_after = int(config.get("emphasis_after_frames", 90))
        # GROUP centroid-fit (nobody reacting): margin around the hull + a floor so we never over-crop
        self.group_margin = float(config.get("group_fit_margin_ratio", 0.12))
        self.group_min_zoom = float(config.get("group_min_zoom", 0.80))
        # single-reactor punch-in (R==1 in a 3+ scene): tighter framing, re-enables vertical comp
        self.group_dom_on = bool(config.get("group_dominant_focus", True))
        self.group_dom_zoom = float(config.get("group_dominant_zoom", 0.72))
        self.group_motion_w = float(config.get("group_motion_weight", 1.0))
        # === reaction-count layout (show every reactor) ===
        self.react_w = float(config.get("reaction_appearance_weight", 1.0))
        self.react_thr = float(config.get("reaction_threshold", 0.012))
        self.react_hold = int(config.get("reaction_hold_frames", 8))
        self.react_release = int(config.get("reaction_release_frames", 18))
        self.max_cells = max(2, int(config.get("max_split_cells", 4)))
        # keep a lost track alive long enough to coast it through the full decay window
        self.coast_frames = max(self.recovery_decay, self.window, 12)
        # layout stability: retain a lost grid-reactor's cell, and only shrink the cell count slowly
        self.react_grid_hold = max(self.coast_frames, int(config.get("react_grid_hold_frames", 45)))
        self.layout_shrink = max(1, int(config.get("react_layout_shrink_frames", 30)))

        # Width of the 9:16 focus crop in SOURCE pixels - decides whether two heads co-fit one
        # frame (two-shot) or must be split. Mirrors the planner's geometry.
        out_w, out_h = config["output_width"], config["output_height"]
        H = frame_height if frame_height else int(round(frame_width * 9 / 16))
        cw = round(H * out_w / out_h)
        self.crop_w = float(min(cw, frame_width))

        self._tracks: List[_Track] = []
        self._next_id = 0
        # active-speaker hysteresis state (single-subject focus)
        self._active_id: Optional[int] = None
        self._cand_id: Optional[int] = None
        self._cand_streak = 0
        self._just_switched = False
        # scene-mode state machine (L2) - kept for reporting + emphasis gating
        self._mode = SceneMode.HOLD
        self._pending_mode: Optional[SceneMode] = None
        self._pending_streak = 0
        # emphasis punch-in dwell
        self._focus_dwell = 0
        self._dwell_id: Optional[int] = None
        # per-track REACTING latch (tid -> state), and the two-shot co-fit latch
        self._reacting: Dict[int, bool] = {}
        self._react_on: Dict[int, int] = {}
        self._react_off: Dict[int, int] = {}
        self._cofit = False
        self._prev_split_n = 0          # how many cells we showed last frame (snap on change)
        # committed displayed cell-count (layout hysteresis: grow fast, shrink slow)
        self._shown_n = 0
        self._shrink_cand: Optional[int] = None
        self._shrink_streak = 0

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
        self._focus_dwell = 0
        self._dwell_id = None
        self._reacting = {}
        self._react_on = {}
        self._react_off = {}
        self._cofit = False
        self._prev_split_n = 0
        self._shown_n = 0
        self._shrink_cand = None
        self._shrink_streak = 0

    def _retention(self, t: "_Track") -> int:
        """How many frames a track is kept alive after its last detection. A latched grid-reactor
        gets a longer leash (react_grid_hold) so a brief detection blink doesn't drop their cell
        and reshuffle the grid; everyone else uses the normal recovery coast window."""
        return self.react_grid_hold if self._reacting.get(t.tid, False) else self.coast_frames

    def _update_tracks(self, fd: FrameDetections):
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
            gap = fd.frame_num - t.last_seen
            if 0 < gap <= _VEL_TRUST_GAP:
                inst_vx = (d.cx - t.det_cx) / gap
                inst_vy = (d.cy - t.det_cy) / gap
                t.vx = _VEL_SMOOTH * t.vx + (1.0 - _VEL_SMOOTH) * inst_vx
                t.vy = _VEL_SMOOTH * t.vy + (1.0 - _VEL_SMOOTH) * inst_vy
            else:
                t.vx = t.vy = 0.0
            t.det_cx, t.det_cy = d.cx, d.cy
            t.cx, t.cy, t.w, t.h = d.cx, d.cy, d.w, d.h
            t.mouth.append(d.mouth_open)
            t.react.append(d.react)
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
            self._tracks[-1].react.append(d.react)
            self._next_id += 1

        for t in self._tracks:
            if t.last_seen == fd.frame_num:
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

        self._tracks = [t for t in self._tracks
                        if fd.frame_num - t.last_seen <= self._retention(t)]
        live_ids = {t.tid for t in self._tracks}
        for d in (self._reacting, self._react_on, self._react_off):
            for tid in list(d.keys()):
                if tid not in live_ids:
                    del d[tid]

    def _confidence(self, t: _Track, frame_num: int) -> float:
        if self.recovery_decay <= 0:
            return 1.0
        gap = frame_num - t.last_seen
        return max(0.0, 1.0 - gap / self.recovery_decay)

    # ---- scene-mode machine (L2) ----
    @staticmethod
    def _raw_mode(n_live: int) -> SceneMode:
        if n_live <= 0:
            return SceneMode.HOLD
        if n_live == 1:
            return SceneMode.SOLO
        if n_live == 2:
            return SceneMode.DUAL
        return SceneMode.GROUP

    def _commit_mode(self, raw: SceneMode, instant: bool) -> SceneMode:
        if instant or raw == self._mode or self._mode == SceneMode.HOLD:
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

    # ---- reaction scoring ----
    def reaction_score(self, t: _Track) -> float:
        """How strongly a track is reacting. APPEARANCE motion (face pixels changing in place -
        laugh / talk / expression) is the spine; jaw-motion std and head translation are added
        bonuses where they survive. Measured: reactors ~0.025-0.05, static onlookers ~0.003."""
        score = self.react_w * t.react_level(self.window)
        score += t.speaking_score(self.window)
        if self.group_motion_w > 0.0:
            speed = (t.vx * t.vx + t.vy * t.vy) ** 0.5
            score += self.group_motion_w * (speed / self.W)
        return score

    def _update_reacting(self, frame_num: int, live: List[_Track]) -> List[_Track]:
        """Update each live track's latched REACTING state (hold to engage, release to drop) and
        return the reacting tracks, strongest first, capped at max_cells."""
        reacting: List[_Track] = []
        for t in live:
            hot = self.reaction_score(t) >= self.react_thr
            if hot:
                self._react_on[t.tid] = self._react_on.get(t.tid, 0) + 1
                self._react_off[t.tid] = 0
            else:
                self._react_off[t.tid] = self._react_off.get(t.tid, 0) + 1
                self._react_on[t.tid] = 0
            if not self._reacting.get(t.tid, False):
                if self._react_on[t.tid] >= self.react_hold:
                    self._reacting[t.tid] = True
            else:
                if self._react_off[t.tid] >= self.react_release:
                    self._reacting[t.tid] = False
            if self._reacting.get(t.tid, False):
                reacting.append(t)
        reacting.sort(key=self.reaction_score, reverse=True)
        return reacting[: self.max_cells]

    def _commit_shown(self, desired: int, is_cut: bool) -> int:
        """Layout hysteresis on the displayed cell-count. Growing (or a cut) is immediate so a
        newly-reacting person is never left out; shrinking waits `layout_shrink` frames so a
        momentary drop in the detected/reacting count doesn't reshuffle the whole grid."""
        if is_cut or desired >= self._shown_n:
            self._shown_n = desired
            self._shrink_cand, self._shrink_streak = None, 0
            return self._shown_n
        if self._shrink_cand != desired:
            self._shrink_cand, self._shrink_streak = desired, 1
        else:
            self._shrink_streak += 1
        if self._shrink_streak >= self.layout_shrink:
            self._shown_n = desired
            self._shrink_cand, self._shrink_streak = None, 0
        return self._shown_n

    # ---- decision ----
    def _decide(self, frame_num: int, is_cut: bool) -> FrameIntent:
        self._just_switched = False
        live = [t for t in self._tracks if frame_num - t.last_seen <= self._retention(t)]

        detected = sum(1 for t in self._tracks
                       if frame_num - t.last_seen < self.mode_hc_window)
        raw = self._raw_mode(detected)
        mode = self._commit_mode(raw, instant=is_cut or self._mode == SceneMode.HOLD)

        if mode != SceneMode.SOLO:
            self._focus_dwell, self._dwell_id = 0, None

        if not live:
            self._cofit = False
            self._prev_split_n = 0
            self._shown_n = 0
            self._shrink_cand, self._shrink_streak = None, 0
            return FrameIntent(frame_num, FramingKind.FOCUS, focus_target=None,
                               active_id=None, is_cut=is_cut, allow_snap=is_cut,
                               confidence=0.0, mode=SceneMode.HOLD)

        reacting = self._update_reacting(frame_num, live)
        R = len(reacting)

        # Desired layout: 2+ reactors -> a multi-cell grid; exactly one reactor in a 3+ scene ->
        # a punch-in; otherwise the calm fallback. Commit it through the grow-fast/shrink-slow
        # hysteresis so detection flicker doesn't reshuffle the grid every second.
        if R >= 2:
            desired = min(R, self.max_cells)
        elif R == 1 and mode == SceneMode.GROUP and self.group_dom_on:
            desired = 1
        else:
            desired = 0
        shown = self._commit_shown(desired, is_cut)
        shown = min(shown, len(live))   # can't display more cells than people actually present

        # ----- 2+ cells -> SHOW THEM ALL (two-shot / 2-way / grid). Fill from the most salient
        #       live people so a cell held open by the shrink debounce stays occupied. -----
        if shown >= 2:
            pool = sorted(live, key=self.reaction_score, reverse=True)[:shown]
            return self._split_decide(frame_num, pool, shown, is_cut, mode)
        self._cofit = False

        # ----- one reactor in a 3+ scene -> reaction-cut punch-in -----
        if shown == 1 and mode == SceneMode.GROUP and self.group_dom_on:
            t = reacting[0] if reacting else max(live, key=self.reaction_score)
            hard = is_cut or self._prev_split_n > 0 or (self._active_id != t.tid)
            self._active_id = t.tid
            self._prev_split_n = 0
            return FrameIntent(frame_num, FramingKind.FOCUS,
                               focus_target=(t.cx, t.cy, t.w, t.h),
                               active_id=t.tid, is_cut=is_cut, allow_snap=hard,
                               confidence=self._confidence(t, frame_num), mode=mode,
                               target_zoom=self.group_dom_zoom)

        # ----- nobody (or one calm subject) -> centroid-fit a crowd, else calm follow -----
        left_split = self._prev_split_n > 0
        self._prev_split_n = 0
        if mode == SceneMode.GROUP:
            # a 3+ scene with no single reaction to cut to: frame the whole group, don't pick one
            return self._group_fit_intent(frame_num, live, is_cut or left_split, mode)

        scored = sorted(live, key=self.reaction_score, reverse=True)
        active = self._select_active(frame_num, scored)
        t = next((x for x in live if x.tid == active), scored[0])
        hard = is_cut or self._just_switched or left_split
        zoom = self._emphasis_zoom(mode, t.tid, hard)
        return FrameIntent(frame_num, FramingKind.FOCUS,
                           focus_target=(t.cx, t.cy, t.w, t.h),
                           active_id=t.tid, is_cut=is_cut, allow_snap=hard,
                           confidence=self._confidence(t, frame_num), mode=mode,
                           target_zoom=zoom)

    def _split_decide(self, frame_num: int, reacting: List[_Track], R: int,
                      is_cut: bool, mode: SceneMode) -> FrameIntent:
        """2+ reactors: a two-shot (one crop) if exactly two co-fit, else a 2-4 cell split grid.
        Cells are ordered left->right so a given person keeps a stable spot."""
        ordered = sorted(reacting, key=lambda t: t.cx)

        if R == 2:
            a, b = ordered[0], ordered[1]
            ax = a.det_cx if a.last_seen == frame_num else a.cx
            bx = b.det_cx if b.last_seen == frame_num else b.cx
            sep = abs(ax - bx)
            margin = self.two_shot_margin * self.crop_w
            if not self._cofit and sep + 2.0 * margin <= self.crop_w:
                self._cofit = True
            elif self._cofit and sep > self.crop_w:
                self._cofit = False
            if self._cofit:
                self._prev_split_n = 0  # a two-shot is a single FOCUS crop, not a split grid
                mx = (a.cx + b.cx) * 0.5
                my = (a.cy + b.cy) * 0.5
                w = sep + (a.w + b.w) * 0.5
                h = max(a.h, b.h)
                return FrameIntent(frame_num, FramingKind.FOCUS, focus_target=(mx, my, w, h),
                                   active_id=None, is_cut=is_cut, allow_snap=is_cut, mode=mode)

        snap = is_cut or self._prev_split_n != R
        self._prev_split_n = R
        targets = [(t.cx, t.cy, t.w, t.h) for t in ordered]
        return FrameIntent(frame_num, FramingKind.SPLIT, split_targets=targets,
                           active_id=None, is_cut=is_cut, allow_snap=snap, mode=mode)

    def _emphasis_zoom(self, mode: SceneMode, active_tid: int, hard: bool) -> float:
        if not self.emphasis_on or mode != SceneMode.SOLO:
            self._focus_dwell, self._dwell_id = 0, active_tid
            return 1.0
        if hard or active_tid != self._dwell_id:
            self._focus_dwell, self._dwell_id = 0, active_tid
        self._focus_dwell += 1
        return self.emphasis_zoom if self._focus_dwell >= self.emphasis_after else 1.0

    def _group_fit_intent(self, frame_num: int, live: List[_Track], snap: bool,
                          mode: SceneMode) -> FrameIntent:
        target, gzoom = self._group_framing(live)
        return FrameIntent(frame_num, FramingKind.FOCUS, focus_target=target,
                           active_id=None, is_cut=snap, allow_snap=snap,
                           confidence=1.0, mode=mode, target_zoom=gzoom)

    def _group_framing(self, heads: List[_Track]):
        """Frame the size-weighted centroid of the heads and zoom to FIT their horizontal hull +
        margin. Spread crowd stays at base (widest); a tight cluster gets a gentle, floored
        punch-in. No dominant-speaker chasing here."""
        ws = [max(1.0, t.w * t.h) for t in heads]
        wsum = sum(ws)
        cx = sum(t.cx * wt for t, wt in zip(heads, ws)) / wsum
        cy = sum(t.cy * wt for t, wt in zip(heads, ws)) / wsum
        left = min(t.cx - t.w / 2 for t in heads)
        right = max(t.cx + t.w / 2 for t in heads)
        needed = (right - left) + 2.0 * self.group_margin * self.crop_w
        zoom = needed / self.crop_w if self.crop_w > 0 else 1.0
        zoom = max(self.group_min_zoom, min(1.0, zoom))
        w = max(t.w for t in heads)
        h = max(t.h for t in heads)
        return (cx, cy, w, h), zoom

    def _select_active(self, frame_num: int, scored: List[_Track]) -> int:
        best = scored[0]
        if self._active_id is None or all(t.tid != self._active_id for t in scored):
            self._active_id = best.tid
            self._cand_id, self._cand_streak = None, 0
            return self._active_id
        best_score = best.speaking_score(self.window)
        if best.tid != self._active_id and best_score >= self.speak_thr:
            if self._cand_id == best.tid:
                self._cand_streak += 1
            else:
                self._cand_id, self._cand_streak = best.tid, 1
            if self._cand_streak >= self.switch_hold:
                self._active_id = best.tid
                self._cand_id, self._cand_streak = None, 0
                self._just_switched = True
        else:
            self._cand_id, self._cand_streak = None, 0
        return self._active_id
