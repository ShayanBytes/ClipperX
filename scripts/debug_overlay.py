"""
debug_overlay.py - visualise the engine's decisions on the SOURCE video.

Draws, per frame: detected faces, the active-speaker marker, and the chosen crop
region(s). Lets you judge tracking / switching / split without watching the
squished vertical output. Writes <name>_debug.mp4 next to the input.

Usage:  python scripts/debug_overlay.py <input_video> [output_video]
"""
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.pipeline import probe_meta
from backend.reframer.detector import FaceAnalyzer
from backend.reframer.scene_detector import detect_scene_cuts
from backend.reframer.speaker import SpeakerTracker
from backend.reframer.crop_planner import CropPlanner
from backend.models import FramingKind
from config import CONFIG
from presets import apply_preset

GREEN = (0, 220, 0)
YELLOW = (0, 220, 220)
RED = (40, 40, 230)
CYAN = (230, 200, 0)


def main():
    args = sys.argv[1:]
    preset = "auto"
    if "--preset" in args:
        i = args.index("--preset")
        preset = args[i + 1]
        del args[i:i + 2]
    if not args:
        print("Usage: python scripts/debug_overlay.py <input_video> [output_video] [--preset NAME]")
        sys.exit(1)
    inp = args[0]
    base = os.path.splitext(os.path.basename(inp))[0]
    outp = args[1] if len(args) > 1 else os.path.join(CONFIG["export_dir"], f"{base}_debug.mp4")
    os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)

    cfg = apply_preset(CONFIG, preset)
    meta = probe_meta(inp)
    base_focus_w = min(round(meta.height * cfg["output_width"] / cfg["output_height"]), meta.width)
    print(f"Analyzing {meta.width}x{meta.height} @ {meta.fps:.1f}fps, "
          f"{meta.total_frames} frames  (preset: {preset})")

    analyzer = FaceAnalyzer(cfg)
    detections, motion = analyzer.analyze(meta)
    analyzer.close()
    cuts = detect_scene_cuts(inp, cfg["scene_threshold"], cfg["min_scene_len_frames"])
    print(f"Scene cuts: {len(cuts)}")
    intents = SpeakerTracker(cfg, meta.width, meta.height).run(detections, cuts)
    plans = CropPlanner(cfg, meta).plan(intents, motion)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(outp, fourcc, meta.fps, (meta.width, meta.height))
    cap = cv2.VideoCapture(inp)
    i = 0
    cut_set = set(cuts)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        fd = detections[i] if i < len(detections) else None
        intent = intents[i] if i < len(intents) else None
        plan = plans[i] if i < len(plans) else None

        if fd:
            react_thr = cfg.get("reaction_threshold", 0.012)
            for d in fd.faces:
                # a face above the reaction threshold (by appearance motion) is a candidate reactor:
                # mark it red-hot so the threshold can be judged by eye against the split decisions.
                hot = d.react >= react_thr
                cv2.circle(frame, (int(d.cx), int(d.cy)), 7, RED if hot else YELLOW, -1)
                cv2.putText(frame, f"r={d.react*100:.0f}", (int(d.cx) + 10, int(d.cy) - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, RED if hot else YELLOW, 2)

        mode = intent.mode.value.upper() if intent is not None else "?"
        if plan and plan.kind == FramingKind.SPLIT and plan.cells:
            for box in plan.cells:
                cv2.rectangle(frame, (box.x, box.y), (box.x + box.width, box.y + box.height), CYAN, 3)
            cv2.putText(frame, f"{mode} / SPLIT x{len(plan.cells)}", (40, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, CYAN, 3)
        elif plan and plan.crop:
            b = plan.crop
            absent = intent is not None and intent.focus_target is None
            color = RED if absent else GREEN
            cv2.rectangle(frame, (b.x, b.y), (b.x + b.width, b.y + b.height), color, 3)
            who = "hold" if absent else f"id={intent.active_id if intent else '?'}"
            zpct = int(round(100 * b.width / base_focus_w))   # <100% = punched in (emphasis/zoom)
            cv2.putText(frame, f"{mode} / {who}  z={zpct}%", (40, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)

        if i in cut_set:
            cv2.putText(frame, "CUT", (meta.width - 180, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 3)

        writer.write(frame)
        i += 1
        if i % 60 == 0:
            print(f"  {i}/{meta.total_frames}")

    cap.release()
    writer.release()
    print(f"Saved debug overlay: {outp}")


if __name__ == "__main__":
    main()
