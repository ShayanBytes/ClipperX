# ClipperX 3.5 — Sequence-level intelligence

## What was still preventing better editing

Version 3.4 adapted decisions to each video, but it still selected the best camera separately for each segment. A locally sensible shot can create a globally bad sequence: crop → fallback → crop flicker, repeated layout changes, an unmotivated speaker cut, or a reaction shown too early.

Professional editing is a path-selection problem, not a collection of independent classifications.

## Research direction

- EditIQ frames shot selection as discrete optimization over an editing graph, including penalties for jump cuts, rapid transitions and irregular rhythm: https://dl.acm.org/doi/10.1145/3708359.3712113
- Disney Research uses dynamic programming with path cost and shot length to create coherent automatic cuts: https://studios.disneyresearch.com/wp-content/uploads/2019/03/Automatic-Editing-of-Footage-from-Multiple-Social-Cameras.pdf
- Real Time GAZED selects virtual shots using an objective function that combines attention evidence and cinematic principles: https://openaccess.thecvf.com/content/WACV2024/papers/Achary_Real_Time_GAZED_Online_Shot_Selection_and_Editing_of_Virtual_WACV_2024_paper.pdf

## New global editing graph

Every segment supplies multiple feasible states:

- Advanced proposed composition
- Stable subject
- Stable wide
- Conversation group view
- Complete-source fallback

ClipperX scores each state, connects it to every state in the next segment and finds the highest-value path through the entire video with dynamic programming.

## Transition intelligence

Transitions consider:

- Shared subjects between consecutive shots
- Layout continuity
- Required-role changes
- Story-motivated changes
- Per-video temporal importance

Holding the same meaningful shot is rewarded when the story is stable. Switching is allowed when required story roles genuinely change. This prevents stability rules from blocking necessary action and reaction cuts.

## Multi-hypothesis risk adjustment

Each candidate now has:

- Raw utility
- Evidence uncertainty
- Risk-adjusted utility
- Local greedy rank
- Global sequence result

Evidence dispersion and disagreement widen uncertainty. The sequence optimizer uses the risk-adjusted value rather than pretending one uncertain interpretation is certain.

## Fallback behavior

Fallback must now win the complete sequence—not merely one ambiguous segment. An isolated fallback that would cause crop → fallback → crop flicker can lose to a slightly lower local crop whose full sequence is more coherent. Genuine evidence loss can still make fallback win for the appropriate span.

## New artifact

`sequence-optimization.json` records:

- Selected path
- Total path score
- Runner-up score
- Sequence margin
- Transition values
- Whether global optimization overrode local greedy choices

## Honest validation boundary

Unit tests prove graph optimization, uncertainty accounting and continuity contracts. They do not prove universal human preference. The frozen real-video benchmark remains the release evidence required for that claim.
