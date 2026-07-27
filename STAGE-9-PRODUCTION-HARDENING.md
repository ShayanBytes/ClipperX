# ClipperX Stage 9 — Production Hardening

Stage 9 turns the nine-stage research pipeline into the stable **ClipperX 2.0.0** desktop engine.

## Hardware-aware execution

Before processing, ClipperX records CPU count, physical memory, GPU availability, GPU memory and free disk space. It selects one bounded runtime profile:

- **Eco:** low-memory or four-core laptops; 4 FPS analysis, six-person ceiling, tiny Whisper and no open-vocabulary detector by default.
- **Balanced:** ordinary laptops; 6 FPS analysis and bounded CPU threads.
- **Quality:** capable CPU systems with at least 16 GB RAM.
- **Accelerated:** CUDA-class GPU with sufficient VRAM and system memory.

Automatic tuning only reduces a user's requested laptop workload. It never silently upgrades to a heavier detector. Set `CLIPPERX_AUTO_TUNE=0` to keep explicit command-line values, or explicitly set `CLIPPERX_ALLOW_HEAVY_MODELS=1` to permit the selected high-end profile to upgrade default model sizes.

## Resource safety

- Preflight free-disk validation uses source size and output dimensions.
- BLAS, OpenMP and inference thread counts are capped.
- Desktop job concurrency is clamped to two, with one as the default.
- Pending queue size is bounded.
- Jobs have a configurable hard timeout and process-tree cancellation.
- Stale cancellation markers are removed before a retry.

## Verified resumability

`runtime-checkpoints.json` binds every checkpoint to:

- a fast source-video content fingerprint;
- source size and modification time;
- processing settings and profile;
- hashed API configuration and correction inputs;
- exact artifact sizes and content hashes.

ClipperX can resume perception, audio/action/social analysis, story intelligence, composition/editorial work and the final render. Corrupt, missing or mismatched artifacts are recomputed automatically rather than trusted.

## Crash recovery

Failures produce `crash-report.json` with secrets redacted and a recovery instruction. Running the same project again reuses only verified completed stages. The final `performance-report.json` records stage timings, resumed checkpoints, hardware, resource budget and selected profile.

## Privacy

- `CLIPPERX_PRIVACY_MODE=local` keeps the existing bring-your-own-API behavior.
- `CLIPPERX_PRIVACY_MODE=strict` disables Stage 8 contact-sheet upload and removes the contact sheet plus extracted audio after verification.
- `CLIPPERX_KEEP_INTERMEDIATES=1` retains silent render passes for debugging.
- API keys and Hugging Face tokens are redacted from crash output.

## Release validation

Run `npm run release:check` before creating the Windows installer. It verifies required desktop/backend/engine files, the stable version, NSIS configuration, ASAR unpack policy, Python compilation and JavaScript syntax.

## Production artifacts

- `runtime-checkpoints.json`
- `performance-report.json`
- `crash-report.json` on failure
- `render-result.json`
- all Stage 1–8 output and benchmark artifacts
