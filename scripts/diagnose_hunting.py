"""Quantify crop 'hunting' on a real video: windows where the crop moves a lot
back-and-forth without net travel (the wander symptom). Prints the worst windows
by timecode so we can confirm the fix / find remaining hot spots.

Usage: python scripts/diagnose_hunting.py <video>
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CONFIG
from backend.pipeline import probe_meta
from backend.reframer.detector import FaceAnalyzer
from backend.reframer.scene_detector import detect_scene_cuts
from backend.reframer.speaker import SpeakerTracker
from backend.reframer.crop_planner import CropPlanner
from backend.models import FramingKind


def tc(frame, fps):
    s = frame / fps
    return f"{int(s // 60)}:{s % 60:05.2f}"


def main():
    inp = sys.argv[1]
    meta = probe_meta(inp)
    fps = meta.fps or 30.0
    print(f"{meta.width}x{meta.height} @ {fps:.1f}fps, {meta.total_frames} frames")

    analyzer = FaceAnalyzer(CONFIG)
    detections, motion = analyzer.analyze(meta)
    analyzer.close()
    cuts = detect_scene_cuts(inp, CONFIG["scene_threshold"], CONFIG["min_scene_len_frames"])
    intents = SpeakerTracker(CONFIG, meta.width).run(detections, cuts)
    plans = CropPlanner(CONFIG, meta).plan(intents, motion)

    # crop-center x per FOCUS frame (None for split/absent so we don't count those)
    cx = []
    for p in plans:
        if p.kind == FramingKind.FOCUS and p.crop is not None:
            cx.append(p.crop.x + p.crop.width / 2)
        else:
            cx.append(None)

    win = int(round(fps))          # 1-second windows
    cut_set = set(cuts)
    results = []
    for s in range(0, len(cx) - win):
        seg = cx[s:s + win]
        if any(v is None for v in seg):
            continue
        if any((s + k) in cut_set for k in range(win)):   # skip windows containing a cut
            continue
        deltas = [seg[k + 1] - seg[k] for k in range(len(seg) - 1)]
        path = sum(abs(d) for d in deltas)                # total distance travelled
        net = abs(seg[-1] - seg[0])                       # net displacement
        reversals = sum(1 for k in range(len(deltas) - 1)
                        if deltas[k] * deltas[k + 1] < 0)  # direction flips
        wasted = path - net                               # back-and-forth motion
        # hunting = lots of wasted motion + many reversals
        results.append((wasted, reversals, path, net, s))

    results.sort(reverse=True)
    print(f"\nWorst 8 one-second windows by wasted (back-and-forth) motion:")
    print(f"{'time':>8}  {'wasted_px':>9}  {'reversals':>9}  {'path_px':>8}  {'net_px':>7}")
    for wasted, reversals, path, net, s in results[:8]:
        flag = "  <-- HUNTING" if (wasted > 40 and reversals >= 5) else ""
        print(f"{tc(s, fps):>8}  {wasted:9.1f}  {reversals:9d}  {path:8.1f}  {net:7.1f}{flag}")

    hunts = [r for r in results if r[0] > 40 and r[1] >= 5]
    print(f"\n{len(hunts)} window(s) flagged as hunting (wasted>40px & >=5 reversals).")


if __name__ == "__main__":
    main()
