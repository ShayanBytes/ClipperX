# ClipperX Work Log

## 2026-07-23 — Advanced engine implementation (v0.2.0)

- Added YOLO11 person/object/ball detection with Ultralytics ByteTrack identities.
- Added MediaPipe face detection associated with persistent person tracks.
- Added Faster-Whisper word timestamps and VAD-filtered speech segments.
- Added optional pyannote speaker diarization using `HF_TOKEN`.
- Added audio-speaker-to-visible-face mapping and active-speaker timeline.
- Added camera-shot detection with AdaptiveDetector and explicit shot resets.
- Added per-shot cloud vision contact sheets plus conservative semantic JSON.
- Added single, pair, group, action and wide composition planning.
- Added ball/important-object inclusion and velocity-based look-ahead.
- Added smooth time-varying crop keyframes, pan-speed limits and zoom smoothing.
- Added JSON manual corrections applied by time range.
- Added ASS subtitle authoring and full-length dynamic OpenCV/FFmpeg rendering.
- Added a single-concurrency queue, live status files, cancellation endpoint and UI cancel action.
- Added crop and action-planner regression tests plus an evaluation metric module.
- Added intermediate debug artifacts for perception, audio, speakers, shots and crops.

### Validation boundary
- Python and Node syntax plus deterministic planner/crop unit tests are validated in the sandbox.
- The heavyweight YOLO/Whisper/MediaPipe runtime cannot be fully executed here without downloading model packages and weights; the target machine must install `requirements.txt` and will download model weights on first use.
- pyannote diarization is optional because it requires its extra package, an accepted model license and a Hugging Face token.


## 2026-07-23 — Windows launcher hotfix (v0.1.1)

- Fixed `spawn EINVAL` on Windows with Node.js 22 by launching the Vite npm process through `cmd.exe`.
- Resolved all development paths from the script location instead of the current shell directory.
- Added child-process error reporting and coordinated shutdown.
- Added `npm run doctor` to verify Node.js, npm, FFmpeg and FFprobe before startup.
- Clarified that the current backend is the runnable Phase-0 foundation, not yet the complete OpenShorts-plus perception stack.


## 2026-07-23 — Full-stack foundation

### Fixed
- Replaced the unsupported `FiSparkles` Feather icon that could crash the React module and produce a white screen.
- Added a development launcher that starts the frontend and backend together.
- Added Vite `/api` proxy configuration.
- Added a visible startup error boundary so runtime failures are no longer a silent white page.

### Frontend
- Responsive React + TypeScript dashboard.
- Desktop and mobile navigation.
- Video selection, content profiles, provider configuration and free-model policy.
- Real API calls for provider validation, project creation, raw video upload, analysis start and status polling.
- Real processing progress, error messages and generated-preview playback.

### Backend
- Dependency-light Node HTTP API using built-in Node modules.
- Local project persistence under `runtime/projects`.
- Health, provider, project, upload, analysis and asset routes.
- Secure filename handling, upload-size limits and asset allowlisting.
- API keys remain request-scoped and are not persisted.
- Real provider validation for Gemini, OpenAI, Anthropic, OpenRouter and custom OpenAI-compatible endpoints.

### Video pipeline
- FFprobe media inspection.
- Lightweight 854px/15fps analysis proxy.
- Eight-frame contact sheet.
- Thumbnail extraction.
- Optional semantic shot planning through the selected vision provider.
- Conservative local fallback when the provider is missing, rate-limited or fails.
- 30-second vertical preview render using center crop for confident single-person mode or blurred-background safe framing otherwise.

### Verification
- Backend syntax checked with Node.
- Health endpoint verified with FFmpeg and FFprobe available.
- End-to-end test completed using a generated 640×360 H.264/AAC video.
- Verified project creation, binary upload, FFprobe inspection, 480p proxy, contact sheet, thumbnail, safe plan and 1080×1920 preview output.
- Fixed an odd-dimension proxy encoding bug discovered during the first pipeline test.

### Known scope
- This is the complete runnable Phase-0 foundation, not the final trained perception engine.
- Person detection, ByteTrack, active-speaker mapping, Whisper subtitles and time-varying crop keyframes are the next test-driven modules.
- The current renderer intentionally chooses a safe composition rather than inventing unreliable subject coordinates.
## 2026-07-23 — Stability and interaction release (v0.2.1)

