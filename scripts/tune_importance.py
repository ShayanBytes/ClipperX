"""Tune the importance-based reactor gate on a real clip WITHOUT re-running the detector each time.

The detector pass (face analysis over every frame) is the slow part. This script runs it ONCE,
pickles the detections + scene cuts next to the clip (`<clip>.dets.pkl`), and on later runs loads
that cache instantly. It then sweeps the importance gate (off, plus several keep_ratios) through
the REAL SpeakerTracker and reports, for each setting, the distribution of how many cells the
layout actually displays — so we can see how hard the gate prunes the "show everyone" quad-spam
and pick keep_ratio / min_top_score from evidence instead of guessing.

Usage:
    python scripts/tune_importance.py <video> [--reanalyze]

`--reanalyze` forces a fresh detector pass (use after changing detector/config detection knobs).
"""
import os, sys, pickle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import Counter
from copy import deepcopy

from backend.pipeline import probe_meta
from backend.reframer.detector import FaceAnalyzer
from backend.reframer.scene_detector import detect_scene_cuts
from backend.reframer.speaker import SpeakerTracker
from backend.models import FramingKind
from config import CONFIG

args = sys.argv[1:]
reanalyze = "--reanalyze" in args
if reanalyze:
    args.remove("--reanalyze")
inp = args[0]

meta = probe_meta(inp)
fps = meta.fps if meta.fps > 0 else 30.0
cache = inp + ".dets.pkl"

if os.path.exists(cache) and not reanalyze:
    with open(cache, "rb") as fh:
        dets, cuts = pickle.load(fh)
    print(f"{os.path.basename(inp)}: {meta.width}x{meta.height} @ {fps:.0f}fps, "
          f"{meta.total_frames} frames, {meta.duration:.1f}s  (detections from cache)")
else:
    print(f"{os.path.basename(inp)}: {meta.width}x{meta.height} @ {fps:.0f}fps, "
          f"{meta.total_frames} frames, {meta.duration:.1f}s  (analyzing — one-time, slow)...")
    an = FaceAnalyzer(CONFIG)
    dets, _ = an.analyze(meta)
    an.close()
    cuts = detect_scene_cuts(inp, CONFIG["scene_threshold"], CONFIG["min_scene_len_frames"])
    with open(cache, "wb") as fh:
        pickle.dump((dets, cuts), fh)
    print(f"  cached detections -> {os.path.basename(cache)}")


def cells_shown(intent):
    """How many distinct source regions this frame actually displays (1 for any FOCUS, N for SPLIT)."""
    if intent.kind == FramingKind.SPLIT:
        return len(intent.split_targets) if intent.split_targets else 0
    return 1 if intent.focus_target is not None else 0


def layout_token(i):
    if i.kind == FramingKind.SPLIT:
        return f"split-{len(i.split_targets) if i.split_targets else 0}"
    if i.focus_target is None:
        return "hold"
    if i.active_id is not None:
        return "punch" if i.mode.value == "group" else "focus"
    return "group/two-shot"


def evaluate(cfg, label):
    intents = SpeakerTracker(cfg, meta.width, meta.height).run(dets, cuts)
    n = len(intents)
    cellhist = Counter(cells_shown(i) for i in intents)
    toks = [layout_token(i) for i in intents]
    changes = sum(1 for a, b in zip(toks, toks[1:]) if a != b)
    quad = 100 * cellhist.get(4, 0) / n
    multi = 100 * sum(v for k, v in cellhist.items() if k >= 2) / n
    single = 100 * (cellhist.get(1, 0)) / n
    churn = changes / (n / fps)
    cdesc = "  ".join(f"{k}c:{100*cellhist.get(k,0)/n:.0f}%" for k in range(0, 5))
    print(f"  {label:<22}  {cdesc}   | multi>={multi:4.0f}% quad={quad:4.0f}% "
          f"1cell={single:4.0f}%  churn={churn:.2f}/s")


print(f"\nframes={len(dets)}  cuts={len(cuts)}")
print("Cell-count distribution per setting (0c=hold, 1c=focus/punch/two-shot, 2-4c=split grid):\n")

off = deepcopy(CONFIG); off["importance_select"] = False
evaluate(off, "gate OFF (baseline)")

for ratio in (0.40, 0.55, 0.70, 0.85):
    on = deepcopy(CONFIG)
    on["importance_select"] = True
    on["importance_keep_ratio"] = ratio
    evaluate(on, f"gate ON  ratio={ratio:.2f}")

print("\nHigher ratio = stricter (keep only people close to the top reactor -> fewer cells).")
print("Watch the chosen setting with: scripts/debug_overlay.py <clip>  (after setting the knobs).")
