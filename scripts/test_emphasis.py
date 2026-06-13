"""Behavioural test for the emphasis punch-in (first consumer of the zoom primitive).

A held SOLO shot must start WIDE and slowly push in once it's been held past
`emphasis_after_frames`; a scene cut (or speaker switch) must reset it back to wide.
Runs the REAL SpeakerTracker (+ CropPlanner for the rendered width).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CONFIG
from backend.models import VideoMeta, Detection, FrameDetections, SceneMode
from backend.reframer.speaker import SpeakerTracker
from backend.reframer.crop_planner import CropPlanner

W, H = 1920, 1080
meta = VideoMeta(width=W, height=H, fps=30.0, total_frames=0, duration=0, path="")
AFTER = CONFIG["emphasis_after_frames"]
EZOOM = CONFIG["emphasis_zoom"]


def person(x, f):
    # alternating mouth so it reads as a speaking solo subject
    return Detection(cx=x, cy=H * 0.4, w=180, h=360, mouth_open=(0.6 if f % 2 else 0.0))


def zooms(frames, cuts):
    return [i.target_zoom for i in SpeakerTracker(CONFIG, W, H).run(frames, cuts)]


checks = []

# --- A: a single subject held for 200 frames, no cuts ---
held = [FrameDetections(frame_num=f, faces=[person(900, f)]) for f in range(200)]
z = zooms(held, [])
checks.append(("A starts wide (no early push-in)", all(abs(v - 1.0) < 1e-9 for v in z[:AFTER - 1])))
checks.append(("A pushes in once held past the dwell", abs(z[AFTER] - EZOOM) < 1e-9))
checks.append(("A stays pushed in while held", abs(z[-1] - EZOOM) < 1e-9))

# --- B: same, but a scene cut at frame 120 must reset to wide, then rebuild ---
z_cut = zooms(held, [120])
checks.append(("B is pushed in just before the cut", abs(z_cut[119] - EZOOM) < 1e-9))
checks.append(("B resets to wide on the cut", abs(z_cut[120] - 1.0) < 1e-9))
checks.append(("B has not re-engaged a few frames after the cut", abs(z_cut[120 + 5] - 1.0) < 1e-9))

# --- C: end-to-end through the planner, the crop width actually narrows toward base*EZOOM ---
planner = CropPlanner(CONFIG, meta)
plans = planner.plan(SpeakerTracker(CONFIG, W, H).run(held, []), [None] * len(held))
w0 = plans[0].crop.width
w_end = plans[-1].crop.width
base_w = planner.base_crop_w
checks.append(("C crop starts at base width", abs(w0 - base_w) <= base_w * CONFIG["zoom_max_rate_per_frame"] + 1))
checks.append(("C crop narrows toward emphasis", abs(w_end - round(base_w * EZOOM)) <= 3))

# --- D: disabling the feature keeps zoom flat at 1.0 ---
import copy
cfg_off = copy.deepcopy(CONFIG)
cfg_off["emphasis_punch_in"] = False
z_off = [i.target_zoom for i in SpeakerTracker(cfg_off, W, H).run(held, [])]
checks.append(("D disabled -> always wide", all(abs(v - 1.0) < 1e-9 for v in z_off)))

print(f"emphasis_after={AFTER}f  emphasis_zoom={EZOOM}  base_w={base_w}px\n")
ok = True
for name, passed in checks:
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print(f"\n  A zoom timeline: f0={z[0]} f{AFTER-1}={z[AFTER-1]} f{AFTER}={z[AFTER]} f199={z[-1]}")
print(f"  C width {w0} -> {w_end} (base {base_w}, target {round(base_w*EZOOM)})")
sys.exit(0 if ok else 1)