### Fixed
- Replaced the static dashboard navigation with functional Home, Projects, Templates, Runs, Settings and Help views.
- Connected the workspace three-dot menu to project details, download and deletion actions.
- Switched project cards from placeholder data to backend project records.
- Made frontend progress monotonic for each run, so stale polling responses cannot move the indicator backwards.
- Changed status-file writes to atomic temporary-file replacement, preventing partially written JSON and stale 0–5% loops.
- Fixed Windows FFmpeg ASS subtitle parsing by rendering from the project directory with `ass=filename=subtitles.ass` instead of an absolute drive-letter path.
- Captured FFmpeg stderr and reduced engine failures to short, bounded messages instead of rendering giant stack traces over the interface.
- Changed the desktop shell to fill the viewport like a software window while retaining rounded outer corners.
- Added responsive route, queue, settings, details, menu and empty-state layouts.

### Verification
- Parsed and bundled the complete React component with esbuild.
- Passed Node syntax checks and Python compilation.
- Passed planner, crop and atomic-status regression tests.
- Completed a real FFmpeg render with audio and ASS subtitles through the new relative-path code.
- Confirmed API health with FFmpeg and FFprobe available.

---


## 2026-07-23 — Native desktop and run observability (v0.3.0)

- Added a real Electron desktop shell with a frameless transparent rounded window and native controls.
- Added Windows portable and installer targets.
- Added a live ten-checkpoint Run Details inspector with slow-stage explanations.
- Full-length rendering now advances from 78% to 97% with frame-level updates.
- Failures preserve the last checkpoint and percentage.
- Added editorial serif italic headings based on the supplied reference.
- Added a real-people image to the live pair-shot composition demonstration.

## 2026-07-23 — Polished edges, profile, installer (v0.4.0)

- Replaced hard uniform card outlines with variable-opacity conic edge highlights and subtle depth shadows.
- Added a local Profile route with editable name, cropped profile-picture upload, persistence, and photo removal.
- Changed Windows packaging to an installable NSIS EXE only.
- Added CREATE INSTALLABLE EXE.bat with prerequisite checks, tests, clear failure output, and automatic installer reveal.

## 2026-07-23 — Self-diagnostics and design refinement (v0.5.0)

- Added automatic Python-module, FFmpeg and FFprobe diagnostics before advanced runs.
- Added one-click engine repair and a guided Details & Fix modal for missing modules, disk, memory, permissions, downloads and FFmpeg problems.
- Installer creation now installs Python engine packages before testing and building.
- Replaced harsh conic card outlines with a softer continuous material-edge gradient.
- Rebuilt the profile page as an editorial creator identity card with metrics, layered color fields and a tilted portrait treatment.

## 2026-07-23 — Windows Python resolver hotfix (v0.5.1)

- Ignored the inherited Hermes agent venv, which had no pip.
- Added system-Python discovery through `py -3.11`, `py -3`, common Windows paths and PATH.
- Added ensurepip recovery and persistent interpreter configuration.
- Routed doctor, tests, backend and Electron through the same selected interpreter.
- Launch now repairs dependencies automatically when diagnostics fail.
- Suppressed npm audit/funding noise during the guided installer build.

## 2026-07-23 — Windows atomic status hotfix (v0.5.2)

- Serialized status JSON writes inside the Python process.
- Added exponential retry for transient Windows `PermissionError: Access is denied` during atomic file replacement.
- Added best-effort retry cleanup for temporary status files.
- Added a regression test that deliberately denies the first three atomic replacements and verifies automatic recovery.
- Kept atomic replacement semantics so the frontend never reads partially written JSON.

## 2026-07-23 — Narrative editor and calm-camera engine (v0.6.0)

- Split long physical scenes into editorial story beats instead of assigning one crop to an entire scene.
- Added hard speaker cuts with minimum shot duration and no interpolation across cut boundaries.
- Added mouth-motion active-speaker evidence, hysteresis, and identity hold through brief occlusions.
- Added 9-second multimodal semantic windows with 12 annotated frames and tracked entity labels.
- Prompted the vision planner to preserve setup, action, outcome, and reaction for games and shooting.
- Added locked dialogue framing, wide group establishing shots, action trajectory filtering, pan dead zones, and slower zoom.
- Added YOLO box smoothing and lower-face motion measurement.
- Added regression tests for hard cuts, stable dialogue framing, group speaker changes, and actor-object action coverage.

