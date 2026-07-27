# ClipperX v0.4 — native story-aware video studio

Native Electron desktop software backed by a local Node + Python story-aware reframing engine. Normal use opens a dedicated rounded app window, not a browser tab.

## Start as software

Run `npm install`, `npm run doctor`, then `npm run desktop`—or double-click `Launch ClipperX Desktop.bat`. Build the installable Windows EXE by double-clicking `CREATE INSTALLABLE EXE.bat` or running `npm run desktop:installer`. The result appears in `release/` and opens only as the rounded native app window.

## What v0.2 contains

- YOLO11 person, object and sports-ball detection
- Ultralytics ByteTrack persistent identities
- MediaPipe face detection associated with person tracks
- Faster-Whisper transcription, VAD filtering and word timestamps
- Optional pyannote speaker diarization
- Audio-speaker-to-face mapping and active-speaker timeline
- PySceneDetect shot boundaries and scene-reset behavior
- Optional cloud vision analysis of six-frame per-shot contact sheets
- Single, pair, group, action and wide composition planning
- Important-object inclusion and velocity-based look-ahead
- Time-varying crop keyframes
- Pan-speed limiting and zoom smoothing
- JSON manual crop corrections
- Styled ASS subtitles
- Full-length dynamic OpenCV crop rendering and FFmpeg audio/subtitle muxing
- Single-concurrency processing queue, progress files and cancellation
- Intermediate debug artifacts, evaluation metrics and regression tests

## Important performance note

The advanced engine is real code, but CPU processing is intentionally quality-first and can be slow. YOLO, Whisper and full-length frame rendering may take longer than the source duration on a laptop. Start with a 10–30 second 720p clip.

## Requirements

- Windows 10/11, macOS or Linux
- Node.js 18+
- Python 3.10 or 3.11 recommended
- FFmpeg and FFprobe on PATH
- 8 GB RAM recommended
- Internet on first run to install packages and download YOLO/Whisper weights

## Windows installation

Fully extract the ZIP first. Open Command Prompt inside `clipperx-ui`.

```bat
npm install
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
npm run doctor
npm run test:engine
npm run desktop
```

ClipperX opens in its own software window. `npm run dev` is retained only for browser debugging.

The first advanced run downloads `yolo11n.pt` and the selected Whisper model. Later runs use the local cache.

### Optional real speaker diarization

The default installation produces Whisper VAD and a safe single-speaker fallback. For multi-speaker pyannote diarization:

```bat
pip install -r requirements-diarization.txt
set HF_TOKEN=your_huggingface_token
```

The pyannote model may require accepting its model license on Hugging Face.

## Windows launcher fallback

If Windows security blocks the combined launcher, keep the virtual environment activated and use two Command Prompt windows:

```bat
npm run dev:api
```

```bat
npm run dev:web
```

## Vision providers

The UI supports Gemini, OpenAI, Anthropic, OpenRouter and custom OpenAI-compatible endpoints. Keys stay in browser memory, are passed to the local backend for the active job and are not written to project files.

Without a vision key, the local planner still uses detection, tracking, audio and conservative fallback logic.

## Processing flow

```text
Upload
→ scene detection
→ YOLO + ByteTrack + faces
→ Whisper + VAD + optional diarization
→ audio-to-face active speaker mapping
→ optional cloud shot semantics
→ composition solver
→ trajectory-aware crop optimizer
→ ASS subtitles
→ full-length dynamic render
```

Each project stores inspectable files in `runtime/projects/<id>/`:

- `perception.json`
- `audio.json`
- `active-speakers.json`
- `scenes.json`
- `semantic.json`
- `shots.json`
- `crop-keyframes.json`
- `subtitles.ass`
- `status.json`
- `manifest.json`
- `output.mp4`

## Manual correction format

Send corrections to `PUT /api/projects/<id>/corrections`:

```json
{
  "corrections": [
    {
      "start": 4.0,
      "end": 7.5,
      "centerX": 0.62,
      "centerY": 0.48,
      "cropHeight": 0.82
    }
  ]
}
```

Corrections override automatic framing only inside their time ranges.

## Queue and cancellation

- `GET /api/queue` — running and pending jobs
- `POST /api/projects/<id>/cancel` — cancel a running or queued job
- `PUT /api/projects/<id>/corrections` — save manual corrections

The UI changes the primary button to **Cancel processing** while a job runs.

## Tests

```bat
npm run test:engine
```

Current deterministic tests cover crop interpolation, vertical crop planning and action-mode selection when a tracked ball is present. `engine/evaluate.py` calculates center error, zoom error and required-subject visibility against labeled ground truth.

## Commands

```text
npm run dev          frontend + backend
npm run dev:web      frontend only
npm run dev:api      backend only
npm run doctor       environment check
npm run test:engine  Python regression tests
npm run build        frontend typecheck/build
```

## Honest validation status

