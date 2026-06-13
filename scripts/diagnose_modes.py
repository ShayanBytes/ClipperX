"""Quantitative read-out of the engine's decisions on a clip (no rendering).

Runs the REAL analysis + speaker stage and tallies what the engine DECIDED: scene-mode
distribution, focus vs two-shot vs split, how often people were detected, and the zoom
range used. Lets us sanity-check DUAL / GROUP / emphasis on real footage without watching.

Usage: python scripts/diagnose_modes.py <video> [--preset NAME]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import Counter
from backend.pipeline import probe_meta
from backend.reframer.detector import FaceAnalyzer
from backend.reframer.scene_detector import detect_scene_cuts
from backend.reframer.speaker import SpeakerTracker
from backend.models import FramingKind
from config import CONFIG
from presets import apply_preset

args = sys.argv[1:]
preset = "auto"
if "--preset" in args:
    i = args.index("--preset"); preset = args[i + 1]; del args[i:i + 2]
inp = args[0]
cfg = apply_preset(CONFIG, preset)

meta = probe_meta(inp)
print(f"{os.path.basename(inp)}: {meta.width}x{meta.height} @ {meta.fps:.0f}fps, "
      f"{meta.total_frames} frames, {meta.duration:.1f}s  (preset: {preset})")

an = FaceAnalyzer(cfg)
dets, _ = an.analyze(meta)
an.close()
cuts = detect_scene_cuts(inp, cfg["scene_threshold"], cfg["min_scene_len_frames"])
intents = SpeakerTracker(cfg, meta.width, meta.height).run(dets, cuts)

n = len(intents)
modes = Counter(i.mode.value for i in intents)


def classify(i):
    if i.kind == FramingKind.SPLIT:
        return "split"
    # DUAL two-shot and GROUP both emit a centroid focus with active_id=None; tell them
    # apart by the committed mode so the read-out isn't misleading.
    if i.active_id is None and i.focus_target is not None:
        return "group_fit" if i.mode.value == "group" else "dual_two_shot"
    return "focus"


kinds = Counter(classify(i) for i in intents)
heads = Counter(len(d.faces) for d in dets)
zooms = [i.target_zoom for i in intents]
punched = sum(1 for z in zooms if z < 0.999)


def pct(c):
    return f"{c} ({100*c/n:4.1f}%)"


print(f"\nscene cuts: {len(cuts)}")
print("\nscene mode distribution:")
for m in ("hold", "solo", "dual", "group"):
    if modes.get(m):
        print(f"  {m:6s} {pct(modes[m])}")
print("\nframing kind:")
for k in ("focus", "dual_two_shot", "split", "group_fit"):
    if kinds.get(k):
        print(f"  {k:13s} {pct(kinds[k])}")
print("\nheads detected per frame:")
for h in sorted(heads):
    print(f"  {h} head(s): {pct(heads[h])}")
print(f"\nzoom: min={min(zooms):.3f} max={max(zooms):.3f}  "
      f"punched-in frames (z<1): {pct(punched)}")
