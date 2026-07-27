# ClipperX 3.0 — Closed-loop dynamic director

ClipperX no longer asks one semantic model to choose a crop and trust it. Version 3 builds a time-varying world model, assigns causal roles, measures evidence, chooses camera ambition from calibrated confidence, and inspects the rendered result before accepting it.

## World state

Every composition segment records visible tracks, detection persistence, active-speaker confidence, physical-action episodes, reactions, missing required subjects and dynamic narrative importance. Actors, moving objects, targets/outcomes, active speakers and reactors receive different causal weights. Visible bystanders do not become important merely because they were detected.

## Camera policy

- High confidence: execute the geometry-validated composition.
- Physical action: preserve actor, object, target and outcome as one continuous camera intention.
- Medium confidence: widen and hold instead of chasing detections.
- Low confidence: preserve the full source over a borderless blurred 9:16 background.
- Uncertain opening: begin conservatively instead of jumping to an unverified region.
- Uncertain split: veto it rather than creating speculative cells.

An API may help interpret meaning but cannot override these safety policies or produce pixel geometry.

## Closed render loop

The existing targeted correction pass remains. If the rendered output still fails required-subject, action-phase, face-safety or body-safety gates, the critic renders a second candidate in which only the failed segments use the full-source GENERAL fallback. The fallback replaces the advanced result when it removes more severe failures, even if the advanced layout is more visually ambitious.

## New artifacts

- `world-model.json`
- `directing-decisions.json`
- `closed-loop-fallback.json` when the critic requests fallback
- `composition-closed-loop-fallback.json` when fallback is rendered
- `closed-loop-fallback-telemetry.json`

## Non-negotiable behavior

- No squeezed output: every foreground and blurred background layer is aspect-preserving.
- No model-created crop coordinates.
- No low-confidence split screen.
- No tight opening crop before acquisition confidence is adequate.
- No optional bystander promotion without narrative evidence.
- No advanced result retained when a conservative candidate removes more severe deterministic failures.

The 50-take benchmark remains release-blocked until real media and human scorecards are present. Version 3 implements the general engine; it does not fabricate benchmark evidence.
