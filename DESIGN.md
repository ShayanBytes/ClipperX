# ClipperX — Auto-Reframe Engine Design

> Source of truth for the reframe **decision engine**. Code follows this doc.
> Scope of this doc: the cinematic 16:9 → 9:16 cropper only (no moment-finder /
> subtitles yet). V1 target = **Solo + Dual nailed; Group/Crowd a graceful fallback.**

---

## 0. The one principle

> **The camera follows a *virtual target*, never a raw detection.**
> Detection feeds the target. The target feeds the camera. They are decoupled.
> Every visible "snap" is detection leaking straight into camera position.

ClipperX already half-respects this: `speaker.py` emits an *intent*, `crop_planner.py`
is a separate camera. The work below tightens that separation and adds the missing
**mode** and **recovery** layers.

---

## 1. Layered model (each layer runs at its own timescale)

```
L0  Detection            per frame   detector.py        pose, face/mouthAR, motion centroid
L1  Per-subject scoring   per frame   speaker._Track     importance score per track
L2  Scene-mode machine    SLOW ~0.5s  speaker (NEW)      SOLO / DUAL / GROUP / HOLD  ← mode hysteresis
L3  Target selection      per mode    speaker            who/what to frame → target point(s)
L4  Virtual camera        per frame   crop_planner.py    spring toward target (inertia, ease, limit)
L5  Crop + render         per frame   renderer.py
```

The chaos everyone hates comes from collapsing L2 (slow) into L4 (fast). Keep them apart.

### Mapping to current files
| Layer | File | State today |
| --- | --- | --- |
| L0 | `backend/reframer/detector.py` | ✅ pose framing + lazy face mouth + motion centroid |
| L0 | `backend/reframer/scene_detector.py` | ✅ PySceneDetect cuts |
| L1 | `speaker._Track.speaking_score` | ⚠️ mouth-std only; no motion/size/face blend |
| L2 | — | ❌ **missing**: no explicit mode; only FOCUS↔SPLIT toggle |
| L3 | `speaker._select_active` / `_decide` | ⚠️ works, but re-acquire path causes the snap bug |
| L4 | `crop_planner.py` | ⚠️ EMA + dead-zone + speed-limit; no predictive recovery |

---

## 2. The two hysteresis layers (do not conflate)

**Mode hysteresis (L2)** — stops the *layout* flickering:
- A new mode must hold continuously **T_mode ≈ 0.6 s (~18f)** before adoption.
- **Asymmetric dwell**: escalating is fast, collapsing is slow.
  SOLO→DUAL: 2nd subject active 0.6 s. DUAL→SOLO: 2nd subject gone **1.2 s (~36f)**.
  Kills ping-pong when someone briefly drops out of detection.
- A **scene cut is the only instant override** — it resets mode + camera (snap allowed).

**Target hysteresis (L3)** — stops chaotic speaker-switching *within* a mode:
- Switch focus only when challenger's smoothed score beats current by margin **M**
  for **T_switch ≈ 0.4 s** (today: `speaker_switch_hold_frames`).
- **Minimum hold** ~1.0 s after any switch before the next is allowed.
- **Pro rule**: if would-be switches fire faster than the min-hold (rapid Q&A),
  don't strobe — escalate to **DUAL two-shot**. Fast exchange ⇒ "show both."

---

## 3. L1 — Importance score (one formula)

Per track, per frame, then EMA-smoothed over ~0.5 s:

```
score = 0.45·speaking + 0.15·motion + 0.15·size + 0.15·face_conf + 0.10·centrality
```

- `speaking` = **std-dev of mouthAR over a rolling window** (oscillation, not openness).
  Already implemented as `_Track.speaking_score`. Keep.
- `motion` = landmark/centroid velocity of that track.
- `size` = bbox area (closer/foreground subject wins ties).
- `face_conf` = detection confidence (penalise half-occluded faces).
- `centrality` = small bias to frame-centre subjects.

V1 note: solo/dual quality barely needs motion/size/centrality — speaking dominates.
Add the blend only if pure-mouth selection misbehaves on real footage.

---

## 4. L2 — Scene-mode classification

**Implemented** in `speaker.py` (`_raw_mode` / `_commit_mode`, `SceneMode` enum, exposed as
`FrameIntent.mode`). Classified from **currently-detected** tracks — coasting recovery ghosts
do NOT vote (else a brief flicker that outlives the enter-dwell would flip the layout).
Classify by head-count, then commit through mode hysteresis (§2):

