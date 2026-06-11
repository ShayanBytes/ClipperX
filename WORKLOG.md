# ClipperX — Work Log

> A running, chronological record of what was built, why, and what's next — so **any
> model or session can pick up with the full picture**. Newest entry on top.
>
> **How to read this:** `DESIGN.md` is the *spec* (source of truth for the engine).
> This file is the *history + current state*. `config.py` holds every tunable knob.
> When you finish a unit of work, add a dated entry at the top using the template at
> the bottom, and keep `DESIGN.md` + the memory index in sync.

## Current state (snapshot)

- **Engine phase:** auto-reframe only (16:9 → 9:16). No moment-finder / subtitles yet.
- **Done:** L0 detection (pose framing + weighted head-centre anchor + lazy face mouth +
  motion centroid), scene cuts, recovery/anti-hunting (§6), L2 scene-mode machine
  (HOLD/SOLO/DUAL/GROUP, asymmetric hysteresis), DUAL two-shot/split, **Presets** layer
  (`presets.py`), and **now the spring camera + zoom primitive (#4)**.
- **Roadmap (DESIGN.md §8):** #1 recovery ✅ · #2 mode machine ✅ · #3 two-shot DUAL ✅ ·
  **#4 spring camera + zoom ✅ (this entry)** · next = **#5 importance blend**, then
  **#6 GROUP centroid-fit**.
- **Tests (all green):** `scripts/test_recovery.py` (A–E), `scripts/test_presets.py`
  (10/10), `scripts/test_spring.py` (spring + zoom). Run them with
  `.venv/Scripts/python scripts/<name>.py`.
- **Unvalidated on real footage:** the DUAL two-shot/split path (need a real 2-person
  clip in `Imports/`); and the new spring feel + any future zoom-in driver need the
  user's eyes on a real render. Diagnose visually with
  `.venv/Scripts/python scripts/debug_overlay.py <vid> [--preset NAME]`.

---

## 2026-06-11 — Roadmap #4: spring camera + zoom primitive

**What & why.** Replaced the raw EMA easing in the L4 virtual camera with a
**critically-damped spring** (PD controller) and added the **zoom primitive**. EMA eases
in but stops abruptly and has no real velocity; a critically-damped spring eases *in and
out* with a single responsiveness knob and **no overshoot** — the cinematic feel the
design (§5) called for. Zoom is the move that was missing entirely: the engine had only
cut + pan, so every "scope changed" beat (emphasis punch-in) was impossible.

**Changes.**
- `backend/reframer/crop_planner.py`: new `_Spring` helper (analytic critically-damped
  update, stable at any rate, carries velocity). The focus path now drives **three
  springs** — pan-x, pan-y, and zoom — instead of EMA. Dead-zone, speed-limit, and
  cut-snap are all preserved (the recovery invariants depend on them). Crop size is now
  **per-frame** = `base_crop · zoom`; the renderer already rescales any box, so no
  renderer change was needed. Split path still uses the old EMA (static-ish, out of scope).
- `backend/reframer/speaker.py`: `FrameIntent` gained `target_zoom: float = 1.0`
  (optional, default = no change). **No speaker logic requests a zoom yet** — the
  primitive is in place; a driver (emphasis punch-in / GROUP fit) lands with #5/#6.
- `config.py`: new `camera_responsiveness` (pan ω), `zoom_responsiveness` (slower ω),
  `min_zoom` (tightest punch-in), `zoom_max_rate_per_frame` (cap on Δzoom/frame).

**Geometric note (important — don't chase an impossible move).** The full-height 9:16
crop is **already the widest** 9:16 region extractable from a 16:9 source. So the zoom
primitive can only **punch IN** (`z ≤ 1`) and return to base. "Zoom out past base to
contain two people" is **geometrically impossible** in strict 9:16 — that is exactly why
SPLIT exists. Zoom-out-to-contain (§10 table) only applies once we allow letterbox/blurred
bars, which is a separate future decision, not part of #4.

**Verification.** `scripts/test_spring.py` (new): spring reaches target with no overshoot,
respects the per-frame speed limit, settles; zoom punches in smoothly, is rate-limited,
snaps on a cut, and stays clamped/centred. `scripts/test_recovery.py` A–E still pass
(spring keeps the speed-limit + snap-only-at-cut invariants). `scripts/test_presets.py`
10/10.

**Next.** #5 importance blend (add motion/size/face_conf to selection only if mouth-only
misbehaves on real footage), then #6 GROUP centroid-fit. A natural first *consumer* of the
new zoom primitive: a slow emphasis punch-in on a sustained lone speaker.

---

## 2026-06-11 — Presets layer (built alongside the roadmap)

Content-type policy profiles that **tune** the mode machine (they don't replace it). See
`presets.py`, DESIGN.md §9. Profiles: `auto` (default no-op), `one_person`, `two_podcast`,
`two_dynamic`, `group_podcast`, `group_dynamic`. Selected via `reframe(..., preset=NAME)` /
`--preset NAME` (in both the pipeline CLI and `debug_overlay.py`); GUI dropdown is future.
Verified by `scripts/test_presets.py` (10/10). Sports/object salience is deliberately a
separate future module, not a preset.

---

### Entry template (copy when adding work)

```
## YYYY-MM-DD — <short title>

**What & why.** <one paragraph: the change and the reasoning>
**Changes.** <files touched + what changed in each>
**Verification.** <tests run + result>
**Next.** <the immediate logical follow-up>
```
