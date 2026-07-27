# ClipperX 3.3 predictive reliability plan

## Goal

Find foreseeable inconsistencies before the user renders and reviews thousands of videos. Real-video benchmarking remains necessary, but known failure classes should be generated and challenged automatically from every uploaded video.

## Research basis

- Metamorphic testing evaluates ML robustness by applying controlled, meaning-preserving perturbations when a perfect answer oracle is unavailable: https://arxiv.org/abs/2504.02335
- Scenario-based testing replaces impractical distance-based testing with parameterized high-risk situations generated from real data: https://pmc.ncbi.nlm.nih.gov/articles/PMC10781207/
- Robust cinematographic camera paths minimize velocity, acceleration and jerk rather than merely filtering visible jitter: https://research.google.com/pubs/archive/37041.pdf

## Planned system

1. Build future trajectories from current position and camera-compensated velocity.
2. Simulate 0, 0.35, 0.75 and 1.15 seconds into the future.
3. Run controlled perturbations: primary-track dropout, left/right detector jitter and confidence loss.
4. Measure future body margins, required-subject coverage, perturbation stability and planned camera travel.
5. Predict non-pixel failures: excessive GENERAL fallback, hurried dialogue switches and redundant split cells.
6. Repair only affected segments before rendering.
7. Keep the existing post-render critic as a separate final defense.
8. Save every simulated case and repair decision for diagnosis and regression tests.

## Acceptance conditions

- A trackable subject approaching an edge is widened or trajectory-followed before clipping.
- A one-frame detection dropout cannot create a camera jump.
- A short dialogue segment cannot force a hurried focus change.
- Duplicate/empty split cells are removed before rendering.
- A GENERAL fallback with valid subject evidence is replaced by a stable crop.
- Simulation is deterministic, local, bounded and lightweight enough for a modest laptop.
