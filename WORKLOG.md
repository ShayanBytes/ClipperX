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
  (HOLD/SOLO/DUAL/GROUP, asymmetric hysteresis), DUAL two-shot/split, **Presets** layer,
  the **spring camera + zoom primitive (#4)**, the **emphasis punch-in** (first zoom
  driver), **GROUP centroid-fit (#6)**, and the **motion-driven dominant-reactor punch-in
  (#5 importance blend)**. **V1 mode coverage is now complete.**
- **Roadmap (DESIGN.md §8):** #1 recovery ✅ · #2 mode machine ✅ · #3 two-shot DUAL ✅ ·
  **#4 spring camera + zoom ✅** · emphasis punch-in ✅ · **#5 importance blend ✅** (built as
  the GROUP dominant-reactor pick; mouth-only DID misbehave on 4K → switched to motion-driven,
  `group_motion_weight=1.0`) · **#6 GROUP centroid-fit ✅**.
- **Tests (all green):** `test_recovery.py` (A–E), `test_presets.py` (10), `test_spring.py`
  (13), `test_emphasis.py` (9), `test_group.py` (16). Run:
  `.venv/Scripts/python scripts/<name>.py`.
- **The big remaining gap is VALIDATION, not code.** Everything below is unvalidated on
  real footage and needs the user's eyes (drop a clip in `Imports/`, then
  `.venv/Scripts/python scripts/debug_overlay.py <vid> [--preset NAME]` — overlay shows
  mode, who, `z=NN%`):
  1. DUAL two-shot/split on a real 2-person clip (never tested on real footage).
  2. Spring camera *feel*.
  3. Emphasis push-in *taste* (8% / 3s on every held solo — too much? too mechanical?).
  4. GROUP centroid-fit on a real 3+ scene.
  5. **GROUP dominant-reactor pick** — does motion punch in on the *right* reactor (segs 1/4/6
     of `Multiple People.mp4`), and does it feel deliberate or jumpy? (`exports/Multiple
     People_debug.mp4`, freshly rendered.)

---

## 2026-06-13 — "Show every reactor" validated: tests, calibration instruments, layout stability

**Context.** Picking up the YuNet + "show every reactor" redesign the prior session left mid-flight
(detector→speaker→planner→renderer were wired; the appearance `react` cue was threaded through;
all 5 old suites green). Three things were still open: a test for the headline split, diagnostics
that expose the NEW signal, and threshold calibration on real footage.

**1. Test for the reaction-count split (was missing entirely).** New `scripts/test_reaction.py`
(23 checks, green) drives the REAL `SpeakerTracker` with injected `Detection(react=...)`:
4 reactors→2×2 quad, 3→3-cell, 2-far→2-way split, 2-close→two-shot FOCUS, 1→punch-in@0.72,
0→centroid-fit, plus hold/release/shrink hysteresis and snap-on-entry. Lesson baked into the test:
`reaction_score` is a **windowed mean**, so a reactor stays "hot" ~`mouth_window_frames` after it
stops before the release/shrink debounces even start — the collapse timing is window+release+shrink.

**2. Diagnostics + overlay now expose the appearance signal (the real split driver).**
`diagnose_segments.py`: new REACTION-signal section (per-track `reaction_score` distribution +
reactor-count R histogram), corrected `kind_of` labels (split-N / reactor-punch / group/two-shot /
focus / hold), and a LAYOUT-CHURN line (layout-token changes/s + hard-snap %). `debug_overlay.py`:
each face now prints `r=NN` and turns RED when it clears `reaction_threshold`, so the gate is
judgeable by eye.

**3. Calibration finding (measured, decided with the user).** On `Multiple People.mp4` the YuNet
switch **solved the detection gap**: group segs 0/4/6/10 now detect **4/4 faces** and render a
**split-4 quad 91–97%** — the old pose detector found 3+ heads ~3% and dropped the 4th person, so
the user's #1 complaint is now structurally fixed. BUT the appearance threshold (0.012) doesn't
*discriminate*: **88% of all track-frames clear it** (median score 0.064, ~5× thr) because 4K
baseline face-pixel churn is ~0.05–0.16. So "reacting" ≈ "detected". **User chose: keep the low
threshold — show everyone detected** (matches "don't neglect anyone"); the threshold is now a
presence/liveness gate, not a discriminator. (A relative/per-frame-median reactor test was the
alternative, declined for now.)

