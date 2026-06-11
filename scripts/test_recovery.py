"""Throwaway behavioural test for the recovery rework (DESIGN.md #1).

Feeds synthetic detections through the REAL SpeakerTracker + CropPlanner and checks:
  A. a detection dropout + re-acquire never snaps (crop center moves <= speed limit)
  B. a scene cut with a repositioned subject DOES snap (one big jump allowed)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CONFIG
from backend.models import VideoMeta, Detection, FrameDetections
from backend.reframer.speaker import SpeakerTracker
from backend.reframer.crop_planner import CropPlanner

W, H, FPS = 1920, 1080, 30.0
meta = VideoMeta(width=W, height=H, fps=FPS, total_frames=0, duration=0, path="")
MAXV = CONFIG["max_velocity_px_per_frame"]


def person(x):
    return Detection(cx=x, cy=H * 0.4, w=180, h=360, mouth_open=0.0)


def run(frames, cuts):
    tracker = SpeakerTracker(CONFIG, W, H)
    planner = CropPlanner(CONFIG, meta)
    intents = tracker.run(frames, cuts)
    plans = planner.plan(intents, [None] * len(frames))
    return [p.crop.x + p.crop.width / 2 for p in plans]  # crop center x per frame


def max_jump(centers, skip=()):
    worst = 0.0
    for i in range(1, len(centers)):
        if i in skip:
            continue
        worst = max(worst, abs(centers[i] - centers[i - 1]))
    return worst


# --- Scenario A: subject at x=1400, detection drops frames 20-34, then returns ---
frames_a = []
for f in range(60):
    if 20 <= f <= 34:
        faces = []                      # detection lost
    else:
        faces = [person(1400)]
    frames_a.append(FrameDetections(frame_num=f, faces=faces))

centers_a = run(frames_a, cuts=[])
jump_a = max_jump(centers_a)
ok_a = jump_a <= MAXV + 1e-6

# --- Scenario B: subject jumps 300->1600 at a scene cut on frame 30 ---
frames_b = []
for f in range(60):
    x = 300 if f < 30 else 1600
    frames_b.append(FrameDetections(frame_num=f, faces=[person(x)]))

centers_b = run(frames_b, cuts=[30])
jump_at_cut = abs(centers_b[30] - centers_b[29])
jump_elsewhere = max_jump(centers_b, skip={30})
ok_b = jump_at_cut > MAXV and jump_elsewhere <= MAXV + 1e-6

# --- Scenario C: HUNTING. Subject drifts 1200->1400 over frames 0-12 then sits still
#     at 1400, with detection dropping during the stationary phase (14-20, 26-31). The
#     crop must SETTLE, not wander back and forth chasing a phantom velocity. ---
frames_c = []
for f in range(80):
    x = 1200 + (200 * f / 12) if f < 12 else 1400
    lost = (14 <= f <= 20) or (26 <= f <= 31)
    frames_c.append(FrameDetections(frame_num=f, faces=[] if lost else [person(x)]))

centers_c = run(frames_c, cuts=[])
settled = centers_c[40:]                      # after motion + both dropouts are over
wander = max(settled) - min(settled)          # total back-and-forth range while "still"
ok_c = wander <= 8.0                          # a few px of easing is fine; hunting is not

# --- Scenario D: MODE HYSTERESIS. One steady speaker; a 2nd person flickers in for a
#     few frames (must stay SOLO) then appears for good (must commit DUAL after the
#     enter-dwell, not instantly). Uses the tracker's committed intent.mode. ---
from backend.models import SceneMode
from backend.reframer.speaker import SpeakerTracker as _ST


def person2(x):
    return Detection(cx=x, cy=H * 0.4, w=160, h=320, mouth_open=0.0)


frames_d = []
for f in range(120):
    faces = [person(700)]                      # steady solo speaker on the left
    flicker = 30 <= f <= 33                     # brief 4-frame intrusion
    sustained = f >= 60                         # second person stays from frame 60
    if flicker or sustained:
        faces.append(person2(1300))
    frames_d.append(FrameDetections(frame_num=f, faces=faces))

modes_d = [i.mode for i in _ST(CONFIG, W, H).run(frames_d, [])]
flicker_stayed_solo = all(m == SceneMode.SOLO for m in modes_d[30:34])
enter = CONFIG["mode_enter_frames"]
committed_dual_after_dwell = (
    modes_d[60 + enter] == SceneMode.DUAL and       # DUAL once the dwell elapses
    all(m == SceneMode.SOLO for m in modes_d[60:60 + enter - 1])  # not before
)
ok_d = flicker_stayed_solo and committed_dual_after_dwell

# --- Scenario E: TWO-SHOT vs SPLIT. Two people BOTH talking. When close enough to
#     co-fit one 9:16 crop -> FOCUS on their midpoint (two-shot); when far apart -> SPLIT. ---
def dual_talking(xa, xb):
    fr = []
    for f in range(80):
        a = Detection(cx=xa, cy=H * 0.4, w=180, h=360, mouth_open=(0.0 if f % 2 else 0.6))
        b = Detection(cx=xb, cy=H * 0.4, w=180, h=360, mouth_open=(0.6 if f % 2 else 0.0))
        fr.append(FrameDetections(frame_num=f, faces=[a, b]))
    return fr


def kinds(frames):
    from backend.reframer.speaker import SpeakerTracker as _ST2
    return [(i.kind, i.mode, i.focus_target) for i in _ST2(CONFIG, W, H).run(frames, [])]

# crop_w for a 1920x1080 source ~= 1080*1080/1920 = 607px. Close pair (260px apart) co-fits;
# far pair (900px apart) cannot.
close = kinds(dual_talking(830, 1090))[-1]   # settled frame
far = kinds(dual_talking(500, 1400))[-1]
from backend.models import FramingKind as _FK
ok_e = (close[1] == SceneMode.DUAL and close[0] == _FK.FOCUS and close[2] is not None
        and far[1] == SceneMode.DUAL and far[0] == _FK.SPLIT)
close_mid = close[2][0] if close[2] else None

print(f"speed limit (max_velocity_px_per_frame) = {MAXV}")
print(f"[A] dropout+reacquire   max per-frame jump = {jump_a:7.2f}  -> {'PASS (no snap)' if ok_a else 'FAIL (snapped!)'}")
print(f"[B] scene cut           jump at cut        = {jump_at_cut:7.2f}  elsewhere = {jump_elsewhere:6.2f}")
print(f"    -> {'PASS (snaps only at cut)' if ok_b else 'FAIL'}")
print(f"[C] stationary+dropouts wander range       = {wander:7.2f}  -> {'PASS (settles)' if ok_c else 'FAIL (hunting!)'}")
print(f"[D] mode hysteresis: 4f flicker stayed SOLO = {flicker_stayed_solo}; "
      f"sustained committed DUAL after {enter}f dwell = {committed_dual_after_dwell}")
print(f"    -> {'PASS' if ok_d else 'FAIL'}")
print(f"[E] dual two-shot: close pair -> {close[0].value}@{close_mid and round(close_mid)} "
      f"(want focus/two-shot); far pair -> {far[0].value} (want split)")
print(f"    -> {'PASS' if ok_e else 'FAIL'}")
sys.exit(0 if (ok_a and ok_b and ok_c and ok_d and ok_e) else 1)
