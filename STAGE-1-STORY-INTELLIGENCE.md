# ClipperX Stage 1 — Story Intelligence Brain

## Scope

Stage 1 understands the story. It deliberately does **not** implement split-screen templates, grid geometry, crop selection, or render transitions. Those are Stage 2 and Stage 3 responsibilities.

## Research conclusions

OpenShorts combines Whisper timestamps, scene detection, Gemini analysis, and a TRACK/GENERAL reframing fallback. The strongest related workflow sends the full video and timestamped transcript to Gemini because transcript-only systems miss laughter, gestures, reactions, and visual outcomes. Computational dialogue-editing research also treats editing as high-level labeled structure: begin wide, keep speakers visible, and intensify framing only when emotion warrants it.

ClipperX Stage 1 extends that model from “select the speaker” to a causal event graph:

- setup → trigger/joke/action → outcome → reaction/payoff;
- speaker and reaction are separate concepts;
- simultaneous laughter is one group event, not three unrelated faces;
- object actions connect actor, object area, result, and reactors;
- sports actions connect anticipation, actor, trajectory, target, outcome, and reaction;
- irrelevant standing/background people remain optional unless they affect the causal chain.

## Two-pass API brain

1. **Factual observation pass** — Gemini receives the full uploaded video plus timestamped local evidence. Other providers receive the evidence package. It extracts entities, events, simultaneous reactions, object actions, outcomes, and uncertainties.
2. **Causal verification pass** — a second bounded API call removes invented entities and duplicate overlap events, then repairs cause/reaction/outcome links.

Every provider call has a timeout and at most three attempts. It cannot retry forever. If the API fails, Stage 1 writes a local evidence graph and records the uncertainty.

## Outputs

- `story-evidence.json` — deterministic local observations.
- `story-pass-1.json` — raw API observation draft when available.
- `story-pass-2.json` — verified API graph when available.
- `story-graph.json` — validated canonical graph consumed by later stages.

Each event includes narrative role, importance, confidence, actors, reactors, objects, targets, must-show entities, anticipation, continuity, spatial spread, important-region count, and whether one vertical crop can contain the evidence.

## Stage boundaries

- **Stage 1 (this release):** story understanding and verified brain map.
- **Stage 2 (next):** choose single crop vs zoom-out vs 2/4/6-region split layouts and continuous action camera policy.
- **Stage 3:** render those layouts, transition them, evaluate missed subjects/jitter, and iterate automatically.
