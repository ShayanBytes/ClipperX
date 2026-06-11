"""
ClipperX 0.3 - Configuration

All tunable parameters for the cinematic auto-reframe engine live here.
Unlike 0.2, every value in this file is actually consumed by the pipeline.
"""

CONFIG = {
    # === OUTPUT (9:16 vertical) ===
    "output_width": 1080,
    "output_height": 1920,

    # === PERSON / FACE DETECTION (MediaPipe Tasks) ===
    # Pose drives framing (works at any distance, incl. wide stage shots). Face is
    # only run when 2+ people are present, to read mouth movement (active speaker).
    "pose_model": "models/pose_landmarker_full.task",
    "face_model": "models/face_landmarker.task",
    "max_people": 3,                    # detect up to N people per frame
    "min_pose_confidence": 0.4,
    "min_tracking_confidence": 0.4,
    "min_face_confidence": 0.4,
    "face_match_dist_ratio": 0.15,      # max nose<->face distance (frac of width) to fuse mouth signal

    # === SCENE CUT DETECTION (PySceneDetect ContentDetector) ===
    "scene_threshold": 27.0,            # correct scale for ContentDetector (higher = fewer cuts)
    "min_scene_len_frames": 12,         # ignore cuts closer than this

    # === IDENTITY TRACKING ===
    "track_match_max_dist_ratio": 0.18, # max centroid distance (as fraction of frame width) to match a track

    # === ACTIVE SPEAKER (lip-motion) ===
    "mouth_window_frames": 15,          # rolling window (~0.5s @30fps) for mouth-motion score
    "speaking_score_threshold": 0.010,  # min mouth-openness std-dev to count as "speaking"
    "speaker_switch_hold_frames": 10,   # candidate must lead this long before we hard-cut to them

    # === RECOVERY (lost-target prediction) ===
    # When the focused subject's detection drops, the crop must NOT snap. The track
    # is kept alive and dead-reckoned (last DETECTED position + decaying velocity) for
    # this many frames; a re-acquisition eases back in. Only scene cuts / deliberate
    # speaker switches are allowed to snap. See DESIGN.md sections 5-6.
    "recovery_decay_frames": 24,         # ~0.8s @30fps to coast a lost target before giving up
    # Anti-hunting: a near-stationary lost subject is HELD at its last spot rather than
    # extrapolated (phantom motion is what makes the crop wander). Extrapolation only
    # kicks in above this speed, and is hard-capped so a bad guess can't snowball.
    "recovery_min_drift_speed_px": 1.5,  # px/frame; below this a coasted target is held still
    "recovery_max_drift_ratio": 0.05,    # cap predicted drift to this fraction of frame width

    # === SCENE MODE (L2 state machine: HOLD / SOLO / DUAL / GROUP) ===
    # Asymmetric dwell so the layout never flickers: escalating to a busier mode (more
    # people) is quick; collapsing back is slow, so a subject who briefly drops out of
    # detection doesn't ping-pong the mode. HOLD<->present and scene cuts commit instantly.
    "mode_enter_frames": 18,            # ~0.6s a busier mode must persist before we adopt it
    "mode_collapse_frames": 36,         # ~1.2s a quieter mode must persist before we fall back

    # === DUAL: SHOW BOTH (two-shot, else split) ===
    # When two people both matter (both talking, or trading lines rapidly) we frame BOTH.
    # If they fit in one 9:16 crop -> two-shot (single crop on their midpoint); if they're
    # too far apart to co-fit -> split screen. joint_hold/release debounce the punch<->wide
    # transition so it doesn't flicker.
    "both_active_threshold": 0.010,     # min speaking score for BOTH people to count as joint
    "joint_hold_frames": 9,             # "show both" condition must hold this long before entering
    "joint_release_frames": 12,         # must be absent this long before returning to punch-in
    "two_shot_margin_ratio": 0.12,      # breathing room each side (fraction of crop width) for co-fit
    "exchange_window_frames": 45,       # ~1.5s window for counting rapid speaker switches
    "exchange_switch_count": 2,         # this many switches in the window => rapid exchange => two-shot

    # === CINEMATIC CROP MOTION ===
    "dead_zone_ratio": 0.16,            # central safe band (fraction of crop width) where crop won't move
    "max_velocity_px_per_frame": 22.0,  # cap on how fast the crop center can move
    "ema_alpha": 0.18,                  # inertia: new = a*target + (1-a)*current (lower = smoother/laggier)
    "vertical_position": 0.42,          # subject's target vertical position in crop (0.5 = centered)

    # === SPRING CAMERA (L4) — critically-damped, replaces raw EMA easing for FOCUS ===
    # A critically-damped spring eases IN *and* OUT with no overshoot, driven by one
    # "responsiveness" knob (omega, per-frame). Pan (x/y) and zoom get SEPARATE springs;
    # zoom is deliberately slower than pan. Dead-zone + speed-limit + cut-snap still apply.
    # (The SPLIT path still uses ema_alpha above - it's static-ish and out of scope here.)
    "camera_responsiveness": 0.22,      # pan spring omega/frame; higher = snappier, still no overshoot
    "zoom_responsiveness": 0.08,        # zoom spring omega/frame - slower than pan on purpose
    # Zoom = a scale on the crop box. 1.0 = base = the WIDEST 9:16 region a 16:9 source can
    # give, so zoom only PUNCHES IN (z<1); "zoom out past base" is geometrically impossible
    # in strict 9:16 (that's what SPLIT is for). No driver requests zoom yet (#5/#6 will).
    "min_zoom": 0.62,                   # tightest punch-in (crop = this * base); 1.0 = base
    "zoom_max_rate_per_frame": 0.02,    # cap on |delta zoom|/frame so a scale change reads as a move

    # === EMPHASIS PUNCH-IN (first consumer of the zoom primitive) ===
    # On a SUSTAINED solo shot (same subject held, no cut/switch) slowly push in for
    # emphasis - the classic "held shot drifts tighter" beat. Dwell-based, not speech-gated
    # (a held shot pushes in regardless); resets to wide on any cut / speaker switch / mode
    # change, so every new shot starts wide. Deliberately subtle. Set False to disable.
    "emphasis_punch_in": True,
    "emphasis_zoom": 0.92,              # target crop scale once emphasis engages (~8% tighter)
    "emphasis_after_frames": 90,        # ~3s of unbroken solo focus before the push-in begins

    # === SUBJECT ABSENT (single person showing something) ===
    "saliency_bias": 0.25,              # how strongly to drift toward motion centroid when no face (0 = hold still)

    # === RENDER (ffmpeg) ===
    "crf": 19,
    "preset": "medium",
    "split_divider_px": 4,              # thickness of divider line between split halves (0 = none)

    # === PATHS ===
    "temp_dir": "temp",
    "export_dir": "exports",
}
