# ClipperX 2.1 — Universal Framing Recovery

This release implements `FRAMING-RECOVERY-PLAN-v2.1.md` across composition, rendering and final quality supervision.

## Root causes corrected

### Hard-coded strokes and insets

The previous renderer always added a gap and drew a rectangle around every cell. This also affected one-cell output. Rendering is now edge-to-edge and borderless for single, shared, split, grid and action layouts.

### Aspect-ratio distortion

The previous crop solver could clamp width without recomputing height, then resize the mismatched crop into a destination cell. ClipperX now solves paired crop dimensions at source boundaries and performs a final aspect-preserving cover crop before resizing. Source geometry is never squeezed.

### Excessive splitting

Split-screen is no longer a normal fallback for separated tracks. One crop is tested first using full-body-safe bounds, occupancy, readable scale and empty-space cost. A split survives only when:

- the moment is not a continuous physical action;
- one crop cannot communicate it readably;
- every cell contains a visible assigned subject;
- every cell safely contains the complete subject;
- cells are not duplicated;
- the regions carry simultaneous or genuinely separated narrative value.

### Missed moving objects

A deterministic action override examines non-person trajectory, displacement, velocity, class and action language. Throws, tosses, rolls, cubes, dice, balls, kicks, shots, catches, saves and other physical actions are converted to one continuous camera intention even if an API model missed the action label.

When one body-safe crop contains the action, `action_wide` wins. Otherwise `action_pan` follows actor → object → target → outcome. Split and grid layouts are prohibited during that chain.

### Unsafe body fragments

Person boxes receive full-body safety expansion. Stage 8 now measures body clipping in addition to face clipping. A goalkeeper fragment, cropped torso or similar failure can trigger one targeted widening correction.

### Unstable opening focus

If the intended opening target is not reliably detected, rendering begins in a conservative centered source-safe view. It does not commit to an incorrect tight hint and then visibly chase another region.

### Overpowered API advice

Kimi 2.6 is not the primary cause. The real issue was that local geometry allowed weak candidates and API advice had too much scoring leverage. API influence is now advisory and reduced to a small bonus. A model cannot restore a candidate rejected for action continuity, aspect safety, body safety, empty content or redundant cells.

## Generalization

These rules are not hard-coded for one clip. They apply to:

- one to six people;
- interviews and conversations;
- simultaneous reactions;
- tabletop games and dice/cube actions;
- sports and goalkeeper sequences;
- demonstrations and moving-object scenes;
- mixed dialogue/action videos.

## Validation

The release includes regression tests for:

- boundary-safe crop ratios;
- circle geometry without squeezing;
- cube motion becoming primary action;
- football shots never using split/grid;
- close speakers exposing no split candidate to an API;
- borderless edge-to-edge cell rendering;
- conservative opening acquisition;
- body-fragment quality failure detection.

All 72 engine tests pass.
