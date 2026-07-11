# ClipperX Architecture

## Product invariant

The runtime never delegates editorial decisions to an LLM. It converts measurable visual evidence into legal presentation candidates, then uses a deterministic global optimizer to choose a stable virtual-camera path.

## Current flow

```text
source video
  -> exact timestamped proxy
  -> shot boundaries
  -> visual evidence maps
  -> persistent entity tracker
  -> interaction graph
  -> entity importance distribution
  -> candidate crop evidence
  -> bounded-look-ahead dynamic program
  -> smoothed camera trajectory
  -> full-resolution FFmpeg render
  -> versioned JSON decision trace
```

## Runtime layers

### Perception

The baseline combines face detections, residual motion, image detail, center prior, and temporal evidence memory. Models are deliberately behind replaceable interfaces. The next detector can be a Core ML person/object model without changing planning or rendering.

### Identity memory

`CentroidTracker` is the deterministic CPU fallback. It predicts track motion through brief misses and performs globally sorted greedy assignment. Production tiers will add appearance embeddings and ByteTrack-style confidence association.

### Narrative Attention Graph

Entities are nodes. The first implemented edge is proximity. The schema is ready for gaze, pointing, touch, shared action, causal motion, reaction, and occlusion. Importance is normalized across visible entities so ambiguity can be measured rather than hidden.

### Planning

The planner maximizes retained evidence while penalizing velocity, acceleration, and target switching. Shot cuts selectively reset motion constraints. Bounded future evidence allows movement to begin before the strongest instantaneous cue.

### Rendering and audit

Planning runs entirely on a proxy. Rendering reads the source once at full resolution through FFmpeg. Every sample records entities, relations, confidence, raw evidence target, and selected camera location.

## Next milestones

1. Replace face-only proposals with person and story-object detection.
2. Add appearance-assisted tracking and cross-shot identity memory.
3. Add pose, gaze, pointing, touch, and reaction features.
4. Generate group, safe-wide, split-screen, and picture-in-picture candidates.
5. Train a compact temporal graph transformer from paired professional edits.
6. Add output-frame QC and automatic conservative rerendering.