## 2026-07-23 — Stage 1 Story Intelligence Brain (v0.7.0)

- Researched OpenShorts, full-video Gemini workflows, computational dialogue editing, multimodal laughter recognition, and multi-subject split-screen use.
- Defined the three-stage boundary so Stage 1 performs story understanding without prematurely implementing layout or rendering.
- Added deterministic 12-second evidence windows combining transcript timestamps, tracked people/objects, active-speaker votes, mouth motion, simultaneous expression, movement, and spatial spread.
- Added Gemini resumable full-video upload so the story brain can watch the source rather than infer only from text or thumbnails.
- Added a two-pass API process: factual observation followed by causal verification.
- Added a canonical causal story graph containing entities, events, arcs, relations, importance, confidence, must-show subjects, simultaneity, anticipation, action continuity, and uncertainty.
- Added local validation that removes invented tracks, clamps timestamps, restores missing reaction links, and computes spatial coverage from actual detections.
- Added explicit group-laughter and actor-object-outcome-reaction semantics.
- Added a compatibility adapter for the existing v0.6 composition engine; true split/grid layout selection remains Stage 2.
- Added three-attempt bounded provider retries and a six-minute bounded Gemini processing poll so analysis cannot retry forever.
- Added story evidence/pass/graph artifacts to the project manifest and detailed run checkpoints to the desktop UI.

## 2026-07-23 — Stage 2 Composition Director (v0.8.0)

- Researched multi-subject vertical cropping, split-screen narrative use, saliency/momentum planning, and sports camera guidance for penalty/free-kick coverage.
- Added discrete story moments derived from Stage 1 events, including anticipation windows for continuous actions.
- Added spatial statistics and viewport hints based on actual tracked boxes, visibility, source dimensions, and output cell aspect ratio.
- Added feasible candidates: single focus, shared wide, two-region stack, four-grid, two three-person story bands, six-grid, predictive action pan, and action wide.
- Added an API composition director that is restricted to supplied candidate IDs and cannot invent layouts or tracks.
- Added dynamic-programming continuity optimization across the entire timeline with penalties for rapid layout changes.
- Enforced all-must-show assignment and prohibited split grids during continuous action.
- Added `composition-plan.json` with cell output rectangles, track assignments, source policies, viewport hints, alternatives, validation, and the Stage 3 renderer contract.
- Kept the current rendered video explicitly labeled as a legacy preview; Stage 2 does not falsely claim that Stage 3 grids are already rendered.
- Added five Stage 2 regression tests covering close groups, separated reactions, six-person bands, continuous penalty action, and required-subject coverage.
- Corrected Stage 1 progress ordering so full-video upload and analysis never move progress backward.

## 2026-07-23 — Stage 3 Multi-Viewport Renderer (v0.9.0)

- Researched temporal-coherence, velocity-variation and acceleration-based jitter assessment, multi-view OpenCV compositing, and vertical subtitle/title-safe guidance.
- Replaced the legacy final renderer with a true Stage 2 composition-plan executor.
- Added independent temporal camera state for every output cell.
- Implemented single, shared, stacked two-region, four-grid, two three-person story-band, six-grid, predictive action-pan and action-wide rendering.
- Added slow dead-zone subject tracking, cluster holds, velocity look-ahead, bounded action motion, hard layout cuts, separators, and neutral empty-cell treatment.
- Added cell-specific manual corrections and aspect-safe crop overrides.
- Moved subtitles into a safer vertical region with larger horizontal margins.
- Added render telemetry for track availability, visibility, blank cells and source viewport coordinates.
- Added evaluation for required-subject coverage, blank-cell rate, velocity variation, acceleration, jitter and layout-switch rate.
- Added one bounded automatic correction render for missed coverage or excessive jitter, then selected the higher-scoring pass.
- Added final FFmpeg audio/subtitle mux using the Windows-safe relative ASS path.
- Added four Stage 3 regression tests including real synthetic multi-viewport rendering and final MP4 mux.