**4. Layout stability (user: "stabilize now" — the 'moved randomly' complaint).** Root cause: the
grid geometry changes with the cell COUNT (3-cell ≠ 4-cell quad), so on segments where detection
fluctuates (seg5 1.9/4 avg, seg9 2.2/3) every count change is a hard relayout. Two debounces, both
in `speaker.py`: (a) **`react_grid_hold_frames`** (45) — a latched grid-reactor is retained
(coasted at last position) far longer than the normal `coast_frames`, so a brief blink doesn't drop
their cell (`_retention()` gates both track-pruning and the live set); (b) **`react_layout_shrink_frames`**
(30) — a committed displayed cell-count (`_commit_shown`) grows immediately (never leave a present
reactor out) but shrinks only after the lower count persists, and cells are filled from the most
salient live people so a held-open cell stays occupied. **Measured on Multiple People.mp4: layout
changes 62→45 (−27%), hard-snap frames 48→38 (−21%).**

**Changes.** `scripts/test_reaction.py` (new). `scripts/diagnose_segments.py` (react section,
kind_of, churn line). `scripts/debug_overlay.py` (per-face r=NN + hot color). `backend/reframer/
speaker.py` (`_retention`, `_commit_shown`, retention-aware `live`/pruning, decision routes through
committed `shown_n`). `config.py` (`react_grid_hold_frames`, `react_layout_shrink_frames` + notes
that 0.012 is now a presence gate). All 6 suites green (recovery A–E, presets 10, spring 13,
emphasis 9, group 16, reaction 23).

**VALIDATED (2026-06-13, later same day).** User replaced `Imports/just 4 people scene .mp4` with a
genuine 4-person scene (3840×2160, 55f/1.1s). Results: YuNet detects **4.0/4 every frame**; engine
commits **GROUP → split-4 quad 85%** (first ~8f centroid-fit while reactors latch via reaction_hold),
R=4 98%, LAYOUT CHURN 1 change/1 snap. Full pipeline `reframe()` → `exports/just4_vertical.mp4`
(real 9:16 quad); overlay `exports/just4_debug.mp4`. **User watched it and said it's "perfect."**

**OPEN QUESTION raised by user (next thing to design).** Current layout shows EVERYONE detected
(up to `max_split_cells`=4), because the threshold is a presence gate. The user asked: what about a
frame with 4–8 people where only 1–2 are *giving content* (the host/speaker) and the rest are
passive? Today the engine would still split to show up to 4 of them — it does NOT select the
*important* people. This is exactly the **relative/importance-based reactor selection** that was
deferred (Option B from the 2026-06-13 calibration fork). To build it we need: (a) a discriminator
— e.g. reactor counts only if its score exceeds the per-frame median + margin (auto-normalises the
4K baseline churn), and/or weight by active-speaker (jaw) + face size (foreground); (b) a decision
on layouts >4 people (cap at top-N vs a 2×3/3×3 grid) and whether a single cell may hold a *pair*
(today every cell = exactly ONE face). **Blocked on a representative clip** (many people, only a
few active) to build + tune against — the current 4-person clip has all 4 active so it can't show
discrimination. Layout mechanics today: #cells = #reactors shown, 1→punch-in, 2→two-shot if they
co-fit else 2 stacked rows, 3→two-top+one-wide, 4→2×2 quad, 5+→top-4 by score (rest dropped).

---

## 2026-06-12 — GROUP reactor pick switched to MOTION-driven (completes the #5 importance blend)