| Mode | Condition | Behaviour |
| --- | --- | --- |
| **HOLD** | `N_active == 0` | Freeze framing; slow drift toward motion centroid (held-up object stays in frame). Re-entry eases in. |
| **SOLO** | `N_active == 1` | Calm follow, dead-zone, breathing room, rule-of-thirds bias. |
| **DUAL** | `N_active == 2` | One dominant & sustained → punch-in on speaker. Comparable/rapid-exchange → two-shot (fit both). Too far apart to co-fit → SPLIT. |
| **GROUP** | `N_active ≥ 3` | **Implemented** (`speaker._group_decide`): if ONE person is a clearly-dominant reactor → punch in on them (reaction cut, `group_dominant_zoom`); else frame the size-weighted centroid + zoom-to-hull (spread crowd → base/widest; tight cluster → gentle floored punch-in), move slowly. Reactor importance is **motion-driven** (head velocity), not mouth — measured on real 4K footage the mouth signal is dead while head-speed separates a reactor (see §3). Hold/release hysteresis keeps the punch-in deliberate. |

`max_people` is currently 4 — covers reaction scenes. GROUP centroid-fit is deliberately
dumb-but-safe so it never wrecks an emotional crowd moment by over-cropping; the
dominant-reactor punch-in rides on top of it only when someone clearly stands out.

---

## 5. L4 — Virtual camera (the cinematic feel)

Keep: dead-zone, speed-limit, scene-cut snap.

**EMA → critically-damped spring (PD controller) — IMPLEMENTED** (`crop_planner._Spring`):
- Natural ease-in *and* ease-out, no overshoot, one "responsiveness" knob
  (`camera_responsiveness`). Analytic critically-damped update — stable at any rate.
- **Separate springs for pan and zoom** — zoom (`zoom_responsiveness`) slower than pan.
- The per-frame speed-limit still clamps the spring's output, so the recovery invariants
  (no snap on re-acquire) are preserved. The SPLIT path still uses EMA (static-ish).

**Zoom primitive — IMPLEMENTED** (`FrameIntent.target_zoom`, default 1.0). A separate
slower spring scales the crop box; the renderer already rescales any box, so crop size is
now per-frame. **Geometric limit:** the full-height 9:16 crop is already the *widest* 9:16
region a 16:9 source allows, so zoom only **punches IN** (`z ≤ 1`); "zoom out past base to
contain" is impossible in strict 9:16 — that is what SPLIT is for (see §10). **First driver
implemented:** the *emphasis punch-in* — a sustained SOLO shot slowly pushes in
(`speaker._emphasis_zoom`, dwell-based, resets to wide on any cut/switch/mode-change). Knobs:
`emphasis_punch_in` / `emphasis_zoom` / `emphasis_after_frames`.

**Snap is allowed in exactly one place: a detected scene cut.** Everywhere else,
including speaker switches and re-acquisition, motion is bounded by the speed-limit.
> ✅ Fixed: `crop_planner` snaps on `intent.allow_snap` (cut / deliberate switch) or when
> leaving a split — NOT on every `active_id` change. A *re-acquire after dropout* eases
> in (see §6).

---

## 6. L6 — Recovery (the #1 quality killer — your snap-back)

### Root cause in the current code
1. `speaker._select_active` (L3:183-186): when the active track **dies**
   (detection dropout), it *immediately* adopts the new best track and resets state.
2. `crop_planner._plan_focus` (L4:75-79): an `active_id` change sets `snap=True`.

⇒ A momentary detection loss → new active_id → **hard jump**. This is the
"loses the person, then SNAP recenters" you described. `coast_frames` softens it
only until the track expires.

### The fix — target carries velocity + confidence (implemented)
The camera tracks a **target point with state**, not the raw detection:
1. On focus-track dropout, confidence `c` decays **1 → 0 over ~0.8 s** (`recovery_decay_frames`).
2. While `c > 0`: advance the target by velocity **measured from the last detected
   anchor**, not the running estimate. Camera keeps gliding — no special case visible.
3. Detection returns → estimate snaps to truth, camera eases (dead-zone + speed-limit) → invisible.
4. Detection returns **far** (different/teleported subject) → ease at the speed-limit, never instant.
5. `c` hits 0 → enter **HOLD** (freeze + slow motion-drift). Re-entry eases in.

> Net rule: **only a scene cut (or deliberate speaker switch) snaps.** Lost-and-found never does.

