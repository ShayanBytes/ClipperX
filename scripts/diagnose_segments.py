"""Per-scene-segment read-out: for each cut-to-cut segment of a clip, show its time range,
the head-count it actually detected, the mode it committed, and what it framed (centroid group
fit vs dominant-reactor punch-in vs single focus vs two-shot vs split).

This is the tool for "which scene is which" — it lines up the engine's decisions with the
scenes the user describes by eye, so we stop tuning blind.

Usage: python scripts/diagnose_segments.py <video> [--preset NAME]
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
fps = meta.fps if meta.fps > 0 else 30.0
print(f"{os.path.basename(inp)}: {meta.width}x{meta.height} @ {fps:.0f}fps, "
      f"{meta.total_frames} frames, {meta.duration:.1f}s  (preset: {preset})")

an = FaceAnalyzer(cfg)
dets, _ = an.analyze(meta)
an.close()
cuts = detect_scene_cuts(inp, cfg["scene_threshold"], cfg["min_scene_len_frames"])
intents = SpeakerTracker(cfg, meta.width, meta.height).run(dets, cuts)

# segment boundaries = [0, cut0, cut1, ..., N]
bounds = [0] + [c for c in cuts if 0 < c < len(intents)] + [len(intents)]
bounds = sorted(set(bounds))


def kind_of(i):
    # Layouts after the "show every reactor" redesign:
    #   split-N        : N reactors, each in their own grid cell (N=2..4)
    #   reactor-punch  : exactly 1 reactor in a 3+ scene -> punch-in on them
    #   group/two-shot : a FOCUS crop with no single subject (group centroid-fit OR a 2-up two-shot)
    #   focus          : ordinary single-subject follow (SOLO/DUAL)
    #   hold           : nobody to follow
    if i.kind == FramingKind.SPLIT:
        return f"split-{len(i.split_targets) if i.split_targets else 0}"
    if i.focus_target is None:
        return "hold"
    if i.active_id is not None:
        return "reactor-punch" if i.mode.value == "group" else "focus"
    return "group/two-shot"


print(f"\n{'seg':>3} {'t_start':>7} {'t_end':>6} {'frames':>6}  {'heads(avg/max)':>14}  "
      f"{'mode':>6}  what-it-framed")
print("-" * 88)
for s in range(len(bounds) - 1):
    a, b = bounds[s], bounds[s + 1]
    seg = intents[a:b]
    if not seg:
        continue
    heads = [len(dets[f].faces) for f in range(a, b) if f < len(dets)]
    avg_h = sum(heads) / len(heads) if heads else 0
    max_h = max(heads) if heads else 0
    mode = Counter(i.mode.value for i in seg).most_common(1)[0][0]
    kinds = Counter(kind_of(i) for i in seg)
    kdesc = ", ".join(f"{k} {100*v/len(seg):.0f}%" for k, v in kinds.most_common())
    print(f"{s:>3} {a/fps:>7.1f} {b/fps:>6.1f} {b-a:>6}  {avg_h:>6.1f}/{max_h:<6}  "
          f"{mode:>6}  {kdesc}")

import numpy as np
from backend.reframer.speaker import SpeakerTracker as _ST

# REACTION signal (appearance) reality check — THE signal that now drives the split. For every
# frame, score each live track with the engine's own reaction_score() (appearance-motion spine +
# speaking + head motion) and report the distribution + how many people clear reaction_threshold
# (= R, the reactor count that picks the layout). This is the read-out to calibrate
# reaction_threshold from: if static onlookers sit above it, the engine over-splits.
react_thr = cfg.get("reaction_threshold", 0.012)
st_r = _ST(cfg, meta.width, meta.height)
cut_set = set(cuts)
all_scores, top_scores_r, r_counts = [], [], []
for fd in dets:
    if fd.frame_num in cut_set:
        st_r._reset_shot()
    st_r._update_tracks(fd)
    live = [t for t in st_r._tracks if fd.frame_num - t.last_seen <= st_r.coast_frames]
    if not live:
        continue
    scores = [st_r.reaction_score(t) for t in live]
    all_scores.extend(scores)
    top_scores_r.append(max(scores))
    r_counts.append(sum(1 for s in scores if s >= react_thr))
if all_scores:
    a = np.array(all_scores)
    print(f"\nREACTION signal (appearance, the split driver) — {len(all_scores)} track-frames:")
    print(f"  per-track score:  median={np.median(a):.4f}  p75={np.percentile(a,75):.4f}  "
          f"p90={np.percentile(a,90):.4f}  max={a.max():.4f}   (reaction_threshold={react_thr})")
    print(f"  track-frames clearing threshold: {int((a>=react_thr).sum())} "
          f"({100*(a>=react_thr).mean():.0f}% of all tracks)")
    rc = np.array(r_counts)
    hist = {n: int((rc == n).sum()) for n in range(0, 5)}
    plus = int((rc >= 5).sum())
    print(f"  reactors/frame R (raw, pre-hysteresis): "
          + "  ".join(f"R={n}:{100*v/len(rc):.0f}%" for n, v in hist.items())
          + (f"  R>=5:{100*plus/len(rc):.0f}%" if plus else ""))

# speaking-score reality check: in GROUP frames, what's the top reactor's score and its lead
# over the runner-up? Tells us whether a dominant reactor EXISTS in the mouth signal (and thus
# whether group_dominant_threshold/margin are reachable) before we tune them.
thr = cfg.get("group_dominant_threshold", 0.012)
mar = cfg.get("group_dominant_margin", 0.006)
win = int(cfg["mouth_window_frames"])
# rebuild per-frame track speaking scores by re-running, capturing live tracks each frame
st = _ST(cfg, meta.width, meta.height)
top_scores, leads, mouth_seen = [], [], 0
cut_set = set(cuts)
for fd in dets:
    if fd.frame_num in cut_set:
        st._reset_shot()
    st._update_tracks(fd)
    live = [t for t in st._tracks if fd.frame_num - t.last_seen < st.mode_hc_window]
    if any(d.mouth_open > 0 for d in fd.faces):
        mouth_seen += 1
    if len(live) >= 3:
        ss = sorted((t.speaking_score(win) for t in live), reverse=True)
        top_scores.append(ss[0])
        leads.append(ss[0] - ss[1])
if top_scores:
    ts = np.array(top_scores); ld = np.array(leads)
    print(f"\nGROUP-frame speaking signal ({len(top_scores)} frames w/ 3+ live tracks):")
    print(f"  top reactor score:  median={np.median(ts):.4f}  p90={np.percentile(ts,90):.4f}  "
          f"max={ts.max():.4f}   (threshold={thr})")
    print(f"  lead over runner-up: median={np.median(ld):.4f}  p90={np.percentile(ld,90):.4f}  "
          f"max={ld.max():.4f}   (margin={mar})")
    print(f"  frames clearing BOTH thr & margin: {int(((ts>=thr)&(ld>=mar)).sum())} "
          f"({100*((ts>=thr)&(ld>=mar)).mean():.1f}% of 3+ frames)")
    print(f"  frames where ANY face had mouth_open>0: {mouth_seen} "
          f"({100*mouth_seen/len(dets):.1f}% of all frames)")

# MOTION reality check: since mouth is dead, can head/body velocity drive the reactor pick?
st2 = _ST(cfg, meta.width, meta.height)
top_spd, spd_lead = [], []
for fd in dets:
    if fd.frame_num in cut_set:
        st2._reset_shot()
    st2._update_tracks(fd)
    live = [t for t in st2._tracks if fd.frame_num - t.last_seen < st2.mode_hc_window]
    if len(live) >= 3:
        spds = sorted(((t.vx**2 + t.vy**2) ** 0.5 / meta.width for t in live), reverse=True)
        top_spd.append(spds[0]); spd_lead.append(spds[0] - spds[1])
if top_spd:
    sp = np.array(top_spd); sl = np.array(spd_lead)
    print(f"\nGROUP-frame MOTION signal (normalised head speed, /frame-width):")
    print(f"  top mover speed:  median={np.median(sp):.5f}  p90={np.percentile(sp,90):.5f}  "
          f"max={sp.max():.5f}")
    print(f"  lead over runner: median={np.median(sl):.5f}  p90={np.percentile(sl,90):.5f}  "
          f"max={sl.max():.5f}")

# LAYOUT CHURN: how often does the framing token change (each change = a hard relayout the viewer
# sees as a jump) and how many frames request a hard snap. Lower = calmer. This is the number to
# watch when tuning react_grid_hold_frames / react_layout_shrink_frames.
tokens = [kind_of(i) for i in intents]
changes = sum(1 for a, b in zip(tokens, tokens[1:]) if a != b)
snaps = sum(1 for i in intents if i.allow_snap)
secs = len(intents) / fps if fps else 1
print(f"LAYOUT CHURN: {changes} layout changes ({changes/secs:.1f}/s), "
      f"{snaps} hard-snap frames ({100*snaps/len(intents):.0f}%)")

# overall: how often did the dominant-reactor path actually fire?
reactor = sum(1 for i in intents if i.mode.value == "group" and i.active_id is not None)
groupfit = sum(1 for i in intents if i.mode.value == "group" and i.active_id is None)
print("-" * 88)
print(f"GROUP-reactor punch-in: {reactor} frames ({100*reactor/len(intents):.1f}%)  |  "
      f"group-fit: {groupfit} frames ({100*groupfit/len(intents):.1f}%)")