## 2026-07-23 — Stage 4 Perceptual Grounding (v1.0.0)

- Added compact local person-appearance descriptors during base perception.
- Added conservative non-overlapping tracklet stitching and canonical person identities.
- Propagated canonical IDs into face ownership and downstream active-speaker/story/composition/render stages.
- Added sparse optical-flow camera-motion estimation with robust affine fitting.
- Added camera-compensated `worldVelocity` to stop action cameras from reproducing source shake.
- Updated crop, composition, story evidence and Stage 3 predictive rendering to use world motion.
- Added optional YOLO-World detection for dice, game pieces, cards, tokens, small balls, goals and other story objects.
- Added fail-safe open-vocabulary behavior and `CLIPPERX_OPEN_VOCAB=0` low-resource override.
- Added per-frame proximity, object-manipulation and gaze interaction edges.
- Added `identity-map.json` and `grounding-report.json` artifacts.
- Added Stage 4 desktop checkpoints and five grounding regression tests.
- Defined the complete nine-stage product roadmap.

## 2026-07-23 — Stage 5 Social and Audio Intelligence (v1.1.0)

- Added local waveform analysis for energy, pitch, voicing, rhythm, spectral centroid and zero-crossing rate.
- Added per-utterance speaking rate, emphasis and arousal features.
- Reconstructed bounded conversation turns from Whisper timestamps and diarization labels.
- Added question, joke, laughter, agreement and disagreement speech-act labels.
- Added response, interruption, agreement, disagreement and laughter-at edges.
- Preserved simultaneous pyannote overlap regions.
- Fused transcript, acoustic and visible-mouth evidence into multimodal reactions.
- Added group-reaction participants and setup-to-payoff joke chains.
- Attached utterance speakers to Stage 4 persistent visible identities.
- Added Stage 5 evidence to every Stage 1 story window.
- Added `social-intelligence.json`, Stage 5 desktop checkpoints and six regression tests.

## 2026-07-23 — Stage 6 Action and Outcome Specialists (v1.2.0)

- Added camera-compensated, median-smoothed object trajectory reconstruction.
- Added class-specific motion thresholds, minimum displacement and burst merging.
- Added actor/release and direction-aware target grounding.
- Added sports-shot, projectile, dice-roll and tabletop specialists.
- Added transcript success, miss, save and score verification.
- Added trajectory target-entry and motion-to-settle outcome evidence.
- Added optional die-pip counting for settled rolls.
- Added anticipation, action, outcome and reaction phases.
- Connected Stage 5 reactions to action episodes and mandatory coverage.
- Added Stage 6 episodes to Stage 1 evidence and preserved continuous sports/object actions through composition.
- Added `action-intelligence.json`, Stage 6 desktop checkpoints and six regression tests.

## 2026-07-23 — Stage 7 Editorial Style and Retention Director (v1.3.0)

- Added narrative energy and early-hook scoring from story, prosody, reaction and verified outcome evidence.
- Added setup-hook, dialogue, action, action-payoff, reaction-payoff and breathing beat roles.
- Added Podcast, Sports, Cinematic, Social and Balanced editorial profiles.
- Added profile-specific crop scale, smoothing, reaction holds, minimum cut intervals, canvas, separators and gap scale.
- Added rapid-cut suppression and same-language hold decisions.
- Preserved action continuity, chronology, segment timestamps and every required track.
- Added profile-aware ASS font, size, density, colors, outline and title-safe margins.
- Updated Stage 3 to execute Stage 7 camera and visual styling.
- Added `editorial-plan.json`, Stage 7 desktop checkpoints and seven regression tests.

## 2026-07-23 — Stage 8 Multimodal Quality Supervisor and Benchmark Lab (v1.4.0)

- Added final encoded-pixel inspection instead of relying only on planning artifacts.
- Added phase-specific action coverage for anticipation, action, outcome and reaction.
- Added face clipping and subtitle collision analysis against executed viewports.
- Added black-frame, freeze, blur and audio/video duration-drift checks.
- Added deterministic quality gates and weighted final scoring.
- Added exact failing-segment identification and one bounded targeted rerender.
- Preserved chronology, layout and required tracks during corrective widening and smoothing.
- Added chronological 3×3 final-output contact sheets.
- Added optional bounded Gemini visual critique with deterministic-gate authority.
- Added benchmark category scores for coverage, composition, camera and render integrity.
- Added Stage 8 desktop checkpoints, artifacts and seven regression tests.

