"""
ClipperX 0.3 - Configuration

All tunable parameters for the cinematic auto-reframe engine live here.
Unlike 0.2, every value in this file is actually consumed by the pipeline.
"""

CONFIG = {
    # === OUTPUT (9:16 vertical) ===
    "output_width": 1080,
    "output_height": 1920,

    # === PERSON / FACE DETECTION ===
    # PRIMARY: YuNet (cv2.FaceDetectorYN) — a CNN face detector shipped in opencv-contrib.
    # It finds ALL visible faces every frame (proven 2/2 close reaction faces where MediaPipe
    # pose found 1), giving box + 5 landmarks + score. Faces are the subject in reaction content,
    # so they drive framing now. Pose is kept only as a FALLBACK for frames with no detectable
    # face (everyone turned away / distant body shots). MediaPipe FaceLandmarker is still used,
    # but now run PER FACE CROP to read jawOpen (it works once we hand it a reliable, big face).
    "face_detector_model": "models/face_detection_yunet_2023mar.onnx",
    "det_width": 1920,                  # detect on a copy downscaled to this width (faster; boxes scaled
                                        # back). 1920 keeps small/distant 3rd-4th faces that 1280 drops.
    "min_face_score": 0.6,              # YuNet confidence floor for a face to count
    "pose_fallback": True,              # run a single pose detection on frames where YuNet finds 0 faces
    "pose_model": "models/pose_landmarker_full.task",
    "face_model": "models/face_landmarker.task",
    "max_people": 4,                    # cap on faces considered per frame (4 covers reaction scenes)
    "min_pose_confidence": 0.4,
    "min_tracking_confidence": 0.4,
    "min_face_confidence": 0.4,
    "face_match_dist_ratio": 0.15,      # max landmark<->box distance (frac of width) to fuse mouth signal
    # jawOpen via FaceLandmarker run on each face crop (restores the mouth signal, ungated from
    # pose). Only attempted on faces big enough to landmark reliably; below that, motion carries.
    "jaw_on_crop": True,
    "jaw_min_face_px": 90,              # min YuNet face-box width (source px) before we bother landmarking

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
    # Head-count for mode classification is the number of DISTINCT tracks seen within the last
    # `mode_headcount_window` frames, not just the exact current frame. On flickery footage the
    # detector finds 4 people only intermittently (avg 2, max 4); counting just this frame keeps
    # the scene stuck in DUAL/SOLO and the 4th person is dropped. A short window bridges that
    # flicker so a genuinely-4-person scene commits GROUP. window=1 = old exact-frame behaviour.
    "mode_headcount_window": 12,        # ~0.4s @30fps; count a track present if seen this recently

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

    # === GROUP centroid-fit (3+ people: V1 "dumb-but-safe" fallback, roadmap #6) ===
    # GROUP doesn't chase a dominant speaker; it frames the size-weighted centroid of the
    # heads and zooms to FIT their horizontal hull + margin. Spread crowd -> stay at base
    # (widest, show the most); tight cluster -> a gentle punch-in. Never over-crops a crowd.
    "group_fit_margin_ratio": 0.12,     # breathing room each side of the hull (frac of crop width)
    "group_min_zoom": 0.80,             # GROUP won't punch in tighter than this (no crowd over-crop)

    # === GROUP dominant-reactor focus (reaction cuts; DESIGN #5 importance blend) ===
    # In a 3+ scene, if ONE person clearly dominates (a strong, sustained reaction - laughing,
    # talking, gesturing) we PUNCH IN on them like a reaction cut, instead of always framing
    # the whole group. Only when nobody stands out do we fall back to centroid-fit. Hysteresis
    # (hold/release) stops it flipping between the reactor and the wide group every frame. The
    # tighter punch-in also re-enables VERTICAL composition (a full-height crop can't pan y).
    "group_dominant_focus": True,       # False -> always centroid-fit (old behaviour)
    "group_dominant_threshold": 0.012,  # min IMPORTANCE to be a "dominant" reactor. On motion-driven footage
                                        # importance ~= head-speed/frame-width; 0.012 sits between the measured
                                        # group-frame median (0.0045) and p90 (0.033), so only a genuinely
                                        # animated reactor clears it. On speech footage it's the mouth-std floor.
    "group_dominant_margin": 0.006,     # the top reactor must beat the runner-up by this much importance
                                        # (motion-lead p90 was 0.024, median 0.0025 -> fires only on real reactions)
    "group_dominant_hold_frames": 8,    # sustained dominance before we commit the punch-in. Motion reactions
                                        # are BURSTY (measured streaks 5-11 frames: a laugh / gesture); 12 was
                                        # too strict (1 engagement on the whole 4K clip), 8 catches the beats
                                        # (4 distinct reactors) while the release below keeps it deliberate.
    "group_dominant_release_frames": 18,# sustained NON-dominance before we fall back to the group
    "group_dominant_zoom": 0.72,        # punch-in scale on the dominant reactor (tighter than emphasis/group floor)
    "group_motion_weight": 1.0,         # motion contribution to importance. 1.0 = head VELOCITY drives the
                                        # reactor pick (a "reaction" here = visible motion: laugh/gesture/lean,
                                        # not lip-sync). Measured on 4K footage the mouth signal is dead (top
                                        # reactor speaking-score p90=0.0000) while head-speed SEPARATES a
                                        # dominant mover (lead p90=0.024 of frame-width). Speech stays an
                                        # additive bonus when present. 0 = speaking-only (old behaviour).

    # === SHOW EVERY REACTOR (multi-way split; the "4-person reaction" fix) ===
    # The core of the redesign: in a 3+ scene we no longer pick ONE dominant reactor and drop the
    # rest. We count how many people are actually REACTING and show them all — 2 -> 2-way split,
    # 3-4 -> a 2x2 quad grid (3 = two on top + one wide below). A single clear reactor still gets
    # a solo punch-in; nobody reacting -> centroid-fit. Reaction = the same importance signal as
    # the dominant-reactor pick (jaw-motion std + head/box motion), thresholded per person.
    "reaction_threshold": 0.012,        # min reaction_score for a person to count as "reacting".
                                        # reaction_score is mainly APPEARANCE motion (face pixels
                                        # changing in place). Measured on the practice clip: active
                                        # reactors ~0.025-0.05, static onlookers ~0.003, so 0.012
                                        # cleanly separates them. jaw + head-motion add on top.
    "reaction_appearance_weight": 1.0,  # weight on the appearance-motion cue in reaction_score
    "reaction_hold_frames": 8,          # a person must sustain a reaction this long to add their cell
    "reaction_release_frames": 18,      # ...and stop reacting this long before their cell is dropped
    "max_split_cells": 4,               # most reactors shown at once (grid caps at a 2x2 quad)
    # --- LAYOUT STABILITY (stop the grid reshuffling on detection flicker) ---
    # The grid geometry changes with the cell COUNT (a 3-cell layout != a 4-cell quad), so every
    # change of N is a hard relayout. On segments where detection fluctuates (e.g. 1-4 faces found
    # frame-to-frame) that reads as the camera "moving randomly". Two debounces tame it:
    "react_grid_hold_frames": 45,       # keep a lost grid-reactor in their cell (coasted at last
                                        # position) this long before dropping it, so a brief blink
                                        # doesn't collapse the grid (~0.9s@50fps / 1.5s@30fps).
    "react_layout_shrink_frames": 30,   # the displayed cell-count only DROPS after the lower count
                                        # persists this long. Growing is immediate (never leave a
                                        # present reactor out); shrinking is slow (a momentary
                                        # count dip doesn't reshuffle). ~0.6s@50fps / 1.0s@30fps.
    "split_face_mult": 3.6,             # each split cell crops this * face-box-height around the face
                                        # (face + shoulders + headroom), aspect-matched to the cell


    "saliency_bias": 0.25,              # how strongly to drift toward motion centroid when no face (0 = hold still)

    # === RENDER (ffmpeg) ===
    "crf": 19,
    "preset": "medium",
    "split_divider_px": 4,              # thickness of divider line between split halves (0 = none)

    # === PATHS ===
    "temp_dir": "temp",
    "export_dir": "exports",
}