### Anti-hunting (recovery v2) — the wander fix
Naive dead-reckoning *introduced* a new failure: at medium distance, intermittent
detection let the coast drift the estimate past the subject; on re-acquire the measured
velocity **flipped sign and grew**, so the crop oscillated, hunting for a spot. Three rules
kill it (all in `speaker._update_tracks`):
1. **Measure velocity from the last *detected* anchor over the real frame gap** — never
   from the coasted estimate (that fed the error back on itself). Trust it only across
   short gaps (`_VEL_TRUST_GAP`); zero it after a long loss.
2. **Stationary deadband** (`recovery_min_drift_speed_px`): below this speed a coasted
   target is **held** at its last detected spot, not extrapolated. A near-still subject
   never wanders.
3. **Bounded, decelerating extrapolation** from the fixed anchor, hard-capped at
   `recovery_max_drift_ratio · width` — a bad velocity guess can't snowball.

Verified by `scripts/test_recovery.py` scenario C (stationary subject + dropouts → 0px wander).

---

## 7. V1 scope (locked)

- ✅ **SOLO** — fully polished: dead-zone, spring follow, thirds bias, scene-cut snap.
- ✅ **DUAL** — punch-in / two-shot / split fallback, with target hysteresis + the
  rapid-exchange → two-shot rule.
- ✅ **Recovery (§6)** — predictive target + confidence decay. Highest-impact fix.
- ✅ **Scene-cut** is the sole snap source.
- ✅ **GROUP/CROWD** — single size-weighted centroid-fit fallback (`_group_framing`),
  zoom-to-hull, slow. No bespoke 3–12-person per-speaker logic (by design for V1).

Do not build per-person crowd switching until solo/dual feel pro on real footage.

---

## 8. Implementation roadmap (priority order)