## 2026-07-23 — Stage 9 Production Hardening (v2.0.0)

- Added CPU, RAM, GPU, VRAM and free-disk detection.
- Added Eco, Balanced, Quality and Accelerated runtime profiles.
- Added laptop-safe automatic reductions for analysis rate, people ceiling, Whisper and open-vocabulary detection.
- Added disk preflight and bounded BLAS/OpenMP worker threads.
- Added source/config fingerprints and content-hashed resumable checkpoints.
- Added corruption detection and automatic checkpoint invalidation.
- Added resumability across perception, audio/action/social, story, composition and render stages.
- Added redacted crash reports and same-project recovery guidance.
- Added per-stage performance profiling and runtime reports.
- Added strict privacy cleanup and optional intermediate retention.
- Added bounded queue depth, concurrency clamp, process-tree cancellation and hard job timeout.
- Added production diagnostics and automated Windows release checks.
- Promoted ClipperX to stable version 2.0.0.

## 2026-07-23 — Windows installer symlink-privilege repair (v2.0.1)

- Confirmed the frontend and TypeScript build completed successfully before the installer failure.
- Isolated the failure to Electron Builder's optional winCodeSign archive containing macOS symbolic links.
- Disabled executable resource editing/signing for local unsigned Windows builds.
- Disabled certificate auto-discovery in the one-click installer batch file.
- Added release validation for the symlink-safe unsigned build contract.
- Added package description and author metadata.
- Added actionable cache cleanup and SmartScreen guidance.

## 2026-07-24 — Universal Framing Recovery (v2.1.0)

- Wrote the framing recovery plan before implementation.
- Compared the architecture with OpenShorts' TRACK and GENERAL modes and retained ClipperX's richer causal planner while adopting a stronger conservative fallback principle.
- Removed every hard-coded renderer stroke, inset and split-cell gap.
- Added paired aspect-ratio crop solving and final no-squeeze cover cropping.
- Added single-frame-first geometric feasibility and cell-utility scoring.
- Added full-body-safe person bounds and small-object safety margins.
- Added generic moving-object/action overrides for throws, tosses, rolls, cubes, dice, balls, shots, kicks, catches and outcomes.
- Prohibited split/grid layouts across one continuous physical action.
- Reduced API layout influence and made unsafe candidates unavailable to Kimi, Gemini, GPT, Claude and other models.
- Added conservative opening acquisition when the target is not yet reliable.
- Added body-clipping measurement and targeted correction to Stage 8.
- Invalidated old render checkpoints so the repaired framing is actually recomputed after upgrade.
- Added eight universal framing regression tests; all 72 engine tests pass.

## 2026-07-24 — 50-take reliability reset (v2.2.0)

- Stopped treating passing unit tests as evidence of professional output quality.
- Documented the honest OpenShorts comparison and corrected development path.
- Added a frozen 50-case benchmark across five real-world categories.
- Added center-crop and OpenShorts-style GENERAL blurred-background baselines.
- Added mandatory human scorecards and source/baseline preference judgments.
- Added P0/P1/P2 severity and release-blocking thresholds.
- Added body, action, opening, split, continuity, object, camera-correction and preference gates.
- Added truthful pending behavior: missing videos or reviews block release rather than defaulting to pass.
- Added benchmark CLI commands and provider-matrix guidance.
- Added seven benchmark regression tests.

## 2026-07-24 — Closed-loop dynamic director (v3.0.0)

- Added `engine/dynamic_director.py` as a model-independent world-state and confidence controller.
- Added causal importance for speakers, actors, moving objects, targets, outcomes and reactions.
- Prevented uninvolved visible people from automatically becoming layout subjects.
- Added low-confidence full-source GENERAL fallback and uncertain-opening protection.
- Added uncertain split veto and medium-confidence widen-and-hold behavior.
- Added aspect-safe blurred-background renderer with no stretching, border or inset stroke.
- Added post-render safety fallback competition for coverage, action, face and body failures.
- Added `world-model.json` and `directing-decisions.json` diagnostics.
- Invalidated old composition/render checkpoints with production schema 1.3.
- Added seven dynamic-director and fallback tests.

