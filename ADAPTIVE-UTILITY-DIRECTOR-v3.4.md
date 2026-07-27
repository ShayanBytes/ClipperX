# ClipperX 3.4 — Adaptive utility director

## Problem

A global cutoff such as 0.3, 0.4 or 0.8 cannot mean the same thing across thousands of unrelated videos. Detection confidence, subject scale, motion speed, conversation rhythm and occlusion differ by camera, lighting, content and model. Static fallback pressure therefore either hides too much context or gives up on scenes that remain crop-able.

## Research principles

- Confidence scores should represent actual correctness likelihood; modern neural models are often miscalibrated: https://arxiv.org/pdf/1706.04599
- Reject-option systems should abstain based on calibrated risk and decision cost rather than an arbitrary universal threshold: https://arxiv.org/html/2107.11277v3
- Conformal risk control formalizes control of expected monotone loss and extensions under distribution shift: https://people.csail.mit.edu/tals/publication/conformal_risk/

## Per-video calibration

Each uploaded video now supplies its own empirical profile:

- Detection-confidence quartiles
- Motion-speed quantiles
- Track-center velocity
- Subject-area distribution
- People-per-frame distribution
- Dialogue-turn duration distribution
- Segment-duration distribution
- Evidence-coverage distribution

These values are not product-wide constants. A low-resolution sports clip and a close-up podcast therefore receive different references.

## Candidate utility competition

For each situation, the engine generates applicable candidates:

- Existing advanced composition
- Stable-wide crop
- Stable-subject crop
- Persistent conversation-group composition
- Complete-source fallback

Every candidate is scored on:

- Required-subject coverage
- Narrative-role coverage
- Geometric feasibility
- Temporal continuity
- Subject clarity
- Robustness under uncertainty

The importance weights are normalized from the current situation: number of required roles, narrative entropy, motion pressure, conversation rhythm and evidence disagreement. Fallback has no bonus, quota or privileged threshold. It is selected only when its expected utility is higher than every crop candidate.

## Adaptive predictive testing

Future horizons, detector-jitter magnitude, camera-travel references, body-safety references, dropout references and dialogue-duration references now derive from the current video calibration. Predictive testing no longer assumes that one motion distance or turn duration applies universally.

## Proof artifacts

- `adaptive-calibration.json` records the learned per-video distribution.
- `candidate-utility.json` records every candidate, feature vector, context weight, winner and decision margin.
- `predictive-risk-report.json` records adaptive horizons and risk references.

This makes every fallback auditable: the report shows which alternatives lost and why.

## Honest boundary

Utility design still encodes universal goals—preserve story, preserve bodies, avoid frantic motion and maintain clarity. Those are product requirements, not content-specific numeric cutoffs. Real-video benchmark review remains necessary to validate whether the goals and feature measurements match human preference across domains.
