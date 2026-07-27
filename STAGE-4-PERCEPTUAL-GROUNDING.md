# ClipperX Stage 4 — Perceptual Grounding and Identity Continuity

Stage 4 improves the evidence that feeds the story brain, composition director and renderer. Although it is the fourth development stage, it executes immediately after base YOLO/ByteTrack analysis so all later stages receive grounded tracks.

## Camera-motion separation

Sparse optical flow and robust affine estimation measure source-camera translation, rotation and zoom at every analysis sample. Each tracked detection receives `worldVelocity`, which removes estimated camera movement from its observed velocity. Action anticipation and predictive pans now follow real subject/object motion instead of reproducing handheld shake.

## Persistent person identities

Each visible person receives a compact local HSV appearance descriptor. Non-overlapping tracklets are stitched only when:

- the temporal gap is bounded;
- appearance similarity passes a strict threshold;
- short-gap spatial continuity is plausible;
- the tracklets are not simultaneous.

Canonical IDs such as `person-001` propagate to face ownership, active-speaker mapping, the story graph, composition cells and rendering. Raw tracker IDs are preserved for debugging.

## Open-vocabulary story objects

An optional YOLO-World pass looks for objects that ordinary COCO detection commonly misses:

- dice and die;
- board-game pieces and tokens;
- playing cards and chess pieces;
- small balls and goals;
- microphones, phones and cups.

The pass is fail-safe. A missing model or unavailable download records a diagnostic error but does not stop the main pipeline. Set `CLIPPERX_OPEN_VOCAB=0` on low-resource systems to disable it.

## Interaction graph

Each analysis frame can now contain structured edges:

- `near` between spatially connected people;
- `manipulates` between a person and nearby story object;
- `looks_at` from head-direction evidence.

Stage 1 evidence also receives interaction counts, identity-stitching state and camera-motion magnitude.

## Artifacts

- Updated `perception.json`
- `identity-map.json`
- `grounding-report.json`

All descriptors and identity matching remain local; no biometric identity database is created.
