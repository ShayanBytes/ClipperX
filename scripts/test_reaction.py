"""Behavioural test for the REACTION-COUNT layout (the 4-person "show every reactor" fix).

This exercises the headline redesign through the REAL SpeakerTracker, driving it with the new
per-face APPEARANCE-motion cue (`Detection.react`) - the signal that decides who is "reacting":

  reaction_score(track) = react_appearance_weight * mean(react)  + speaking_score + motion

Each reacting person is latched with hold/release hysteresis; the layout then follows the
count R of people reacting at once:

    R >= 3  -> SPLIT grid (3 = two-on-top + one wide; 4 = 2x2 quad), one reactor per cell
    R == 2  -> two-shot (one FOCUS crop) if they co-fit one 9:16 frame, else a 2-way SPLIT
    R == 1  -> punch-in on that single reactor (FOCUS, group_dominant_zoom) in a 3+ scene
    R == 0  -> centroid-fit the crowd (FOCUS, active_id None)

Faces are injected as Detection objects (react=...), bypassing the live detector, exactly like
the other test_*.py suites. Heads are stationary (motion term ~0) and mouths closed unless a
test says otherwise, so `react` is the sole driver - which is the whole point.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CONFIG
from backend.models import Detection, FrameDetections, SceneMode, FramingKind
from backend.reframer.speaker import SpeakerTracker

W, H = 1920, 1080
THR = CONFIG["reaction_threshold"]
HOLD = CONFIG["reaction_hold_frames"]
RELEASE = CONFIG["reaction_release_frames"]
WINDOW = CONFIG["mouth_window_frames"]   # react_score is a windowed mean, so the latch only starts
                                         # releasing once the window has flushed the hot frames
SHRINK = CONFIG["react_layout_shrink_frames"]   # ...and the displayed cell-count then shrinks slowly
HOT = THR * 4.0   # comfortably above threshold -> a clear reactor
COLD = 0.0        # a still onlooker


def head(x, react=COLD, w=160, mouth=0.0):
    return Detection(cx=x, cy=H * 0.45, w=w, h=w * 2, mouth_open=mouth, react=react)


def run(per_frame_faces):
    """per_frame_faces: list (one entry/frame) of lists of Detection. No scene cuts."""
    frames = [FrameDetections(frame_num=f, faces=faces)
              for f, faces in enumerate(per_frame_faces)]
    return SpeakerTracker(CONFIG, W, H).run(frames, [])


def steady(face_specs, frames=40):
    """Hold the same set of faces for `frames` frames; return all intents."""
    return run([[head(*s) if isinstance(s, tuple) else head(s) for s in face_specs]
                for _ in range(frames)])


checks = []
crop_w = SpeakerTracker(CONFIG, W, H).crop_w


def split_n(intent):
    return len(intent.split_targets) if intent.kind == FramingKind.SPLIT and intent.split_targets else 0


# --- A: 4 reactors all animated -> 2x2 quad split (one cell each) ---
four = [(300, HOT), (760, HOT), (1200, HOT), (1620, HOT)]
ia = steady(four)[-1]
checks.append(("A 4 reactors -> SPLIT", ia.kind == FramingKind.SPLIT))
checks.append(("A 4 reactors -> 4 cells (quad)", split_n(ia) == 4))
checks.append(("A split is a group layout (no single active_id)", ia.active_id is None))

# --- B: 3 reactors -> 3-cell split (two-on-top + one wide) ---
three = [(400, HOT), (1000, HOT), (1500, HOT)]
ib = steady(three)[-1]
checks.append(("B 3 reactors -> SPLIT", ib.kind == FramingKind.SPLIT))
checks.append(("B 3 reactors -> 3 cells", split_n(ib) == 3))

# --- C: 2 reactors FAR apart (cannot co-fit one 9:16 crop) -> 2-way split ---
far = [(300, HOT), (1620, HOT)]
ic = steady(far)[-1]
checks.append(("C 2 far reactors -> SPLIT", ic.kind == FramingKind.SPLIT))
checks.append(("C 2 far reactors -> 2 cells", split_n(ic) == 2))

# --- D: 2 reactors CLOSE together (co-fit) -> two-shot, a single FOCUS crop on their midpoint ---
near = [(900, HOT), (1040, HOT)]
idd = steady(near)[-1]
mid = (900 + 1040) / 2
checks.append(("D 2 close reactors -> FOCUS two-shot (not split)", idd.kind == FramingKind.FOCUS))
checks.append(("D two-shot has no single active_id", idd.active_id is None))
checks.append(("D two-shot frames their midpoint",
               idd.focus_target is not None and abs(idd.focus_target[0] - mid) <= 40))

# --- E: exactly 1 reactor among 4 detected people -> reaction-cut punch-in on that person ---
one_hot = [(300, COLD), (760, COLD), (1200, HOT), (1620, COLD)]
ie = steady(one_hot)[-1]
checks.append(("E 1 reactor in a 3+ scene -> FOCUS", ie.kind == FramingKind.FOCUS))
checks.append(("E punch-in targets the reactor (x~1200)",
               ie.focus_target is not None and abs(ie.focus_target[0] - 1200) <= 60))
checks.append(("E punch-in active_id is set", ie.active_id is not None))
checks.append(("E uses the dominant punch-in zoom",
               abs(ie.target_zoom - CONFIG["group_dominant_zoom"]) < 1e-6))

# --- F: nobody reacting (all still) in a 3+ scene -> centroid-fit, no false split/punch-in ---
none_hot = [(300, COLD), (760, COLD), (1200, COLD), (1620, COLD)]
intents_f = steady(none_hot)
iff = intents_f[-1]
checks.append(("F nobody reacting -> FOCUS (centroid-fit)", iff.kind == FramingKind.FOCUS))
checks.append(("F centroid-fit has no single active_id", iff.active_id is None))
checks.append(("F never split a still crowd",
               all(i.kind != FramingKind.SPLIT for i in intents_f)))

# --- G: hold hysteresis - a brief react SPIKE shorter than reaction_hold_frames must NOT split ---
#     One person flickers HOT for (HOLD-2) frames then stops; never sustains long enough to latch.
spike_len = max(1, HOLD - 2)
g_frames = []
for f in range(40):
    r = HOT if (f < spike_len) else COLD
    g_frames.append([head(300, COLD), head(760, COLD), head(1200, r), head(1620, COLD)])
intents_g = run(g_frames)
checks.append(("G a sub-hold react spike never triggers a split",
               all(i.kind != FramingKind.SPLIT for i in intents_g)))

# --- H: release + shrink hysteresis - the grid stays up briefly after reactors stop (no instant
#     collapse). 4 people react for 30 frames (all latch), then ALL go cold (still present). Three
#     debounces stack before the grid collapses: the windowed react_score must flush its hot frames
#     (~WINDOW), then the per-track release counts (RELEASE), then the displayed cell-count shrinks
#     slowly (SHRINK). So the split persists right after they stop and has collapsed well past the sum.
n_hot = 30
cold_tail = WINDOW + RELEASE + SHRINK + 16
h_frames = [[head(*s) for s in four] for _ in range(n_hot)]
h_frames += [[head(x, COLD) for x, _ in four] for _ in range(cold_tail)]
intents_h = run(h_frames)
collapse_by = n_hot + WINDOW + RELEASE + SHRINK + 8   # past window-flush + release + shrink debounce
checks.append(("H split persists right after reactors stop (release/shrink debounce)",
               intents_h[n_hot].kind == FramingKind.SPLIT))
checks.append(("H split has collapsed once past window+release+shrink",
               intents_h[collapse_by].kind != FramingKind.SPLIT))

# --- I: entering a split SNAPS (allow_snap) so the grid appears cleanly, not via a slide ---
checks.append(("I the frame a split first appears requests a snap",
               next(i.allow_snap for i in steady(four) if i.kind == FramingKind.SPLIT)))


print(f"crop_w={crop_w:.0f}px  reaction_threshold={THR}  hold={HOLD}f  release={RELEASE}f\n")
ok = True
for name, passed in checks:
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print(f"\n  A: kind={ia.kind.value} cells={split_n(ia)}   "
      f"B cells={split_n(ib)}   C cells={split_n(ic)}   "
      f"D kind={idd.kind.value}   E zoom={ie.target_zoom:.3f}")
sys.exit(0 if ok else 1)
