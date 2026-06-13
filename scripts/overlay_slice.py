"""Render a debug overlay for a SLICE of a clip, reusing cached detections (from tune_importance.py).

Skips the slow detector pass entirely by loading `<clip>.dets.pkl`. Applies the current CONFIG
(so set importance_select / importance_keep_ratio there or via the flags below), runs the real
speaker + planner, and writes an overlay for only [--start, --end] seconds — so you can watch the
gate's framing decisions on a short, representative chunk instead of the whole 19 minutes.

If no slice is given it auto-picks the 90s window where the importance gate changes the most cells
vs gate-off (the most informative thing to watch).

Usage:
    python scripts/overlay_slice.py <video> [--ratio 0.70] [--start S] [--end S] [--off]
"""
import os, sys, pickle

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.pipeline import probe_meta
from backend.reframer.speaker import SpeakerTracker
from backend.reframer.crop_planner import CropPlanner
from backend.models import FramingKind
from config import CONFIG

GREEN = (0, 220, 0); YELLOW = (0, 220, 220); RED = (40, 40, 230); CYAN = (230, 200, 0)

args = sys.argv[1:]


def take(flag, default=None, cast=str):
    if flag in args:
        i = args.index(flag)
        if flag == "--off":
            args.remove(flag); return True
        v = args[i + 1]; del args[i:i + 2]; return cast(v)
    return default


gate_off = take("--off", False)
ratio = take("--ratio", None, float)
start_s = take("--start", None, float)
end_s = take("--end", None, float)
inp = args[0]

meta = probe_meta(inp)
fps = meta.fps if meta.fps > 0 else 30.0
cache = inp + ".dets.pkl"
if not os.path.exists(cache):
    print(f"No cache {os.path.basename(cache)} — run tune_importance.py first."); sys.exit(1)
with open(cache, "rb") as fh:
    dets, cuts = pickle.load(fh)

cfg = dict(CONFIG)
cfg["importance_select"] = not gate_off
if ratio is not None:
    cfg["importance_keep_ratio"] = ratio


def cells(intent):
    if intent.kind == FramingKind.SPLIT:
        return len(intent.split_targets) if intent.split_targets else 0
    return 1 if intent.focus_target is not None else 0


# auto-pick the most informative 90s window: max sum |cells_on - cells_off| over the window
if start_s is None or end_s is None:
    off_cfg = dict(CONFIG); off_cfg["importance_select"] = False
    on_cfg = dict(CONFIG); on_cfg["importance_select"] = True
    if ratio is not None:
        on_cfg["importance_keep_ratio"] = ratio
    i_off = SpeakerTracker(off_cfg, meta.width, meta.height).run(dets, cuts)
    i_on = SpeakerTracker(on_cfg, meta.width, meta.height).run(dets, cuts)
    diff = [abs(cells(a) - cells(b)) for a, b in zip(i_off, i_on)]
    win = int(90 * fps)
    run_sum = sum(diff[:win])
    best_sum, best_start = run_sum, 0
    for s in range(1, len(diff) - win):
        run_sum += diff[s + win - 1] - diff[s - 1]
        if run_sum > best_sum:
            best_sum, best_start = run_sum, s
    start_s = best_start / fps
    end_s = (best_start + win) / fps
    print(f"auto-picked slice: {start_s:.0f}-{end_s:.0f}s (max gate effect)")

f0, f1 = int(start_s * fps), int(end_s * fps)
intents = SpeakerTracker(cfg, meta.width, meta.height).run(dets, cuts)
plans = CropPlanner(cfg, meta).plan(intents, [])  # motion only affects HOLD drift; [] -> None/frame (guarded)

base_focus_w = min(round(meta.height * cfg["output_width"] / cfg["output_height"]), meta.width)
tag = "off" if gate_off else f"on{int((ratio or cfg['importance_keep_ratio'])*100)}"
base = os.path.splitext(os.path.basename(inp))[0]
outp = os.path.join(cfg["export_dir"], f"{base}_gate_{tag}_{int(start_s)}-{int(end_s)}.mp4")
os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)

cap = cv2.VideoCapture(inp)
cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
writer = cv2.VideoWriter(outp, cv2.VideoWriter_fourcc(*"mp4v"), fps, (meta.width, meta.height))
cut_set = set(cuts)
print(f"rendering frames {f0}-{f1}  gate={'OFF' if gate_off else 'ON'} "
      f"ratio={cfg['importance_keep_ratio']}  -> {os.path.basename(outp)}")

for i in range(f0, f1):
    ret, frame = cap.read()
    if not ret:
        break
    fd = dets[i] if i < len(dets) else None
    intent = intents[i] if i < len(intents) else None
    plan = plans[i] if i < len(plans) else None
    if fd:
        rthr = cfg.get("reaction_threshold", 0.012)
        for d in fd.faces:
            hot = d.react >= rthr
            cv2.circle(frame, (int(d.cx), int(d.cy)), 6, RED if hot else YELLOW, -1)
            cv2.putText(frame, f"{d.react*100:.0f}", (int(d.cx) + 8, int(d.cy) - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, RED if hot else YELLOW, 1)
    mode = intent.mode.value.upper() if intent else "?"
    if plan and plan.kind == FramingKind.SPLIT and plan.cells:
        for box in plan.cells:
            cv2.rectangle(frame, (box.x, box.y), (box.x + box.width, box.y + box.height), CYAN, 2)
        cv2.putText(frame, f"{mode}/SPLIT x{len(plan.cells)}", (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, CYAN, 2)
    elif plan and plan.crop:
        b = plan.crop
        absent = intent is not None and intent.focus_target is None
        color = RED if absent else GREEN
        cv2.rectangle(frame, (b.x, b.y), (b.x + b.width, b.y + b.height), color, 2)
        who = "hold" if absent else f"id={intent.active_id if intent else '?'}"
        cv2.putText(frame, f"{mode}/{who} z={int(round(100*b.width/base_focus_w))}%", (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    if i in cut_set:
        cv2.putText(frame, "CUT", (meta.width - 90, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    writer.write(frame)

cap.release(); writer.release()
print(f"Saved: {outp}")