## 2026-07-24 — Reliability architecture correction (v3.1.0)

- Audited v3.0 before modifying it and documented six architectural blockers.
- Decoupled required-subject discovery from the upstream composition proposal.
- Added independent fusion of active speakers, actions, trajectories, targets and reactions.
- Added 0.9-second discounted identity/object memory for temporary occlusion.
- Added phase-specific actor/object/target/reactor requirements.
- Added confidence hysteresis, action continuity and stable-wide reacquisition.
- Added stable-wide single-cell repair when new evidence invalidates a proposed layout.
- Replaced failed-gate counting with weighted safety-loss magnitude.
- Scoped action fallback to segments linked to the failed episode.
- Added explicit renderer geometry-safety telemetry.
- Added four regression tests for incomplete plans, phase roles, occlusion and risk magnitude.

## 2026-07-24 — Selective fallback and conversation camera (v3.2.0)

- Researched dialogue idioms, active-speaker failure modes, group-meeting editing and online shot selection.
- Separated semantic uncertainty from visual trackability.
- Reserved GENERAL full-source framing for genuine evidence voids and catastrophic post-render loss.
- Added stable-subject framing for one reliably tracked person.
- Kept solo juggling/action crops locked to performer and moving object.
- Added persistent spatial conversation clusters.
- Added speech/story-weighted dominance independent of body-box size.
- Added 2.2-second minimum dialogue shot duration and short-turn suppression.
- Added deliberate group cuts for sustained/meaningful turns.
- Added borderless persistent two-group coverage for rapid balanced dialogue.
- Changed ordinary body/face/jitter/coverage failures to stable-wide repair before GENERAL fallback.
- Added six targeted regression tests for solo action, selective fallback, spatial dialogue and narrative dominance.

## 2026-07-24 — Predictive reliability guard (v3.3.0)

- Planned and researched metamorphic, scenario-based and future-trajectory testing.
- Added `engine/predictive_guard.py` before editorial compilation and rendering.
- Added four future horizons and five deterministic evidence perturbations.
- Added future body-margin, crop coverage and camera-travel prediction.
- Added automatic prediction of GENERAL fallback overuse, hurried dialogue changes and redundant splits.
- Added segment-level pre-render repairs for exits, dropout, travel, splits, dialogue and fallback misuse.
- Added `predictive-risk-report.json` and `counterfactual-tests.json` outputs.
- Added six predictive-guard regression tests.
- Kept the post-render quality supervisor and real-video benchmark as independent defenses.

## 2026-07-25 — Adaptive utility director (v3.4.0)

- Replaced global fallback pressure with per-video robust calibration.
- Added `engine/adaptive_intelligence.py` between dynamic story direction and predictive simulation.
- Learned confidence, motion, track velocity, subject area, people count, turn duration, segment duration and evidence distributions from each input.
- Added candidate generation and expected-utility ranking for proposed, stable-wide, stable-subject, conversation-group and complete-source layouts.
- Derived context weights from required roles, narrative entropy, motion pressure, conversation rhythm and evidence disagreement.
- Required fallback to win the same utility competition as every advanced candidate.
- Added decision margins and full candidate feature diagnostics.
- Converted predictive horizons, jitter magnitude, travel references, body references, dropout references and dialogue-duration references to per-video calibration.
- Added `adaptive-calibration.json` and `candidate-utility.json` artifacts.
- Added six regression tests proving calibration changes by video, clear-subject/action crops beat fallback, evidence void can select fallback, and all selections are utility argmax decisions.

## 2026-07-25 — Sequence-level intelligence (v3.5.0)

- Replaced per-segment greedy selection with global dynamic-programming optimization.
- Added a fully connected editing graph across candidate layouts for every segment.
- Added story-aware transition values from shared subjects, layout continuity and required-role changes.
- Added multi-hypothesis uncertainty measurement from feature dispersion, evidence disagreement and sample support.
- Added risk-adjusted candidate utilities.
- Prevented isolated crop → fallback → crop flicker when a coherent advanced path has higher sequence utility.
- Preserved motivated cuts when required story roles change.
- Added local-greedy versus global-path diagnostics and sequence override counts.
- Added `sequence-optimization.json` with path score, runner-up score, margin and transition values.
- Added three sequence-optimization regression tests.