Node/Python syntax, queue wiring and deterministic planner/crop tests have been validated. The earlier Phase-0 FFmpeg upload-to-render path was tested end to end. The heavyweight advanced path requires installed third-party models and cannot be fully executed in the packaging sandbox without downloading those weights. Test it first with short clips and use the generated debug JSON to isolate failures.

See `WORKLOG.md` for the detailed implementation log and validation boundary.

## Automatic diagnostics and repair

Before every advanced run, ClipperX now checks Python, FFmpeg, FFprobe, OpenCV, YOLO, Whisper, scene detection, MediaPipe, SciPy, and SoundFile. If anything is missing, processing does not start blindly. The error notification includes **Details & fix**, a simple explanation, and a **Repair engine** action.

For a complete manual setup, run:

```bat
npm run setup:engine
npm run doctor
```

The Windows installer builder runs both commands automatically before creating the EXE.

## Python selection on Windows

ClipperX now ignores the private Hermes agent virtual environment and locates a real pip-capable system Python through the Windows `py` launcher, common Python installation folders, or PATH. The selected absolute interpreter is saved in `.clipperx-python.json` and reused by diagnostics, tests, the local API, and the installed desktop app.

## Windows status-file contention

Version 0.5.2 handles temporary Windows file locks from antivirus, indexing, or concurrent readers. Status writes remain atomic but now serialize Python writers and retry denied file replacements automatically instead of failing the test or processing job.

## Narrative editor engine (v0.6.0)

ClipperX no longer treats a long multi-person scene as one continuously moving crop. It divides physical scenes into editorial story beats, locks dialogue shots, and uses hard cuts for stable speaker changes. The vision model receives 12 annotated frames, timed transcript words, active-speaker hints, and track IDs for each nine-second window so it can preserve setup, action, result, and reaction. Action coverage uses actor/object relationships, median trajectory filtering, a movement dead zone, limited pan speed, and slow zoom. This quality-first mode intentionally performs more analysis and may take longer.

## Stage 1: Story Intelligence Brain

Version 0.7.0 adds a separate story-understanding layer before composition. Gemini receives the full video and timestamped local evidence, then a second API pass verifies the causal graph. The canonical `story-graph.json` distinguishes speakers from reactions, preserves simultaneous group laughter, connects object or sports actions to their outcomes, and records which subjects/regions later stages must cover. Provider retries are bounded to three attempts; failures fall back to an auditable local evidence graph instead of hanging.

See `STAGE-1-STORY-INTELLIGENCE.md` for the research conclusions, schema, artifacts, and strict Stage 1/2/3 boundary.

## Stage 2: Composition Director

Version 0.8.0 turns `story-graph.json` into `composition-plan.json`. It generates feasible single/shared/split/grid/action candidates, lets the API select only from those candidates, and then applies deterministic timeline optimization. Every must-show track must be assigned to a cell, grids are forbidden during continuous sports/object motion, and repeated layout changes are penalized. The output video remains a legacy single-crop preview until the Stage 3 multi-viewport renderer executes the plan.

See `STAGE-2-COMPOSITION-DIRECTOR.md` for layout rules and the Stage 3 contract.

## Stage 3: Multi-Viewport Renderer and Quality Loop

Version 0.9.0 executes `composition-plan.json` instead of producing a legacy single-crop preview. Every cell receives an independent stabilized source camera; split, grid, story-band, shared, single and action layouts are composed into the final 9:16 video. Sampled render telemetry measures required-subject coverage, blank cells, camera velocity variation and acceleration. A failed quality gate triggers at most one corrective render, and the higher-scoring pass is muxed with audio and subtitle-safe captions.

See `STAGE-3-MULTIVIEW-RENDERER.md` for the rendering model, thresholds, correction behavior and artifacts.

## Stage 4: Perceptual Grounding

Version 1.0.0 adds camera-motion compensation, persistent identity stitching, optional open-vocabulary small-object detection, head-direction evidence and structured person/object interaction edges. Story planning and rendering now use camera-compensated world motion rather than raw screen movement. See `STAGE-4-PERCEPTUAL-GROUNDING.md` and `CLIPPERX-9-STAGE-ROADMAP.md`.

## Stage 5: Social and Audio Intelligence

Version 1.1.0 adds local prosody analysis, bounded conversational turns, overlap and interruption structure, multimodal laughter/group-reaction detection, setup-to-payoff joke chains, and attachment of voice turns to persistent visible people. The resulting `social-intelligence.json` is included in Stage 1 evidence. See `STAGE-5-SOCIAL-AUDIO-INTELLIGENCE.md`.

## Stage 6: Action and Outcome Specialists

Version 1.2.0 reconstructs grounded object trajectories, links actors and targets, specializes sports/projectile/dice/tabletop actions, verifies outcomes from transcript and geometry, and joins Stage 5 reactions into one continuous coverage contract. See `STAGE-6-ACTION-OUTCOME-SPECIALISTS.md`.

