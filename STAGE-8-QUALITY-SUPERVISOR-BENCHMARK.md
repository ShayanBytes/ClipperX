# ClipperX Stage 8 — Multimodal Quality Supervisor and Benchmark Lab

Stage 8 evaluates the encoded output rather than trusting planning artifacts alone. Deterministic checks remain authoritative; an optional API opinion can add observations but cannot override failed gates.

## Final-output inspection

Stage 8 measures:

- required-subject visibility from final render telemetry;
- phase-specific action coverage for anticipation, action, outcome and reaction;
- face clipping against the executed source viewport;
- face/subtitle safe-zone collisions;
- camera jitter and blank cells;
- black, frozen and persistently soft output frames;
- encoded audio/video duration drift.

Action phases use different coverage contracts. For example, anticipation requires actor/object/target, while a reaction phase requires the actual reactors rather than incorrectly demanding the shooter remain visible forever.

## Bounded correction

Correctable failures identify exact composition segments. Stage 8 may perform one additional render with:

- a wider crop scale;
- stronger temporal smoothing;
- preserved layout, chronology and must-show tracks.

The corrected render replaces the original only when its deterministic quality score improves. There is no unbounded retry loop.

## Optional multimodal critique

When Gemini is configured, ClipperX builds a chronological 3×3 contact sheet from the final output and requests a strict JSON critique. The request has bounded retries and a hard timeout. Other providers fall back to deterministic local evaluation in this stage.

The API can flag visible framing, continuity, readability or artifact concerns, but cannot mark a deterministically failed render as passed.

## Benchmark report

`benchmark-report.json` records category scores for:

- story and action coverage;
- composition safety;
- camera quality;
- render integrity.

This creates a stable regression surface for future releases and difficult-video fixtures.

## Artifacts

- `quality-supervisor.json`
- `benchmark-report.json`
- `quality-contact-sheet.jpg`
- `stage8-corrections.json` when correction is required
- `stage8-corrected-telemetry.json` when correction is attempted
- `composition-stage8-corrected.json` when correction is attempted