## 2026-07-25 — Diagnostic-driven body-safe director (v4.2.0)

### Diagnostic findings
- An actual 4.1 run reported 26 body-fragment segments, 83.72% initial body clipping, 62.79% required coverage, and 76.9% blank/unresolved viewports.
- Predictive safety settings were erased by the later editorial profile stage.
- Repairs were logged without re-verifying the repaired geometry.
- Repeated P1 failures were under-penalized in executive scoring and did not block approval.
- Missing tracks drifted toward the default middle crop.
- Final quality could pass after fallback without treating blank-cell rate as a blocking threshold.
- The configured custom Kimi provider returned HTTP 503; zero model decisions were used and all executive routing was local.

### Corrections
- Preserved predictive camera safety tuning through editorial styling.
- Added post-repair simulation, structural retry, and last-resort full-source verification.
- Added unresolved-P1 release blocking and occurrence-aware executive penalties.
- Added spatial two-region repair for distant mandatory people.
- Added ambiguous-action actor filtering using object proximity and motion.
- Kept the active speaker primary and removed unrelated tracks from adaptive candidates.
- Limited hurried speaker/reaction layouts to two meaningful views.
- Restricted complete-source fallback to evidence failure or failed targeted alternatives.
- Added last-valid-view hold and temporary full-source behavior for missing detections.
- Added blank-cell rate to final quality gates and expanded downloadable diagnostics.

### Validation
- 121 deterministic Python tests passed.
- Release check passed for 4.2.0.
- Python and backend/desktop JavaScript syntax checks passed.
- ZIP integrity passed with zero original files missing.
- Real-video rerun remains required; frontend TypeScript/Vite build was not completed in the sandbox because project React dependencies were unavailable.

### Planning
- Added `plan.md` as the cross-agent source of engineering invariants, priorities, acceptance criteria, validation boundaries, workflow, and handoff format.


## 2026-07-25 — Evidence-targeted fallback correction (v4.3.0)

- Diagnosed a real 4.2 run with 23 of 26 segments converted to `general_safe` (`88.46%`), despite the adaptive director initially selecting zero complete-source candidates.
- Found that the predictive guard treated missing action-object IDs as missing human bodies and escalated unresolved identity gaps to whole-segment full-source fallback.
- Found that structural split groups were built from whole-video track positions rather than segment-local simultaneous evidence.
- Found that two missing split cells independently rendered the same complete-source recovery, duplicating the video in upper and lower halves.
- Body safety now evaluates person tracks only; action objects retain story importance without being evaluated as human bodies.
- Structural splits now require co-visible, spatially distinct people inside the same segment.
- Split rendering collapses to one meaningful viewport when two independent views are unavailable.
- Final predictive repair keeps a targeted stable view whenever reliable evidence exists and reserves complete source for a true evidence void.
- Pipeline completion is now blocked when predictive risk still reports unresolved P1 safety issues.
- Added regressions for missing action objects, fragmented non-co-visible identities, and duplicate split recovery.


## 2026-07-25 — Predictive-review completion fix (v4.3.1)

- A 4.3 real run correctly avoided complete-source fallback but crashed before rendering because predictive risks were treated as a fatal exception.
- The risk report contained 25 false hurried-dialogue warnings because an unavailable turn-duration reference defaulted to 99 seconds.
- Missing people in sampled frames reduced the body-safety score as if absent bodies were clipped.
- Body safety now scores clipping only for people actually present in each sample; temporal absence remains a separate coverage measurement.
- Hurried-dialogue checks now require actual speaker evidence and a finite, plausible observed turn duration.
- Tiny numerical edge margins no longer fail otherwise visible bodies.
- Predictive P1 findings now trigger targeted repair and encoded-pixel review instead of a processing crash. The final pixel quality supervisor remains the completion gate.

## 4.4.0 — Coordinate-grounded text-model director
- Text-only models now receive normalized boxes, body-safe boxes, source dimensions, screen zones, trajectories, velocities, edge risk, co-visibility, pairwise distance, union width, vertical overlap, and sampled coordinate timelines.
- Story reasoning runs in bounded coordinate batches followed by global causal/spatial verification instead of one oversized prompt.
- Automatic routing sends native video to the Gemini file adapter and uses the coordinate-text dossier for text/custom models.
- Grounded model hints may reorder verified subjects and bias safe candidate ranking, but cannot invent tracks, layouts, timestamps, or override geometry.
- Diagnostics now include story model routing and the coordinate dossier.

