# ClipperX Stage 6 — Action and Outcome Specialists

Stage 6 converts grounded object motion into verified action episodes before the story brain decides what matters.

## Trajectory reconstruction

Camera-compensated object centers are median-smoothed and converted into finite-difference trajectories. The specialist detects bounded motion bursts using class-specific thresholds, minimum displacement, temporal gap merging and source-camera-compensated velocity.

## Actor, object and target grounding

For every motion episode, Stage 6 identifies:

- the closest plausible actor before release;
- the moving object and its class;
- likely targets in the direction of travel;
- explicit goal objects when available;
- anticipation, action and outcome time ranges.

The resulting coverage contract includes actor, object and target. Stage 5 reactions are attached afterward, adding every visible reactor to the must-show list.

## Domain specialists

- **Sports shots:** shooter, ball, goalkeeper/target, trajectory and result.
- **Projectile actions:** thrower, moving object, destination and landing/result.
- **Dice rolls:** roller, die, motion-to-settle transition and optional visual pip count.
- **Tabletop actions:** actor, token/card/piece, destination and connected reaction.

## Outcome verification

Outcomes are never silently invented. Evidence can come from:

- explicit transcript success, goal or score language;
- explicit miss, save, block or failure language;
- trajectory entry into a detected target;
- a clear motion-to-settle transition;
- visual die-pip counting when confidence is sufficient.

Unresolved outcomes remain marked as uncertain. Stage 1 receives the specialist episode, evidence, confidence and uncertainty, then the API verification pass can compare it against the full video.

## Continuity contract

Every action episode contains anticipation, action, outcome and optional reaction phases. Sports and object actions are marked `keepContinuousAction`, preventing Stage 2 from inserting a grid or unrelated cut through the causal motion.

## Artifact

`action-intelligence.json` contains trajectory summaries, action episodes, actors, objects, targets, phases, outcomes, reaction links, must-show tracks and verification state.
