# ClipperX 2.2 — 50-take reliability gate

ClipperX is no longer released because unit tests pass. The release gate now requires 50 reviewed real-video cases across dialogue, sports/action, games/objects, group reactions and adversarial footage.

## Commands

```bash
npm run benchmark:init
npm run benchmark:baselines -- --case sports-action-01
npm run benchmark:evaluate
```

`benchmark:init` creates 50 case folders and pending scorecards under `benchmark-50`.

For each case:

1. Put the source at `<case>/input.mp4`.
2. Render ClipperX into `<case>/candidate/` so it contains `output.mp4`, `composition-plan.json` and `quality-supervisor.json`.
3. Generate center-crop and GENERAL blurred-background baselines.
4. Review source, candidate and both baselines.
5. Complete `scorecard.json`.
6. Run evaluation.

## Mandatory targets

- 50/50 completed cases
- zero geometric distortion
- zero unrequested strokes/insets
- zero blank or redundant split cells
- at least 98% body safety
- at least 95% required action coverage
- at least 90% opening-focus accuracy
- at least 90% split-decision accuracy
- at least 95% continuous-action accuracy
- at least 95% important-object coverage
- no more than one visible camera correction per minute
- candidate preferred over source/center/GENERAL in at least 70% of reviewed cases
- zero P0 failures
- no more than two P1 failures

## Severity

- **P0:** wrong story, lost action/outcome, distortion, unusable render.
- **P1:** major framing, body, split, opening or continuity failure.
- **P2:** visible polish issue without story loss.

Pending cases are failures. Missing human judgments are failures. API opinions cannot mark a case as passed.

## Provider matrix

The same frozen suite should be run in separate roots for Kimi, Gemini and a local/no-API fallback. A provider is acceptable only when the deterministic fallback prevents P0 regressions. This distinguishes model quality from engine safety.

## Honest limitation

The ZIP contains the complete harness, baselines, scorecards and 50-case specification. It does not contain 50 copyrighted user videos, and therefore the included report starts blocked at 0/50. A truthful release cannot claim the 50-video gate passed until real source clips and human reviews are supplied.
