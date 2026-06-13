"""Behavioural test for IMPORTANCE-BASED reactor selection (the "few active among many" case).

When a frame has more reacting people than are genuinely *giving content* (e.g. 2 hosts animated,
the rest passive but still clearing the low presence-gate threshold), turning on `importance_select`
should keep only the people within `importance_keep_ratio` of the top reactor — a RELATIVE gate.

The two invariants that matter:
  * OFF (default): everyone detected is shown -> the validated 4-person quad is untouched.
  * ON + everyone equally active: the relative gate keeps EVERYONE -> the quad is STILL untouched.
  * ON + a real activity gap (hosts hot, rest warm-but-low): only the hosts get cells.

Faces are injected as Detection objects (react=...), bypassing the live detector, like the other
test_*.py suites. Heads are stationary and mouths closed, so `react` is the sole importance driver.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from copy import deepcopy

from config import CONFIG
from backend.models import Detection, FrameDetections, FramingKind
from backend.reframer.speaker import SpeakerTracker

W, H = 1920, 1080
THR = CONFIG["reaction_threshold"]
HOT = THR * 4.0    # a strong reactor (host giving content)
WARM = THR * 1.4   # clears the presence gate but is well below a host (a passive onlooker)
COLD = 0.0


def head(x, react=COLD):
    return Detection(cx=x, cy=H * 0.45, w=160, h=320, mouth_open=0.0, react=react)


def run(per_frame_faces, cfg):
    frames = [FrameDetections(frame_num=f, faces=faces)
              for f, faces in enumerate(per_frame_faces)]
    return SpeakerTracker(cfg, W, H).run(frames, [])


def steady(face_specs, cfg, frames=50):
    return run([[head(x, r) for x, r in face_specs] for _ in range(frames)], cfg)


def split_n(intent):
    return len(intent.split_targets) if intent.kind == FramingKind.SPLIT and intent.split_targets else 0


OFF = deepcopy(CONFIG)                       # default: importance_select False
ON = deepcopy(CONFIG); ON["importance_select"] = True

checks = []

# Spread the people far apart so any kept pair is a 2-way SPLIT (never a co-fit two-shot),
# keeping the cell COUNT a clean read of how many survived the gate.
POS = [300, 760, 1200, 1620]

# --- A: gate OFF, 4 equally-hot reactors -> 2x2 quad (the validated case, untouched) ---
ia = steady([(POS[i], HOT) for i in range(4)], OFF)[-1]
checks.append(("A gate off, 4 hot -> SPLIT", ia.kind == FramingKind.SPLIT))
checks.append(("A gate off, 4 hot -> 4 cells (quad)", split_n(ia) == 4))

# --- B: gate ON, 4 equally-hot reactors -> STILL a quad (relative gate keeps all) ---
ib = steady([(POS[i], HOT) for i in range(4)], ON)[-1]
checks.append(("B gate on, all equally hot -> SPLIT", ib.kind == FramingKind.SPLIT))
checks.append(("B gate on, all equally hot -> STILL 4 cells (validated quad untouched)",
               split_n(ib) == 4))

# --- C: gate ON, 2 hosts HOT + 2 passive WARM -> only the 2 hosts survive -> 2-way split ---
mixed = [(POS[0], HOT), (POS[1], WARM), (POS[2], HOT), (POS[3], WARM)]
ic = steady(mixed, ON)[-1]
checks.append(("C gate on, 2 hot + 2 warm -> SPLIT", ic.kind == FramingKind.SPLIT))
checks.append(("C gate on, 2 hot + 2 warm -> only 2 cells (passives pruned)", split_n(ic) == 2))
# the two surviving cells must be the HOT hosts (x=300 and x=1200), not the warm onlookers
if ic.split_targets:
    xs = sorted(t[0] for t in ic.split_targets)
    checks.append(("C survivors are the two hosts (x~300, ~1200)",
                   abs(xs[0] - 300) <= 60 and abs(xs[1] - 1200) <= 60))
else:
    checks.append(("C survivors are the two hosts (x~300, ~1200)", False))

# --- D: same mixed crowd with the gate OFF -> all 4 still shown (no accidental pruning) ---
idd = steady(mixed, OFF)[-1]
checks.append(("D gate off, 2 hot + 2 warm -> all 4 cells (no pruning when off)",
               split_n(idd) == 4))

# --- E: gate ON, 1 host HOT + 3 passive WARM in a 3+ scene -> single-reactor punch-in ---
#     The gate prunes the 3 warm onlookers, leaving R==1 -> the GROUP reaction-cut punch-in.
one_host = [(POS[0], WARM), (POS[1], HOT), (POS[2], WARM), (POS[3], WARM)]
ie = steady(one_host, ON)[-1]
checks.append(("E gate on, 1 hot + 3 warm -> FOCUS punch-in (not a split)",
               ie.kind == FramingKind.FOCUS))
checks.append(("E punch-in targets the host (x~760)",
               ie.focus_target is not None and abs(ie.focus_target[0] - 760) <= 60))
checks.append(("E uses the dominant punch-in zoom",
               abs(ie.target_zoom - CONFIG["group_dominant_zoom"]) < 1e-6))

# --- F: gate ON but everyone only WARM (nobody above importance_min_top_score) ->
#     nobody is really giving content -> keep importance_min_keep, NOT a full crowd split. ---
all_warm = [(POS[i], WARM) for i in range(4)]
intents_f = steady(all_warm, ON)
iff = intents_f[-1]
checks.append(("F gate on, all weak -> never a multi-cell split (no host to feature)",
               all(split_n(i) <= 1 for i in intents_f)))


print(f"HOT={HOT:.4f}  WARM={WARM:.4f}  keep_ratio={ON['importance_keep_ratio']}  "
      f"floor={ON['importance_min_top_score']}  cutoff(HOT)={HOT*ON['importance_keep_ratio']:.4f}\n")
ok = True
for name, passed in checks:
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print(f"\n  A off={split_n(ia)}  B on-equal={split_n(ib)}  C on-mixed={split_n(ic)}  "
      f"D off-mixed={split_n(idd)}  E kind={ie.kind.value}")
sys.exit(0 if ok else 1)
