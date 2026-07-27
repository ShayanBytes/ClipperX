# What was preventing ClipperX from becoming reliable

The v3.0 direction was correct, but a code audit found six architectural weaknesses that could still create visibly wrong edits.

## 1. The world model still trusted the composition plan too much

The director began with `mustShowTrackIds` created upstream. If story interpretation omitted the ball, target, active speaker or reactor, the dynamic director could confidently optimize an incomplete plan.

**Correction:** v3.1 independently fuses active-speaker, action, trajectory, outcome and reaction evidence. Missing causal roles are inserted before the camera policy is selected. An incomplete semantic plan can no longer silently remove a strongly evidenced subject.

## 2. Confidence was frame-local

A small object disappearing for a few frames immediately reduced confidence. That could abandon the ball or cube at exactly the difficult part of an action.

**Correction:** v3.1 keeps bounded track memory and predicts through short occlusions for no more than 0.9 seconds. Predicted evidence is explicitly discounted and labelled; it is not treated as a new detection.

## 3. Action importance was not phase-aware

Actors, objects, targets and reactors were assigned nearly constant importance across the entire event. This could keep the shooter too long, show reactions before the outcome, or waste space after the result was already known.

**Correction:** role requirements now change across anticipation, action/travel, outcome/result and reaction phases. The camera follows causal necessity rather than a fixed list of people.

## 4. Segment decisions could oscillate

Independent confidence decisions could alternate between advanced crop, fallback and split across short neighboring segments.

**Correction:** v3.1 adds confidence hysteresis, minimum policy hold time, action-episode continuity and stable-wide reacquisition before returning from GENERAL fallback to advanced framing.

## 5. The critic counted failed gates instead of measuring severity

A crop with 93% coverage and one with 20% coverage both counted as one failed gate. A visually nicer but catastrophically incomplete result could therefore survive.

**Correction:** candidate selection now uses weighted failure magnitude first. Action loss and body clipping carry stronger penalties than cosmetic quality. Overall visual quality is only the tie-breaker after deterministic safety risk.

## 6. Fallback targeting was too broad

An action failure could cause every segment to be replaced because the failed action was not linked back to the exact director situation.

**Correction:** action episode IDs and phases are stored on each directed segment. The critic replaces only overlapping failed episodes. Jitter can use a stable-wide locked crop, while coverage/body/action failures use the complete-source fallback.

## Resulting policy

1. Reconstruct important roles independently from the proposed layout.
2. Carry identity/object evidence through short, bounded occlusions.
3. Change importance by causal action phase.
4. Stabilize camera policy over time.
5. Compare candidate renders by safety-loss magnitude.
6. Replace only the segments responsible for the failure.
7. Preserve aspect ratio, zero cell gaps and zero strokes in every mode.

This removes major internal reasons for avoidable errors. It does not constitute proof over arbitrary real videos; the frozen 50-take benchmark still supplies that external evidence.