## Stage 7: Editorial Style and Retention Director

Version 1.3.0 maps energy and hook strength, labels editorial beats, applies profile-specific camera/pacing/subtitle language, suppresses unnecessary cuts and preserves every causal timestamp and required subject. Stage 3 now executes the resulting style. See `STAGE-7-EDITORIAL-STYLE-RETENTION.md`.

## Stage 8: Multimodal Quality Supervisor and Benchmark Lab

Version 1.4.0 inspects the encoded output for phase-specific story coverage, face clipping, subtitle collision, jitter, blank/black/frozen/blurred frames and A/V drift. It permits one targeted quality-improving rerender, creates a contact sheet, supports optional Gemini visual critique, and writes deterministic benchmark gates. See `STAGE-8-QUALITY-SUPERVISOR-BENCHMARK.md`.

## Stage 9: Production Hardening — ClipperX 2.0.0

The complete engine now includes hardware-aware workload selection, disk and thread guards, content-verified resumable checkpoints, crash recovery, privacy modes, bounded queue execution, performance reports and automated release validation. Run `npm run release:check` before `npm run desktop:installer`. See `STAGE-9-PRODUCTION-HARDENING.md`.

## ClipperX 2.1: Universal Framing Recovery

Version 2.1 removes all cell strokes/insets, prevents aspect-ratio squeezing, prefers one body-safe frame, rejects empty or fragmentary split cells, tracks generic moving objects through outcomes, stabilizes opening acquisition, measures body clipping, and makes API layout advice strictly subordinate to deterministic geometry. See `FRAMING-RECOVERY-PLAN-v2.1.md` and `UNIVERSAL-FRAMING-RECOVERY-v2.1.md`.

## ClipperX 2.2: 50-take reliability reset

The development process now compares every advanced output against source, center-crop and GENERAL blurred-background baselines. Fifty reviewed cases, human preference, P0/P1 severity and strict framing/action gates are required before a release can honestly pass. Run `npm run benchmark:init`, add real case media, create baselines, complete scorecards, then run `npm run benchmark:evaluate`. See `OPENSHORTS-PATH-ASSESSMENT.md` and `RELIABILITY-BENCHMARK-50.md`.

## ClipperX 3.0: closed-loop dynamic director

Version 3 reconstructs a time-varying world state, ranks causal roles, calibrates confidence, vetoes uncertain crops/splits, preserves full source under uncertainty, and performs a post-render safety competition. See `CLOSED-LOOP-DYNAMIC-DIRECTOR-v3.md`. The frozen 50-take benchmark remains the independent proof gate.

## ClipperX 3.1: reliability architecture correction

The director now repairs incomplete upstream story plans with independent evidence, predicts through bounded short occlusions, changes required roles by action phase, stabilizes policy with hysteresis, ranks render candidates by failure magnitude and targets fallback to the exact failed action segments. See `WHAT-PREVENTED-RELIABILITY-v3.1.md`.

## ClipperX 3.2: selective fallback and conversation camera

Semantic uncertainty no longer automatically causes a complete-source fallback. Trackable solo performers and actions keep stable crops; spatial dialogue groups use turn-duration gating, story-weighted dominance and persistent borderless group coverage. See `SELECTIVE-FALLBACK-CONVERSATION-CAMERA-v3.2.md`.

## ClipperX 3.3: predictive reliability guard

Every planned edit now undergoes future-trajectory and counterfactual testing before render. The guard predicts edge exits, detection dropout, box jitter, confidence loss, hurried dialogue changes, redundant splits and fallback overuse, then repairs affected segments. See `PREDICTIVE-RELIABILITY-PLAN-v3.3.md` and `PREDICTIVE-RELIABILITY-GUARD-v3.3.md`.

## ClipperX 3.4: adaptive utility director

Fallback is no longer selected by a universal confidence cutoff. Each video calibrates its own confidence, motion, subject-size, conversation and coverage distributions. Advanced crops, stable views, group layouts and complete-source framing compete by context-weighted expected utility. See `ADAPTIVE-UTILITY-DIRECTOR-v3.4.md`.

## ClipperX 3.5: sequence-level intelligence

ClipperX now optimizes the complete camera sequence instead of choosing each segment greedily. A dynamic-programming editing graph combines risk-adjusted candidate utility with story-aware continuity, preventing isolated fallback flicker and unmotivated camera changes. See `SEQUENCE-LEVEL-INTELLIGENCE-v3.5.md`.

## ClipperX 4.0: executive director

ClipperX 4.0 turns direction, sequence optimization, predictive verification, and model criticism into callable capabilities selected by a bounded executive brain. A connected model can compare route consequences, while local geometry and body-safety checks remain authoritative. Every run now includes a downloadable diagnostic package with model-use and routing transparency. See `CLIPPERX-4-EXECUTIVE-DIRECTOR.md`.
