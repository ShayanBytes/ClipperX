# ClipperX 3.3 — Predictive reliability guard

ClipperX now tests each planned edit against generated future and counterfactual situations before spending time on the final render.

## What it predicts

- A person or object moving outside the future crop.
- Insufficient body-safe margin near an edge.
- Large planned camera-center travel.
- Fragility when the primary detection disappears briefly.
- Instability under small left/right box jitter.
- Instability under confidence degradation.
- GENERAL fallback used despite trustworthy subject evidence.
- Duplicate or empty split cells.
- Dialogue focus changes shorter than 2.2 seconds.

## Scenario generation

For sampled frames in every segment, the guard projects tracked subjects at 0, 0.35, 0.75 and 1.15 seconds. It then runs five variants: base evidence, primary-track dropout, left jitter, right jitter and confidence loss. One ordinary segment can therefore generate dozens or hundreds of controlled tests without requiring another user video.

## Automatic repairs

- Predicted exit: widen crop, increase smoothing and use trajectory follow for actions.
- Dropout fragility: hold the last trustworthy camera state without unnecessary zoom-out.
- Camera travel spike: widen and stabilize before rendering.
- Misused GENERAL fallback: return to a stable evidence-complete crop.
- Redundant split: replace with one stable crop.
- Hurried dialogue change: retain the preceding shot.

## Artifacts

- `predictive-risk-report.json` — summarized risks, thresholds and repairs.
- `counterfactual-tests.json` — individual simulated trials.

## Relationship to real testing

Generated tests reduce how many obvious and repeatable errors reach the user. They do not replace the frozen 50-video benchmark because simulation cannot invent every visual, cultural or narrative ambiguity. The correct hierarchy is predictive testing before render, pixel inspection after render and representative human review before release.
