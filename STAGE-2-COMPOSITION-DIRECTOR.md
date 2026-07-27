# ClipperX Stage 2 — Composition Director

## Scope

Stage 2 converts the verified Stage 1 causal story graph into a feasible multi-viewport composition plan. It selects **what visual arrangement should be used and when**. It does not yet render those grids; that is the Stage 3 contract.

## Research conclusions

- Multi-subject reframing must consider saliency, momentum, and temporal continuity rather than center-cropping each frame.
- Split screen is valuable when it connects simultaneous meaning, but unnecessary split layouts create distraction.
- Dialogue coverage should prefer one natural frame when subjects are close.
- Group laughter is a simultaneous payoff: if one vertical crop cannot contain the meaningful reactors, all reactors need explicit regions.
- Sports camera guidance recommends anticipating a penalty/free kick, keeping kicker and goal in frame when possible, holding until contact/result, and following motion only after the action begins.
- Layout decisions should therefore be discrete story decisions while movement inside an action can remain continuous.

## Candidate layouts

- `single_focus` — one dominant person.
- `shared_wide` — nearby people remain in one natural crop.
- `split_2_stack` — two separated story regions stacked vertically.
- `grid_4` — three or four simultaneous individual reactions.
- `bands_2x3` — two horizontal regions, each containing up to three spatially connected people.
- `grid_6` — six individual cells only when grouping is not meaningful.
- `action_pan` — uninterrupted predictive actor → object → target motion.
- `action_wide` — stable complete action frame when spatially feasible.

## Decision process

1. Build actual spatial/visibility statistics for every Stage 1 moment.
2. Generate only feasible candidates and assign every must-show track to a cell.
3. Ask the API composition director to choose only from those candidate IDs.
4. Run deterministic dynamic programming across the full timeline.
5. Penalize rapid layout changes and reject grids during continuous action.
6. Verify that every required person/object is assigned and save `composition-plan.json`.

## Stage 3 contract

Each selected cell already includes output rectangle, track IDs, source policy, priority, and a source viewport hint. Stage 3 will execute these cells, animate allowed action pans, composite borders/backgrounds, place captions around faces, and evaluate the rendered result.

The current video output remains a clearly labeled legacy single-crop preview until Stage 3 is implemented. Stage 2 does not pretend that a planned grid has already been rendered.
