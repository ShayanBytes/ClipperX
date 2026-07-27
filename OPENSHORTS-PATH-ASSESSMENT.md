# Are ClipperX and OpenShorts following the same path?

## Short answer

Partly. Both use the correct foundational path: transcription, scene boundaries, semantic analysis, subject detection/tracking, vertical reframing, subtitles and rendering. The difference is sequencing and ambition.

OpenShorts keeps reframing comparatively conservative:

- **TRACK mode** follows a reliable detected face/person using MediaPipe and YOLO.
- **GENERAL mode** avoids risky crop decisions by preserving the complete source over a blurred 9:16 background.
- Gemini is primarily used to identify worthwhile moments, while deterministic vision handles the crop.

ClipperX added causal story graphs, social reactions, moving objects, sports outcomes, grids, split screens, editorial profiles and correction passes before proving a conservative crop on a broad real-video benchmark.

## What we did right

- Separating story understanding, composition and rendering is sound.
- Using local geometry to bound an API model is sound.
- Tracking people, objects, actions and outcomes is necessary for the harder product we want.
- Preserving a complete causal chain is more capable than a face-only tracker.
- A local fallback and final quality supervisor are the right concepts.

The architecture does not need to be discarded.

## What we did wrong

### Complexity arrived before reliability evidence

We implemented more possible layouts before measuring whether the simpler layouts were consistently good. Every new mode increased the chance of choosing a bad mode.

### Tests measured code contracts, not viewer preference

Most tests proved that a selected layout contained track IDs or that a metric file existed. They did not prove that a viewer preferred the result.

### No frozen benchmark

Without the same 50 cases on every release, fixes for one clip could quietly damage another category.

### No conservative baseline competition

A sophisticated result should only survive when it is better than center crop and GENERAL blurred-background fallback. Previously the advanced result was accepted by default.

### The user became the evaluator

Obvious failures reached the user because the release process had no mandatory human scorecard and no P0/P1 blocker.

## The corrected path

1. Make center and GENERAL fallbacks unbreakable.
2. Run all advanced outputs against both baselines.
3. Escalate from single crop to pan, split or grid only when evidence proves the simpler mode insufficient.
4. Evaluate the same 50 scenarios every release.
5. Require automatic safety metrics plus human preference.
6. Block packaging on any P0 failure, more than two P1 failures, missing cases or weak preference.
7. Only then improve models or add features.

This is the right path because it is monotonic: complexity is admitted only when it beats a safe baseline. Even if Kimi, Gemini or another model is imperfect, the product cannot become worse than the conservative fallback.

## What is known and what is not

OpenShorts publicly documents its dual TRACK/GENERAL architecture and product pipeline. Its public repository does not present evidence of a 50-case framing benchmark equivalent to this release. Therefore it would be inaccurate to claim that OpenShorts used exactly this benchmark process.

It is accurate to say that its simpler fallback hierarchy is a useful design lesson, while ClipperX's intended scope is significantly harder. Our mistake was not pursuing a richer editor; it was pursuing that richness before establishing a mandatory comparative reliability gate.