**What & why.** Finishing the thread the previous entry left open: the dominant-reactor punch-in
was speech-keyed, but the mouth signal is dead on this 4K footage, so it fired on only **4 frames
(0.2%)** — effectively never. Read the motion numbers `diagnose_segments.py` already prints: over
593 group frames the top **mover's** head-speed leads the runner-up by p90 **0.024** of frame-width
(vs the speaking lead's p90 = **0.0000**). Motion clearly separates a reactor where speech can't, so
flipped `_group_importance` to motion-driven.

**Two-step change, both measured not guessed.**
1. `group_motion_weight` 0.0 → **1.0**. Importance is now head VELOCITY (speech stays an additive
   bonus where it survives, so the mouth-driven synthetic tests are untouched — their heads are
   stationary so the motion term is 0). The old thresholds (`threshold` 0.012 / `margin` 0.006)
   already sit between the measured motion median (0.0045) and p90 (0.033), so they fire only on a
   genuinely-animated reactor — no retune needed.
2. **But it still fired 4 frames.** Traced the gate: motion IS dominant 27.2% of group frames, but
   reactions are **bursty** — the same track stays top-mover for only 5–11 frames, so the 12-frame
   `group_dominant_hold_frames` almost never accumulated (1 streak cleared it in the whole clip).
   Swept hold against a full tracker run: 12→4 frames/1 engage · 10→29/3 · **8→52/4 distinct
   reactors** · 6→95/6. Set `group_dominant_hold_frames` 12 → **8** (≈0.27s @30fps) — the
   conservative end that still fires, with the 18-frame release keeping it deliberate, not twitchy.

**Result (per-segment, `diagnose_segments.py`).** GROUP-reactor punch-in now fires across segs
**1 (67%), 4 (12%), and 6 (8%)** — seg 6 (17.6–22.4s) is the exact 4-person reaction scene the user
said neglected the 4th person. Was 0.2% total; now reaches the genuinely-GROUP reaction frames. The
0.72 punch-in also re-enables vertical (y) composition there.

**Changes.** `config.py`: `group_motion_weight` 1.0, `group_dominant_hold_frames` 8, +rewritten
threshold/margin/motion comments documenting the measured scale. `speaker.py`: `_group_importance`
docstring (motion is now the spine). `DESIGN.md`: GROUP table row + §8 #5 now ✅ (motion-driven).

**Verification.** All 5 suites green (group 16, emphasis 9, spring 13, recovery A–E, presets 10) —
the additive blend keeps the speech-driven synthetic tests passing. Re-rendered
`exports/Multiple People_debug.mp4` (363 MB) for the user.

**Next.** **User to watch the overlay** and judge the reactor picks in segs 1/4/6: right person?
deliberate or jumpy? If reactor identity flickers, the principled next step is a short windowed
motion signal (smooth the per-track speed like `speaking_score` smooths mouth) so streaks lengthen
and `hold` can rise again. Then Phase 2 (scene 3: edge-release vs framing blank space when a subject
walks off + walking-together two-shot) and Phase 3 (scene 5: sports/object salience).

---

## 2026-06-12 — User footage feedback → dominant-reactor GROUP focus (#5) + detection finding

**Trigger.** User watched real reframed scenes and reported 5 issues: (1)&(4) a 4-person
reaction scene neglected the 4th person and "moved randomly"; wanted the engine to find and
cut to the **dominant reactor**; also noticed it only pans horizontally, never vertically.
(2) a 2-person scene was framed well (DUAL punch-in ✅). (3) a walk-and-track scene lost the
tracker and **cropped blank space**, and asked what to do when two people walk together.
(5) a football scene tracked the shooter but ignored the ball/keeper.

**Phase 0 — detection finding (measured, not assumed).** Bumped `max_people` 3→4. Re-ran
`diagnose_modes.py`: 4-head detection went 0%→0.1%, 3-head 3.5%→4.3% — **negligible**. The
4th person isn't being dropped by the cap; the **pose detector doesn't detect 3-4 simultaneous
people** in this footage. Tried lowering `min_pose/tracking_confidence` 0.4→0.25 to recover
them — it **backfired** (2-head 37.5%→18.1%, collapsed toward 1-head: in VIDEO mode a low
tracking floor makes the landmarker cling to one pose instead of re-detecting the rest).
Reverted to 0.4. **Conclusion: the reaction-scene lever is SELECTION among the 2-3 heads we do
get, not detection.** Kept `max_people=4` as cheap insurance. NOTE: much of the "4 people"
footage is actually committing **DUAL (44.2%)**, not GROUP (15.6%) — the detector sees 2 of
the 4 — so the reaction fix below only reaches the genuinely-GROUP frames until detection of
3+ improves.

**Phase 1 — dominant-reactor GROUP focus (this is DESIGN #5, finally justified by footage).**
GROUP no longer *always* centroid-fits. `speaker._group_decide`: rank tracks by
`_group_importance` (speaking-score std, + optional motion weight); if the top reactor clears
`group_dominant_threshold` AND leads the runner-up by `group_dominant_margin`, **punch in on
them** (reuse the active-speaker focus path: reacquire eases, a real hand-off snaps) at the
tighter `group_dominant_zoom` (0.72). Two-timescale hysteresis (`group_dominant_hold_frames`
to engage/hand-off, `group_dominant_release_frames` to fall back) stops reactor↔group flicker.
Nobody dominant → old centroid-fit. **The 0.72 punch-in also fixes the "only horizontal"
complaint**: a sub-full-height crop re-enables `crop_planner._pan_y` (at zoom=1 the crop is
full height and y-pan is dead by geometry).

**Changes.** `config.py`: `max_people` 4; new `group_dominant_*` block (7 keys).
`speaker.py`: `_group_decide` / `_group_importance` / `_group_fit_intent`, candidate+lock
hysteresis state (init + `_reset_shot`). `scripts/test_group.py`: +4 checks (C dominant
reactor→punch-in@0.72, D flag off→centroid, E nobody dominant→centroid).

**Verification.** `test_group.py` 16/16; recovery (A–E), presets, spring, emphasis all still
green. Real clip (`diagnose_modes.py`): dominant path fires (zoom min now **0.720**, was
0.920) but rarely (GROUP is only 15.6% of the clip). Debug overlay rendering for the user.

**Next.** User to watch `exports/MultiplePeople_debug.mp4` and judge the reactor pick + the
0.72 framing. Then Phase 2 (scene 3: edge-release so we stop framing blank space when a
subject walks off + walking-together two-shot) and Phase 3 (scene 5: sports/object salience).

---

## 2026-06-12 — User: "same as before" → root-caused via per-segment + signal diagnostics

**Why it looked unchanged.** Built `scripts/diagnose_segments.py` (per cut-to-cut segment:
time range, detected head avg/max, committed mode, what it framed) + a speaking/motion signal
read-out. Three hard findings on `Multiple People.mp4`, each measured not assumed:

1. **Mode classification was the real "neglected 4th person."** Reaction segments (e.g. seg6
   17.6–22.4s) detect up to 4 heads but only intermittently (avg ~2), so the exact-current-
   frame head-count kept committing **DUAL → framed ONE person**. Fix: count distinct tracks
   seen within a short window (`mode_headcount_window`=12 ≈0.4s), not just this frame. Result:
   seg6 DUAL→**GROUP 64%**, total group-fit 15.4%→**32.4%**. The whole group is now framed
   instead of locking one person + dropping three. `mode=1` reproduces old behaviour.

2. **The mouth/speaking signal is essentially DEAD on this footage.** In GROUP frames the top
   reactor's speaking-score median/p90 = **0.0000**; only **0.4% of ALL frames** had ANY face
   with mouth_open>0. At 4K with 4 small/distant people the FaceLandmarker almost never finds a
   face to attach a jawOpen to (`detector._attach_mouth` needs a face within 0.15·W of a pose).
   ⇒ **The dominant-reactor punch-in (Phase 1) CANNOT fire on this footage — it's speech-keyed
   and there is no speech signal.** The 4 frames it fired were noise. Not a tuning problem.

3. **Direction change (matches the user's own words).** A "reaction" here = visible MOTION
   (laugh/gesture/lean/head-turn), not lip-sync. The fix is to drive `_group_importance` by
   **head/body velocity** (the `vx/vy` already tracked; the `group_motion_weight` hook I built
   is currently 0), not mouth. Verifying motion signal exists/separates before committing.

**Changes so far.** `config.py`: `mode_headcount_window` (new). `speaker.py`: head-count for
mode now windowed. `scripts/diagnose_segments.py` (new). All 5 suites still 0 fails.

**Next.** Read the motion-signal numbers; if a dominant mover separates from the group, switch
the GROUP reactor pick to motion-driven (raise `group_motion_weight`, lower/replace the
speech threshold) and re-validate per-segment. THEN re-render the overlay for the user.

---

## 2026-06-11 — First real multi-person validation (`Multiple People.mp4`, 4K)

**Setup.** After the `_attach_mouth` fix, ran `debug_overlay.py` (→
`exports/MultiplePeople_debug.mp4`, 360 MB, for the user to watch) and the new
`scripts/diagnose_modes.py` for quantitative decisions. Clip = 3840×2160 @ 50 fps, 1700
frames, 34 s, 10 scene cuts.

**What worked (✅).**
- Engine runs **clean on 4K real footage** end-to-end; no crashes after the fix.
- **All four scene modes activate**: HOLD 0.7 % · SOLO 39.4 % · DUAL 44.2 % · GROUP 15.6 %.
  The L2 mode machine behaves on real video, not just synthetic.
- **Emphasis punch-in fires**: 13.1 % of frames punched in, zoom range exactly 0.92–1.00
  (the emphasis band) — the held-shot push-in works on real footage.
- Heads detected/frame: 0 → 4.6 % · 1 → 53.5 % · 2 → 38.5 % · 3 → 3.5 %.

**Two things to watch — need the user's eyes on the debug video (⚠️ candidates for tuning).**
1. **DUAL never "showed both."** Zero two-shots, zero splits across 752 DUAL frames — every
   DUAL frame punched in on one speaker. On a 2-person clip that *may* be correct (if they
   rarely both-talk at once), or it may mean `both_active_threshold` / `joint_hold_frames`
   are too strict, or co-fit never satisfied at this framing. **Watch:** when both people
   talk/laugh together, does it ever frame both? If not and it should, loosen the
   `two_podcast` preset or the joint thresholds.
2. **GROUP looks sticky.** GROUP committed 15.6 % of frames but only 3.5 % had 3 detected
   heads — the slow `mode_collapse_frames` (36) lets a brief 3rd-person appearance linger as
   GROUP. **Watch:** does the framing pull wide to a "group" when really it's 2 people + a
   brief passer-by? If so, shorten GROUP collapse or require steadier 3-head evidence.

**Note.** `diagnose_modes.py`'s first version mislabeled GROUP centroid frames as DUAL
two-shots (both use `active_id=None`); fixed to split them by committed mode. Re-run for a
clean `dual_two_shot` vs `group_fit` breakdown.

**Next.** User to watch `exports/MultiplePeople_debug.mp4` and judge (1) and (2) above plus
the spring feel; then we tune thresholds from real evidence (this is finally the real-footage
signal #5/tuning was waiting for).

---

## 2026-06-11 — Bugfix: detector `_attach_mouth` crashed on every 2+-person frame

**What & why.** First real run on `Imports/Multiple People.mp4` (4K, multi-person) crashed
instantly: `detector._attach_mouth` used `H` (frame height) which was never a parameter —
`NameError: name 'H' is not defined` at `fcy = (min(ys)+max(ys))*0.5*H`. The mouth/face
landmarker only runs when **2+ people** are present, so the solo test clip (0212) never
exercised it and the bug sat latent. It blocked **all** DUAL/GROUP processing on real
footage. The synthetic tests feed `Detection` objects straight in, bypassing the detector,
so they were green while real multi-person footage was 100% broken — a reminder that the
unit tests don't cover the live detector path.

**Changes.** `backend/reframer/detector.py`: `_attach_mouth(..., W)` → `(..., W, H)` and the
call site now passes `H` (both already in scope in `analyze`).

**Verification.** Compiles; re-running the debug overlay on the 4K multi-person clip now
proceeds past analysis (full result pending — heavy 4K render). **Lesson logged:** add a
detector-level smoke test on a real frame, or the synthetic suite will keep missing this
class of bug.

---

## 2026-06-11 — Roadmap #6: GROUP centroid-fit (V1 mode coverage complete)

**What & why.** GROUP (3+ people) was a placeholder — it just chased the dominant speaker.
Replaced it with the intended V1 fallback: frame the **size-weighted centroid** of the
heads and **zoom to fit their hull**, so a group scene reads as a group instead of
ping-ponging between faces. This is the "dumb-but-safe" fallback the design always wanted,
and it's the second consumer of the zoom primitive.

**Design.** `speaker._group_framing(heads)`: centroid weighted by head area (foreground
people anchor the frame); horizontal hull = `[min(cx-w/2), max(cx+w/2)]`; `needed = hull +
2·margin`; `target_zoom = clamp(needed / crop_w, group_min_zoom, 1.0)`. So a **spread crowd**
(hull ≥ base) stays at base (widest, contains the most), a **tight cluster** (hull < base)
gets a gentle punch-in, floored at `group_min_zoom` so a crowd is never over-cropped. No
dominant-speaker chasing (`active_id=None`); the centroid + springs make it move slowly.
Only a scene cut snaps.

**Changes.**
- `backend/reframer/speaker.py`: GROUP now branches to `_group_framing` (new) before the
  active-speaker path, emitting a centroid FOCUS intent with a fitted `target_zoom`.
- `config.py`: `group_fit_margin_ratio` (0.12), `group_min_zoom` (0.80).

**Verification.** `scripts/test_group.py` (new, 9 checks): 4 spread people → GROUP, centroid
x≈970, zoom 1.0, `active_id` None; 3 tight people → GROUP, centroid x≈1000, zoom 0.832
(floored at 0.80). All other suites still green.

**Why #5 (importance blend) was skipped, not built.** DESIGN §3/§8 says add the
motion/size/face_conf blend to speaker selection **only if** pure-mouth selection misbehaves
on real footage. There's no real footage to show it misbehaving, so building it now would be
unvalidated speculative complexity. Deferred until a real clip justifies it.

**Next.** The roadmap's buildable items are done; the remaining V1 work is **validation on
real footage** (see snapshot). Natural future modules (all out of V1 scope): action/sports
object-salience preset, the AI moment-finder, subtitles.

---

## 2026-06-11 — Emphasis punch-in (first consumer of the zoom primitive)

**What & why.** The zoom primitive (#4) had no driver — nothing requested a zoom, so it
was dead code. Wired its first consumer: on a **sustained SOLO shot** (same subject held,
no cut/switch) the engine slowly **pushes in** for emphasis — the classic "held shot drifts
tighter" beat. This both makes zoom do something visible and is a real cinematic win.

**Design.** Dwell-based, **not** speech-gated (a held shot pushes in regardless — simpler,
and a held subject is the subject). `speaker._emphasis_zoom`: a per-frame dwell counter for
the focused track; once it exceeds `emphasis_after_frames` it requests `emphasis_zoom`
(<1.0). It resets to wide (1.0) on **any** scene cut, deliberate speaker switch, change of
focused subject, or mode change away from SOLO — so every new shot starts wide and only
tightens if it's actually held. The zoom *spring* (#4) turns the 1.0→0.92 target flip into
a slow, smooth drift. Deliberately subtle; fully off via `emphasis_punch_in=False`.

**Changes.**
- `backend/reframer/speaker.py`: dwell state (`_focus_dwell`/`_dwell_id`), reset in
  `_reset_shot` and whenever `mode != SOLO`, and `_emphasis_zoom()` feeding
  `FrameIntent.target_zoom` on the solo focus return.
- `config.py`: `emphasis_punch_in` (bool), `emphasis_zoom` (0.92), `emphasis_after_frames`
  (90 ≈ 3 s).
- `scripts/debug_overlay.py`: focus label now prints `z=NN%` (crop width ÷ base) so the
  push-in is legible, not just visible.

**Verification.** `scripts/test_emphasis.py` (new, 9 checks): starts wide, pushes in past
the dwell, holds; a cut resets to wide then rebuilds; end-to-end the crop narrows 608→559px;
disabling pins zoom at 1.0. Spring (13) / recovery (A–E) / presets (10) all still green
(emphasis defaults don't trip them: their solo clips are < 90 frames or don't inspect zoom).

**Taste caveat — needs the user's eyes.** Whether an 8% push-in over ~3 s on *every* held
solo shot is tasteful (vs only on emotional/emphatic beats) can't be judged without real
renders. If it feels mechanical, options: gate on speaking-energy, require a longer dwell,
or only push in on the longest shots. Left dwell-based + subtle for now.

**Next.** #5 importance blend (only if mouth-only selection misbehaves on real footage —
blocked on a real clip), or #6 GROUP centroid-fit. Best done once the user drops footage so
we tune emphasis + validate DUAL at the same time.

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
