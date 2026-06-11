"""
crop_planner.py - turn per-frame framing intents into actual crop boxes.

This is the cinematic core (L4 in DESIGN.md). For FOCUS frames it moves the crop like a
calm camera operator, driven by **critically-damped springs** (one per axis + one for
zoom) rather than a raw EMA - the spring eases IN *and* OUT with no overshoot:
  * dead zone   - the subject can drift within a central band without the crop moving
  * spring      - critically-damped PD easing toward the target (carries velocity)
  * speed limit - capped px/frame so a fast catch-up never lurches
  * zoom        - a separate, slower spring scales the crop box (punch-in); base = widest
  * snap        - on a scene cut, a hard speaker switch, or entering/leaving split, the
                  crop (and zoom) jump instantly (no awkward post-cut slide)
  * absent      - when no face is present, hold position and drift gently toward the
                  motion centroid so a held-up object stays in frame

Zoom note: the full-height 9:16 crop is ALREADY the widest 9:16 region a 16:9 source can
yield, so zoom only punches IN (z<=1); "zoom out past base" is impossible without bars and
is what SPLIT handles. See DESIGN.md sections 5 & 10.

For SPLIT frames it frames each person in their own half (top = left person, bottom =
right person), stacked by the renderer into 1080x1920. The split path still uses EMA - it
is static-ish and out of scope for the spring rework.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from backend.models import CropBox, FramePlan, FramingKind, VideoMeta
from backend.reframer.speaker import FrameIntent


class _Spring:
    """Critically-damped 1-D spring (no overshoot, ever). One responsiveness knob
    `omega` (per-frame angular frequency); carries velocity so motion eases in AND out.

    Uses the analytic critically-damped update (Game Programming Gems 4 / SmoothDamp),
    which is stable for any omega*dt - no integration blow-up at high responsiveness.
    An optional `max_step` clamps movement per frame (the cinematic speed-limit).
    """

    def __init__(self, x: float, omega: float, max_step: float = float("inf")):
        self.x = float(x)
        self.v = 0.0
        self.omega = float(omega)
        self.max_step = float(max_step)

    def snap(self, x: float):
        """Hard-jump to x and kill velocity (used on scene cuts / deliberate switches)."""
        self.x = float(x)
        self.v = 0.0

    def step(self, target: float, dt: float = 1.0) -> float:
        w = self.omega
        if w <= 0.0:                      # degenerate: behave as an instant follow
            self.x, self.v = float(target), 0.0
            return self.x
        exp = math.exp(-w * dt)
        delta = self.x - target
        temp = (self.v + w * delta) * dt
        new_x = target + (delta + temp) * exp
        new_v = (self.v - w * temp) * exp
        # speed limit: never move more than max_step in one frame
        move = new_x - self.x
        if move > self.max_step:
            new_x, new_v = self.x + self.max_step, self.max_step
        elif move < -self.max_step:
            new_x, new_v = self.x - self.max_step, -self.max_step
        self.x, self.v = new_x, new_v
        return self.x

    def clamp(self, lo: float, hi: float):
        """Keep x within [lo, hi]; kill velocity if it hit a wall (no wall-grinding)."""
        if hi < lo:
            hi = lo
        if self.x < lo:
            self.x, self.v = lo, 0.0
        elif self.x > hi:
            self.x, self.v = hi, 0.0


class CropPlanner:
    def __init__(self, config: dict, meta: VideoMeta):
        self.cfg = config
        self.meta = meta
        self.W, self.H = meta.width, meta.height
        out_w, out_h = config["output_width"], config["output_height"]

        # --- focus crop geometry at zoom=1 (the WIDEST 9:16 region the source allows) ---
        self.base_crop_h = self.H
        self.base_crop_w = round(self.H * out_w / out_h)
        if self.base_crop_w > self.W:
            self.base_crop_w = self.W
            self.base_crop_h = round(self.W * out_h / out_w)

        # --- split crop geometry (each half is out_w x out_h/2) ---
        self.split_h = self.H
        self.split_w = round(self.H * out_w / (out_h / 2))
        if self.split_w > self.W:
            self.split_w = self.W
            self.split_h = round(self.W * (out_h / 2) / out_w)

        self.dead_ratio = float(config["dead_zone_ratio"])
        self.max_vel = float(config["max_velocity_px_per_frame"])
        self.alpha = float(config["ema_alpha"])              # split path only
        self.v_pos = float(config["vertical_position"])
        self.saliency_bias = float(config["saliency_bias"])

        # spring camera (L4)
        omega = float(config.get("camera_responsiveness", 0.22))
        z_omega = float(config.get("zoom_responsiveness", 0.08))
        self.min_zoom = float(config.get("min_zoom", 0.62))
        z_rate = float(config.get("zoom_max_rate_per_frame", 0.02))
        self.pan_x = _Spring(self.W / 2.0, omega, self.max_vel)
        self.pan_y = _Spring(self.H / 2.0, omega, self.max_vel)
        self.zoom = _Spring(1.0, z_omega, z_rate)

        # split / transition state
        self.prev_active: Optional[int] = None
        self.was_split = False
        self.split_cx: List[Optional[float]] = [None, None]

    def plan(
        self,
        intents: List[FrameIntent],
        motion: List[Optional[Tuple[float, float]]],
    ) -> List[FramePlan]:
        plans: List[FramePlan] = []
        for i, intent in enumerate(intents):
            mc = motion[i] if i < len(motion) else None
            if intent.kind == FramingKind.SPLIT and intent.split_targets:
                plans.append(self._plan_split(intent))
            else:
                plans.append(self._plan_focus(intent, mc))
        return plans

    # ---- focus ----
    def _plan_focus(self, intent: FrameIntent, motion: Optional[Tuple[float, float]]) -> FramePlan:
        # The speaker stage decides when a hard jump is warranted (cut / deliberate switch).
        # A re-acquired target after a detection dropout is NOT a snap - the camera eases
        # back to it, which is the whole point of the recovery rework. Leaving a split snaps.
        snap = intent.allow_snap or self.was_split

        # zoom first - it sets the crop size that pan + dead-zone are measured against.
        z = self._update_zoom(intent.target_zoom, snap)
        cw = max(8, int(round(self.base_crop_w * z)))
        ch = max(8, int(round(self.base_crop_h * z)))
        dead = self.dead_ratio * cw

        if intent.focus_target is not None:
            tx, ty, _, _ = intent.focus_target
            self._pan_x(tx, cw, dead, snap)
            self._pan_y(ty, ch, snap)
        else:
            # subject absent: hold, drift gently toward the motion centroid
            if motion is not None:
                desired = self.pan_x.x + self.saliency_bias * (motion[0] - self.pan_x.x)
                self.pan_x.step(desired)
                self.pan_x.clamp(cw / 2, self.W - cw / 2)
            # else: hold completely still

        self.prev_active = intent.active_id
        self.was_split = False

        x = self._clamp(self.pan_x.x - cw / 2, 0, self.W - cw)
        y = self._clamp(self.pan_y.x - ch / 2, 0, self.H - ch)
        return FramePlan(
            frame_num=intent.frame_num,
            kind=FramingKind.FOCUS,
            crop=CropBox(int(round(x)), int(round(y)), cw, ch),
        )

    def _update_zoom(self, target_zoom: float, snap: bool) -> float:
        tz = self._clamp(float(target_zoom or 1.0), self.min_zoom, 1.0)
        if snap:
            self.zoom.snap(tz)
        else:
            self.zoom.step(tz)
            self.zoom.clamp(self.min_zoom, 1.0)
        return self.zoom.x

    def _pan_x(self, tx: float, cw: float, dead: float, snap: bool):
        # dead zone: only chase enough to bring the subject back to the band edge
        delta = tx - self.pan_x.x
        if delta > dead:
            target = tx - dead
        elif delta < -dead:
            target = tx + dead
        else:
            target = self.pan_x.x
        lo, hi = cw / 2, self.W - cw / 2
        if snap:
            self.pan_x.snap(self._clamp(target, lo, hi))
        else:
            self.pan_x.step(target)
            self.pan_x.clamp(lo, hi)

    def _pan_y(self, ty: float, ch: float, snap: bool):
        if ch >= self.H:
            self.pan_y.snap(self.H / 2.0)   # full height -> no vertical motion
            return
        target = ty + ch * (0.5 - self.v_pos)
        lo, hi = ch / 2, self.H - ch / 2
        if snap:
            self.pan_y.snap(self._clamp(target, lo, hi))
        else:
            self.pan_y.step(target)
            self.pan_y.clamp(lo, hi)

    # ---- split ----
    def _plan_split(self, intent: FrameIntent) -> FramePlan:
        targets = intent.split_targets
        snap = not self.was_split or intent.is_cut
        boxes = []
        half_lo = self.split_w / 2
        half_hi = self.W - self.split_w / 2
        for slot in range(2):
            tx = targets[slot][0]
            cur = self.split_cx[slot]
            if snap or cur is None:
                cur = self._clamp(tx, half_lo, half_hi)
            else:
                cur += self.alpha * (self._clamp(tx, half_lo, half_hi) - cur)
            self.split_cx[slot] = cur
            x = self._clamp(cur - self.split_w / 2, 0, self.W - self.split_w)
            y = self._clamp(self.H / 2 - self.split_h / 2, 0, self.H - self.split_h)
            boxes.append(CropBox(int(round(x)), int(round(y)), self.split_w, self.split_h))

        self.was_split = True
        self.prev_active = None
        return FramePlan(
            frame_num=intent.frame_num,
            kind=FramingKind.SPLIT,
            top=boxes[0],     # left person on top
            bottom=boxes[1],  # right person on bottom
        )

    @staticmethod
    def _clamp(v: float, lo: float, hi: float) -> float:
        if hi < lo:
            return lo
        return max(lo, min(hi, v))
