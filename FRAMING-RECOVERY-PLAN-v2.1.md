# ClipperX v2.1 — Universal Framing Recovery Plan

This plan is written before implementation. The goal is not to tune one football or cube clip; it is to replace weak layout heuristics with deterministic framing rules that generalize to dialogue, games, sports, reactions, demonstrations and mixed scenes with up to six important people.

## Problems confirmed in the current engine

1. **Decorative strokes are hard-coded.** Every cell receives a gap and rectangle, including single-screen output.
2. **Aspect safety is incomplete.** Crop width can be capped without recomputing crop height, after which OpenCV stretches the region to the output cell.
3. **Split-screen has insufficient cost.** Two distant tracks can beat one meaningful crop even when one cell adds no story value or shows an unsafe body fragment.
4. **Action continuity depends too heavily on Stage 1 labels.** If a toss, kick, ball, die or cube is not marked `keepContinuousAction`, ordinary dialogue layout logic may cut away from it.
5. **The opening can commit too early.** A weak initial detection or median hint can produce an incorrect tight crop followed by a visible correction.
6. **Model advice has too much leverage.** Kimi or another general LLM can influence composition despite not having reliable geometric understanding. Geometry must be deterministic; the model may only advise among safe candidates.
7. **Cuts are event-driven rather than shot-driven.** Multiple semantic events can create unnecessary visual cuts during one continuous physical action.

## Implementation contract

### A. Borderless, edge-to-edge output

- Remove all cell strokes and white borders.
- Remove gaps around single-screen output.
- Multi-cell layouts tile the 9:16 canvas exactly with no decorative seams.
- Styling cannot re-enable borders unless a future explicit user setting requests them.

### B. Zero-distortion crop math

- Solve every source viewport against the exact destination-cell aspect ratio.
- If width or height reaches a source boundary, recompute the paired dimension rather than clamping one dimension independently.
- Use aspect-preserving cover crops only; never squeeze or stretch source geometry.
- Add automated shape-ratio tests.

### C. Single-frame-first composition

For every moment, compute whether all mandatory subjects fit one readable vertical crop. Prefer one frame whenever:

- required subjects fit with body-safe margins;
- the crop does not contain excessive empty area;
- important subjects remain readable;
- the moment is one causal action rather than simultaneous independent reactions.

Split/grid layouts are permitted only when every cell has unique narrative value, a full safe subject, adequate occupancy and no meaningful single-crop solution.

### D. Action-object override

Independently detect physical-action evidence from:

- non-person object speed and trajectory;
- actor/object/target relations;
- action words such as throw, toss, roll, cube, die, ball, kick, shoot, catch, hit and score;
- Stage 6 action episodes.

When evidence exists, force one continuous action camera or one stable action-wide crop. The object/action area becomes primary; cuts and grids are prohibited until the outcome is visible. This applies to arbitrary moving objects, not only footballs or dice.

### E. Body-safe framing and cell utility

- Expand person boxes to full-body-safe bounds before solving a viewport.
- Reject cells that show only a fragment, contain mostly empty space, duplicate another cell, or have no visible assigned subject.
- Penalize unused field space when it reduces action readability.
- Never create a goalkeeper-only lower cell that contains an unsafe body fragment while the upper cell already communicates the shot.

### F. Stable opening acquisition

- Begin with a conservative source-safe view if the intended subject is not reliably detected.
- Lock the first confident target for a minimum opening hold.
- Do not perform a wrong tight crop and then chase another region.
- Permit immediate action tracking only when motion evidence is already reliable.

### G. Shot continuity and cut hysteresis

- Merge adjacent semantic events that belong to one physical action or retain the same primary focus.
- Enforce minimum shot holds.
- Cut on genuine speaker/action changes, not on every event boundary.
- Preserve actor → object → target → outcome → reaction as one camera intention when spatially feasible.

### H. Model-bounded intelligence

- Local geometry and action evidence define the safe candidate set.
- Kimi 2.6, Gemini, GPT, Claude or another model can rank only safe candidates.
- API advice receives a small bonus and cannot override aspect safety, body safety, content utility, action continuity or single-frame feasibility.
- Therefore Kimi is not the root cause and changing models is not the primary workaround.

## Validation scenarios

1. One-person full-screen output has no stroke or inset.
2. Two-, four- and six-cell output has no decorative borders.
3. Circles and faces remain geometrically undistorted.
4. Three-person dialogue keeps only the two active speakers when the third person is optional.
5. A cube/die toss tracks the object/action area through its result.
6. A football shot uses one action-wide/pan camera when one crop is feasible.
7. A split is rejected when one cell is blank, redundant or body-unsafe.
8. A split remains available for truly separated simultaneous reactions.
9. Opening frames remain conservative until target confidence is stable.
10. Adversarial API advice cannot select an unsafe layout.

## Deliverable

ClipperX v2.1 will include the new universal framing arbiter, renderer corrections, regression tests, documentation and a complete ZIP. The existing nine-stage architecture remains; this is a quality-recovery release across Stages 2, 3, 6 and 8.
