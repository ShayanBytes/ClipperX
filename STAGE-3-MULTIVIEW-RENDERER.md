# ClipperX Stage 3 — Multi-Viewport Renderer and Quality Loop

## Scope

Stage 3 executes the Stage 2 composition plan. It renders single crops, shared frames, stacked splits, four-grids, two three-person story bands, six-grids, predictive action pans, and stable action-wide layouts into the final 9:16 video.

## Rendering model

- Every output cell has an independent source viewport and temporal state.
- Subject cells use slow dead-zone tracking.
- Multi-person cells use wider cluster holds.
- Action cells use velocity look-ahead and faster but bounded predictive movement.
- Layout changes are hard editorial cuts; crop coordinates are never tweened between unrelated layouts.
- Multi-cell layouts use consistent inset separators and a dark neutral canvas.
- Manual corrections can target a specific `cellId`; unqualified corrections apply to single-cell layouts.
- Captions use larger horizontal margins and a higher vertical safe position for phone UI/title safety.

## Quality evaluation

The renderer records sampled telemetry for every cell and measures:

- required-subject center coverage;
- blank-cell rate;
- camera velocity standard deviation;
- mean acceleration and combined jitter score;
- layout switches per minute;
- declared caption-safe zone.

Temporal-coherence research treats unstable velocity and acceleration as major sources of visible jitter, so cuts are excluded from within-shot motion metrics.

## Automatic correction

If subject coverage, blank cells, or jitter miss thresholds, Stage 3 performs exactly one bounded corrective render:

- expand source margins for missed subjects;
- increase smoothing for excessive velocity variation;
- hold last known framing through short detection gaps;
- evaluate both passes and select the higher quality score.

Artifacts:

- `stage3-pass1-silent.mp4`
- `stage3-pass2-silent.mp4` when correction is needed
- `render-telemetry-pass1.json`
- `render-telemetry-pass2.json` when applicable
- `render-telemetry.json`
- `render-evaluation-pass1.json`
- `render-evaluation-pass2.json` when applicable
- `render-corrections.json` when applicable
- `render-evaluation.json`
- `output.mp4`