## 4.5.0 — Web test mode and temporal subject anchoring
- Added `START WEB TEST.bat`: launches localhost testing without building or reinstalling the desktop application; dependencies and engine setup are reused.
- Diagnosed the 4.4 production run: every active-speaker situation was null, the coordinate-story endpoint timed out after three 240-second waits, and 7/26 visual segments were shorter than two seconds.
- Active-speaker mapping now uses mouth evidence first, holds a canonically tracked body through face-landmark loss, permits a single-visible-body fallback, and bridges only short gaps whose surrounding speaker identity agrees.
- Added non-speaking visual narrative anchors from action actors and fused person importance. Short unstable subject changes inherit the previous visible anchor or widen instead of cutting.
- Added a 2.6-second sequence-level visual hold, while allowing sustained speakers and strong verified actions to trigger motivated changes.
- Coordinate text requests now use one compact window per request, partial success, bounded timeouts, and a circuit breaker instead of losing the entire story pass after one oversized request.

## 4.6.0 — Semi-automated external AI handoff
- Added an opt-in Semi-automated workflow. The normal UI stays unchanged until the mode is selected; the project card then transforms into a manual AI handoff explanation.
- The engine pauses at 58% after local perception, transcript, tracking, action, social, and coordinate evidence are ready.
- ClipperX generates `semi-automated-request.json` with instructions, strict response schema, and grounded evidence for upload to any external/free text AI.
- Run Details provides a download button, paste area, JSON validation, and resume action.
- Pasted responses are stripped from optional code fences, required to contain an events array, grounded against real IDs/timestamps, and cannot bypass deterministic geometry or safety.
- Perception and audio checkpoints are reused after the handoff; the source video is not reanalyzed.

## 4.6.1 — Reliable one-click engine repair
- Repair Engine now resolves a compatible 64-bit Python 3.10–3.12 interpreter instead of blindly installing into whichever `python` command Windows returns.
- Python 3.11 is preferred, followed by 3.12 and 3.10; incompatible 3.13-only setups receive an explicit installation instruction.
- The selected interpreter is activated immediately in the running backend, so a successful repair no longer requires a server restart.
- Virtual environments no longer receive the invalid `--user` install flag.
- Pip output is retained and the useful tail is surfaced when installation fails.
- Automatic setup and the in-app Repair button now share the same compatibility policy.

## 4.7.0 — Scene-aware one-second temporal director
- Added a second-by-second evidence cadence that observes active speakers, performer continuity and visible tracks without forcing a camera cut every second.
- Hard visual cuts and screen changes now cause immediate camera reacquisition instead of carrying the old crop for one or two seconds.
- Strong grounded speaker changes can acquire immediately; weak or ungrounded changes retain a stable anchor.
- Continuous physical action keeps the performer even when a counter or commentator becomes audible.
- Composition gaps no longer borrow a future story segment; they use current local evidence or conservative source context.
- Combined adaptive and hard-cut scene detection recognizes new screens more reliably.
- Cluster-follow smoothing is faster while retaining dead-zone and velocity limits to prevent jitter.
- Diagnostics now include `temporal-cadence.json` with every one-second decision, scene cut and acquisition reason.

## 4.8.0 — Capability-tested automatic mode and precise speaker grounding
- Custom endpoints now receive a bounded demo coordinate/story request before ClipperX approves Automatic mode.
- The capability test checks chat completion, valid JSON, story schema, event/hint linkage, and grounded demo track IDs.
- Passing endpoints display Automatic mode approved and switch the workflow to Automatic. Failing structured-output tests recommend Semi-automated mode with a one-click handoff.
- Active-speaker mapping now uses temporal mouth-motion dominance instead of favoring the largest visible face.
- Strong speech turns after silence reacquire the new speaker immediately, while ambiguous multi-person frames keep the grounded identity instead of guessing.
- Diagnostics record temporal mouth evidence, dominance margins, candidate counts, body continuity, diarization consensus, and ambiguous-face counts.
