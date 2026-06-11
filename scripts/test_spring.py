"""Behavioural test for the spring camera + zoom primitive (DESIGN.md #4 / §5).

Feeds hand-built FrameIntents straight through the REAL CropPlanner and checks the
cinematic invariants the spring must satisfy:
  A. pan reaches its target with NO overshoot, monotonic, within the speed limit, settles
  B. snap (cut) still hard-jumps in one frame
  C. zoom punches IN smoothly: rate-limited, monotonic, settles near target, stays centred
  D. zoom snaps on a cut
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CONFIG
from backend.models import VideoMeta, FramingKind, SceneMode
from backend.reframer.speaker import FrameIntent
from backend.reframer.crop_planner import CropPlanner

W, H, FPS = 1920, 1080, 30.0
meta = VideoMeta(width=W, height=H, fps=FPS, total_frames=0, duration=0, path="")
MAXV = CONFIG["max_velocity_px_per_frame"]


def intent(f, tx, ty=H * 0.4, snap=False, zoom=1.0):
    return FrameIntent(frame_num=f, kind=FramingKind.FOCUS, focus_target=(tx, ty, 180, 360),
                       active_id=1, is_cut=snap, allow_snap=snap, confidence=1.0,
                       mode=SceneMode.SOLO, target_zoom=zoom)


def plan(intents):
    return CropPlanner(CONFIG, meta).plan(intents, [None] * len(intents))


def centers(plans):
    return [p.crop.x + p.crop.width / 2 for p in plans]


def widths(plans):
    return [p.crop.width for p in plans]


def max_jump(seq, skip=()):
    return max((abs(seq[i] - seq[i - 1]) for i in range(1, len(seq)) if i not in skip), default=0.0)


checks = []

# --- A: step the target far right, hold; spring must ease in, no overshoot, settle ---
plans_a = plan([intent(f, 1500) for f in range(140)])
cx_a = centers(plans_a)
base_w = CropPlanner(CONFIG, meta).base_crop_w
settle_target = 1500 - CONFIG["dead_zone_ratio"] * base_w        # dead-zone edge
overshoot = max(cx_a) - settle_target
monotonic = all(cx_a[i] >= cx_a[i - 1] - 1e-6 for i in range(1, len(cx_a)))
settled_range = max(cx_a[-20:]) - min(cx_a[-20:])
checks.append(("A pan respects speed limit", max_jump(cx_a) <= MAXV + 1e-6))
checks.append(("A pan does NOT overshoot", overshoot <= 1.0))
checks.append(("A pan approach is monotonic", monotonic))
checks.append(("A pan settles", settled_range <= 1.0))
checks.append(("A pan actually arrives", abs(cx_a[-1] - settle_target) <= 2.0))

# --- B: a cut with a repositioned subject snaps in one frame ---
seq_b = [intent(f, 400) for f in range(30)] + [intent(30, 1600, snap=True)] + \
        [intent(f, 1600) for f in range(31, 60)]
cx_b = centers(plan(seq_b))
checks.append(("B snaps at the cut", abs(cx_b[30] - cx_b[29]) > MAXV))
checks.append(("B no snap elsewhere", max_jump(cx_b, skip={30}) <= MAXV + 1e-6))

# --- C: sustained zoom punch-in to 0.7 -> width eases from base toward base*0.7 ---
plans_c = plan([intent(f, 960, zoom=0.7) for f in range(160)])
w_c = widths(plans_c)
want_w = round(base_w * 0.7)
zoom_rate_px = CONFIG["zoom_max_rate_per_frame"] * base_w
mono_zoom = all(w_c[i] <= w_c[i - 1] + 1e-6 for i in range(1, len(w_c)))
checks.append(("C zoom starts at base", abs(w_c[0] - base_w) <= base_w * CONFIG["zoom_max_rate_per_frame"] + 1))
checks.append(("C zoom is rate-limited", max_jump(w_c) <= zoom_rate_px + 1.5))
checks.append(("C zoom punches in monotonically", mono_zoom))
checks.append(("C zoom settles near target", abs(w_c[-1] - want_w) <= 2))
# crop stays inside the frame and roughly centred on the subject (960)
last = plans_c[-1].crop
checks.append(("C zoomed crop stays in-frame", last.x >= 0 and last.x + last.width <= W))

# --- D: zoom snaps on a cut ---
plans_d = plan([intent(0, 960, snap=True, zoom=0.7)])
checks.append(("D zoom snaps on cut", abs(plans_d[0].crop.width - round(base_w * 0.7)) <= 1))

print(f"base focus crop width = {base_w}px   speed limit = {MAXV}px/frame\n")
ok = True
for name, passed in checks:
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print(f"\n  A settle={cx_a[-1]:.1f} (target {settle_target:.1f}, overshoot {overshoot:.2f})")
print(f"  C width {w_c[0]}->{w_c[-1]} (target {want_w}), max d/frame={max_jump(w_c):.1f} (cap {zoom_rate_px:.1f})")
sys.exit(0 if ok else 1)