1. **Recovery rework** (§6) — biggest perceived-quality win. Add velocity +
   confidence to the focus target; split "deliberate switch snap" from "re-acquire".
   Touches `speaker.py` (don't instantly re-adopt) + `crop_planner.py` (predictive coast).
2. ✅ **Explicit L2 mode machine** (§4) with asymmetric dwell (§2). SOLO/DUAL/GROUP/HOLD are
   first-class (`SceneMode`); committed from detected head-count via asymmetric hysteresis
   (instant on cut / first appearance). Split gated to DUAL. GROUP routes to dominant-speaker
   focus pending #6. Verified by `test_recovery.py` scenario D.
3. ✅ **Two-shot DUAL** + rapid-exchange→two-shot rule (§2). `speaker._dual_framing`: when
   both talk (or trade lines rapidly) we "show both" — a single FOCUS crop on their midpoint
   if the two heads co-fit `crop_w` (latched with a dead-band), else SPLIT. Entering a two-shot
   pans smoothly; cutting from two-shot to one speaker snaps. Verified by `test_recovery.py`
   scenario E. NOT yet validated on real 2-person footage (needs a clip in `imports/`).
4. ✅ **Spring camera** (§5) replacing EMA + the **zoom primitive**. `crop_planner._Spring`
   = critically-damped PD; separate pan/zoom springs (zoom slower); speed-limit + cut-snap
   kept. `FrameIntent.target_zoom` (default 1.0) plumbed; crop size now per-frame. **Unlocks
   the zoom primitive** for the §10 camera moves. NOTE: zoom only punches IN (9:16 geometry);
   no driver requests zoom yet — first consumer = an emphasis punch-in (#5). Verified by
   `scripts/test_spring.py`.
5. ✅ **Importance blend** (§3) — justified by real footage and built as the GROUP
   **dominant-reactor** pick (`speaker._group_importance` / `_group_decide`). Mouth-only DID
   misbehave: on 4K multi-person footage the FaceLandmarker can't attach a jawOpen to small/
   distant heads, so the speaking signal is dead (top-reactor score p90 = 0.0000). Switched the
   blend to **motion-driven** (`group_motion_weight = 1.0`: head velocity is the spine; speech
   is an additive bonus where it survives). Hold/release hysteresis (`group_dominant_hold_frames`
   = 8, tuned to bursty 5–11-frame reaction beats) keeps the punch-in deliberate.
6. ✅ **GROUP fallback** (§4) — `speaker._group_framing`: size-weighted centroid + zoom-to-hull
   (floored at `group_min_zoom`), no dominant-speaker chasing. Verified by `scripts/test_group.py`.

Built alongside the roadmap: ✅ **Presets** (§9) — content-type policy layer over the
mode machine (`presets.py`).

---

## 9. Presets (content-type policy)  ✅ scaffold + people presets

A preset does **not** replace the engine; it **tunes** it — a small dict of `config.py`
overrides that biases the same mode machine toward what a content type wants. It's how the
user injects context the engine can't infer. Lives in `presets.py`, selected via
`reframe(..., preset=NAME)` / `--preset NAME` (GUI dropdown = future).

| Preset | Bias |
| --- | --- |
| `auto` | Mode machine decides everything (default) |
| `one_person` | `max_people=1` → lock SOLO; no false DUAL/split; cheaper |
| `two_podcast` | Favor two-shot/split, calm switching, "show both" often |
| `two_dynamic` | Favor punch-in hard cuts, quick switching, little two-shot |
| `group_podcast` | 3+ seated: calm active-speaker focus |
| `group_dynamic` | 3+ lively: quicker, more heads tracked |

Verified by `scripts/test_presets.py`. **Out of scope (separate future module):** an
`action`/sports preset needs object salience (ball/goal/player detection + event
understanding) — a different problem from talking-head reframing; do not fold it in.

## 10. Camera-move taxonomy — *match the move to why the frame changes*

The move encodes the **relationship** between old and new framing. This is the rule for
"when to use what":

| Why the frame changes | Move | Status |
| --- | --- | --- |
| Source scene cut | hard cut | ✅ |
| Deliberate subject change (new speaker, for pace) | hard cut | ✅ |
| Same subject moved (walk/lean) | pan (track) | ✅ |
| Bring 2nd person in / co-frame both | pan / two-shot | ✅ |
| Scope of what matters changed | zoom | 🟡 primitive ready (#4); needs a driver |
| Reveal context (group laugh, play unfolds) | **zoom out to contain** | ⛔ impossible in strict 9:16 (use SPLIT) / needs bars + #6 |
| Emphasize an emotional beat | slow zoom in | ✅ emphasis punch-in on held SOLO (#4 driver) |
| Establish a space then commit | zoom out → in | ⛔ needs bars + #4/#6 |

Primitives: **cut = discontinuity/pace/new subject · pan = continuity/same thing moving ·
zoom = scope-of-what-matters changed (out=reveal, in=emphasize).** Override rule: when
several things matter at once, **zoom out to contain — never chase.** The engine has
cut + pan, and now a **zoom punch-in primitive** (#4); zoom-out-to-contain stays out of
reach in strict 9:16 (SPLIT covers it).

---

## 11. Config keys

Existing (`config.py`) already covers: dead-zone, max-velocity, EMA alpha, speaker
switch hold, joint/split holds, scene threshold, mouth window. **New keys needed:**

```python
# Mode hysteresis (L2)
"mode_enter_frames": 18,        # ~0.6s to adopt a more-complex mode
"mode_collapse_frames": 36,     # ~1.2s to fall back to a simpler mode (asymmetric)

# Target switching (L3)
"switch_score_margin": 0.004,   # challenger must beat focus by this (M)
"min_focus_hold_frames": 30,    # ~1.0s lock after a switch
"exchange_to_twoshot_frames": 24, # rapid-switch burst → escalate to two-shot

# Recovery (L6) — implemented
"recovery_decay_frames": 24,        # ~0.8s confidence 1→0 while target undetected
"recovery_min_drift_speed_px": 1.5, # below this, a coasted target is HELD (anti-hunting)
"recovery_max_drift_ratio": 0.05,   # cap predicted drift to this fraction of frame width

# Spring camera + zoom (L4) — implemented (#4)
"camera_responsiveness": 0.22,      # pan spring omega/frame (higher = snappier, no overshoot)
"zoom_responsiveness": 0.08,        # zoom spring omega/frame (slower than pan on purpose)
"min_zoom": 0.62,                   # tightest punch-in (crop = this * base); 1.0 = base/widest
"zoom_max_rate_per_frame": 0.02,    # cap on |Δzoom|/frame so a scale change reads as a move

# Emphasis punch-in (first zoom driver) — implemented
"emphasis_punch_in": True,          # slow push-in on a sustained SOLO shot (False = off)
"emphasis_zoom": 0.92,              # target crop scale once emphasis engages (~8% tighter)
"emphasis_after_frames": 90,        # ~3s of unbroken solo focus before the push-in begins

# GROUP centroid-fit (#6) — implemented
"group_fit_margin_ratio": 0.12,     # breathing room each side of the hull (frac of crop width)
"group_min_zoom": 0.80,             # GROUP won't punch in tighter than this (no crowd over-crop)
```
