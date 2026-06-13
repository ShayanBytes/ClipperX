"""Behavioural test for the GROUP centroid-fit fallback (DESIGN.md #6 / §4).

3+ people -> GROUP mode frames the size-weighted CENTROID of the heads (no dominant-speaker
chasing) and zooms to FIT their hull: a spread-out crowd stays at base (widest), a tight
cluster gets a gentle, floored punch-in. Runs the REAL SpeakerTracker.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CONFIG
from backend.models import VideoMeta, Detection, FrameDetections, SceneMode, FramingKind
from backend.reframer.speaker import SpeakerTracker

W, H = 1920, 1080
GMIN = CONFIG["group_min_zoom"]


def head(x, w=160, mouth=0.0):
    return Detection(cx=x, cy=H * 0.45, w=w, h=w * 2, mouth_open=mouth)


def last_intent(xs, frames=60):
    fr = [FrameDetections(frame_num=f, faces=[head(x) for x in xs]) for f in range(frames)]
    return SpeakerTracker(CONFIG, W, H).run(fr, [])[-1]


def last_intent_dom(xs, dom_idx, frames=80, cfg=None):
    """Drive a GROUP scene where person `dom_idx` has an OSCILLATING mouth (a real reaction:
    high speaking-score std) and everyone else is still. Returns the final intent."""
    use = cfg if cfg is not None else CONFIG
    fr = []
    for f in range(frames):
        faces = []
        for k, x in enumerate(xs):
            m = (0.6 if f % 2 == 0 else 0.0) if k == dom_idx else 0.0
            faces.append(head(x, mouth=m))
        fr.append(FrameDetections(frame_num=f, faces=faces))
    return SpeakerTracker(use, W, H).run(fr, [])[-1]


checks = []

# crop_w for 1920x1080 ~= 608px. Spread crowd far exceeds it; tight cluster fits inside it.
crop_w = SpeakerTracker(CONFIG, W, H).crop_w

# --- A: 4 people spread across the frame -> GROUP, centroid-framed, stay wide (z=1.0) ---
spread = [300, 760, 1200, 1620]
ia = last_intent(spread)
centroid = sum(spread) / len(spread)
checks.append(("A commits GROUP", ia.mode == SceneMode.GROUP))
checks.append(("A is a single FOCUS (not split)", ia.kind == FramingKind.FOCUS))
checks.append(("A frames the centroid", ia.focus_target is not None and abs(ia.focus_target[0] - centroid) <= 40))
checks.append(("A stays at base width (spread crowd)", abs(ia.target_zoom - 1.0) < 1e-9))
checks.append(("A does not chase one person (active_id None)", ia.active_id is None))

# --- B: 3 people tightly clustered -> GROUP, gentle punch-in, floored at group_min_zoom ---
tight = [900, 1000, 1100]
ib = last_intent(tight)
checks.append(("B commits GROUP", ib.mode == SceneMode.GROUP))
checks.append(("B punches in on a tight cluster", ib.target_zoom < 1.0))
checks.append(("B respects the group zoom floor", ib.target_zoom >= GMIN - 1e-9))
checks.append(("B frames the cluster centroid", abs(ib.focus_target[0] - sum(tight) / 3) <= 30))

# --- C: 4 people, ONE clearly reacting (oscillating mouth) -> punch in on that reactor ---
dom = [300, 760, 1200, 1620]
ic = last_intent_dom(dom, dom_idx=2)   # person at x=1200 is the dominant reactor
checks.append(("C commits GROUP", ic.mode == SceneMode.GROUP))
checks.append(("C punches in on the dominant reactor (active_id set)", ic.active_id is not None))
checks.append(("C frames that reactor, not the centroid",
               ic.focus_target is not None and abs(ic.focus_target[0] - 1200) <= 60))
checks.append(("C uses the dominant punch-in zoom",
               abs(ic.target_zoom - CONFIG["group_dominant_zoom"]) < 1e-6))
checks.append(("C sub-full-height crop (vertical composition possible)",
               ic.target_zoom < 1.0))

# --- D: same scene with group_dominant_focus OFF -> falls back to centroid-fit (active_id None) ---
from presets import apply_preset  # noqa: E402
cfg_off = dict(CONFIG); cfg_off["group_dominant_focus"] = False
idd = last_intent_dom(dom, dom_idx=2, cfg=cfg_off)
checks.append(("D with dominant-focus off -> centroid-fit (active_id None)", idd.active_id is None))

# --- E: nobody clearly dominates (all still) -> still centroid-fit, no false punch-in ---
ie = last_intent_dom(spread, dom_idx=-1)   # dom_idx=-1 -> no one oscillates
checks.append(("E nobody dominates -> centroid-fit (active_id None)", ie.active_id is None))

print(f"crop_w={crop_w:.0f}px  group_min_zoom={GMIN}\n")
ok = True
for name, passed in checks:
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print(f"\n  A: mode={ia.mode.value} target_x={ia.focus_target[0]:.0f} zoom={ia.target_zoom:.3f}")
print(f"  B: mode={ib.mode.value} target_x={ib.focus_target[0]:.0f} zoom={ib.target_zoom:.3f}")
sys.exit(0 if ok else 1)
