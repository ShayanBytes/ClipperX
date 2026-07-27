# ClipperX 3.2 — Selective fallback and story-weighted conversation camera

## Why v3.1 still looked patterned

The confidence controller treated uncertainty primarily as a reason to preserve the complete horizontal source. That was safe, but too coarse. It did not distinguish **semantic uncertainty** from **visual trackability**. A juggler can be semantically ambiguous while the performer and ball remain visually trackable; GENERAL fallback is unnecessary in that case.

The dialogue director also evaluated speaker changes more often than a human editor would. In a four-person conversation split across two spatial sides, short turns and acknowledgements could create hurried virtual camera motion. Speaker activity alone is not a sufficient reason to move the camera.

## Research principles applied

- Stanford/Adobe's dialogue-editing work models editing as structural idioms over dialogue rather than a mandatory cut for every spoken line: https://graphics.stanford.edu/papers/roughcut/
- Real Time GAZED and prior meeting-editing work combine speaker, posture/head orientation, overview shots and transition rhythm rather than using active speaker as a direct camera command: https://openaccess.thecvf.com/content/WACV2024/papers/Achary_Real_Time_GAZED_Online_Shot_Selection_and_Editing_of_Virtual_WACV_2024_paper.pdf
- Active-speaker evaluation for automated editing identifies overlap, occlusion, low resolution and unseen conditions as failure modes, which means switching must be confidence- and duration-gated: https://project.inria.fr/wicedxcinemotions2023/files/2023/06/WICED_x_Cinemotions_2023_paper_13.pdf
- EditIQ similarly combines dialogue interpretation with visual saliency rather than equating visible size with importance: https://dl.acm.org/doi/10.1145/3708359.3712113

## New fallback hierarchy

1. Trackable single person/action → stable subject or action crop.
2. Multiple trackable subjects → stable evidence-complete crop.
3. Spatial dialogue groups → persistent group hold or borderless two-group coverage.
4. Moderate uncertainty → widen and hold.
5. Complete-source GENERAL fallback → only when no trustworthy region exists or post-render coverage/action loss is catastrophic.

Semantic uncertainty no longer automatically means visual fallback.

## Juggling and solo action

When one performer and a moving object are tracked:

- the performer remains the visual anchor;
- the moving object remains causally important;
- short object disappearances use bounded trajectory memory;
- one stable/action crop is preferred;
- GENERAL fallback is prohibited unless both performer/action evidence collapse.

## Four-person and spatial-group dialogue

People are clustered by persistent horizontal position, not body-box area. Dominance is calculated from speaking evidence and story/reaction importance.

- Short secondary turns do not force a camera change.
- Minimum dialogue shot duration is 2.2 seconds.
- A sustained or meaningful turn can motivate one deliberate cut.
- Rapid balanced conversation across two groups uses a persistent borderless two-cell layout, eliminating left-right camera chasing.
- Group cells have zero stroke and zero gap.
- A physically larger person does not become dominant unless dialogue/story evidence supports it.

## Post-render repair

Body, face, moderate coverage, blank-cell and jitter failures now try a stable-wide repair first. The complete-source fallback is selected only when required-subject coverage falls below 70% or action-phase coverage below 65%.

## New diagnostics

`world-model.json` now includes:

- conversation spatial clusters;
- speech weight by track and cluster;
- dominant cluster;
- median turn duration;
- current turn duration;
- balanced/rapid dialogue decisions;
- whether the segment had a genuine evidence void.

This release reduces patterned fallback and hurried dialogue movement. The frozen 50-video benchmark remains the external proof gate.
