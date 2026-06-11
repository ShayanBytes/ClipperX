"""
presets.py - content-type policy profiles.

A preset does NOT replace the decision engine; it TUNES it. Each profile is a small set
of overrides applied on top of config.CONFIG, biasing the same scene-mode machine toward
the behaviour a given kind of content wants. The user picks the context the engine can't
infer (see DESIGN.md "Presets").

V1 is people-centric only. Zoom-dependent behaviours (e.g. zoom-out on group laughter)
arrive with the spring/zoom camera (roadmap #4/#6). An object-salience "Action/Sports"
preset (track ball + players + goal) is a separate future module, deliberately out of
scope here.
"""
from __future__ import annotations

from typing import Dict, List

# name -> overrides merged onto CONFIG. Only keys that exist in config.py.
PRESETS: Dict[str, Dict] = {
    "auto": {},  # let the mode machine decide everything (default)

    "one_person": {
        # Lock to a single subject: detect ONE person, so DUAL/GROUP/split/two-shot can
        # never fire (cheaper, no false multi-person framing). Calm single follow.
        "max_people": 1,
    },

    "two_podcast": {
        # Sit-down interview: keep BOTH on screen often (two-shot / split), switch calmly.
        "max_people": 2,
        "speaker_switch_hold_frames": 14,   # reluctant to hard-cut between them
        "joint_hold_frames": 7,             # enter "show both" sooner
        "joint_release_frames": 16,         # leave it reluctantly (stay on the two-shot)
        "both_active_threshold": 0.008,     # more sensitive to "both engaged"
        "exchange_switch_count": 2,         # rapid back-and-forth -> two-shot readily
        "two_shot_margin_ratio": 0.10,      # co-fit a slightly wider pair
    },

    "two_dynamic": {
        # Energetic banter/debate: punch-in hard cuts to whoever's talking; little two-shot.
        "max_people": 2,
        "speaker_switch_hold_frames": 7,    # quick cuts to the active speaker
        "joint_hold_frames": 14,            # hard to enter "show both"
        "joint_release_frames": 8,          # drop it quickly
        "both_active_threshold": 0.013,     # only a strong joint moment counts
        "exchange_switch_count": 4,         # don't escalate to two-shot easily - let it cut
        "max_velocity_px_per_frame": 28.0,  # snappier pans
    },

    "group_podcast": {
        # 3+ seated panel: calm active-speaker focus. (True group centroid-fit + laughter
        # zoom-out arrive with roadmap #4/#6; for now this tunes pace + head-count.)
        "max_people": 5,
        "speaker_switch_hold_frames": 12,
    },

    "group_dynamic": {
        # 3+ lively (reactions, crowd): quicker, more people tracked.
        "max_people": 6,
        "speaker_switch_hold_frames": 8,
        "max_velocity_px_per_frame": 26.0,
    },
}

# Human-facing labels (for a future GUI dropdown).
PRESET_LABELS: Dict[str, str] = {
    "auto": "Auto (let the engine decide)",
    "one_person": "One person",
    "two_podcast": "Two people - podcast",
    "two_dynamic": "Two people - dynamic (non-podcast)",
    "group_podcast": "Three or more - podcast",
    "group_dynamic": "Three or more - dynamic",
}


def preset_names() -> List[str]:
    return list(PRESETS.keys())


def apply_preset(base: Dict, name: str) -> Dict:
    """Return a NEW config dict = `base` overlaid with the named preset's overrides."""
    key = (name or "auto").strip().lower()
    if key not in PRESETS:
        raise ValueError(f"Unknown preset '{name}'. Choose from: {', '.join(PRESETS)}")
    merged = dict(base)
    merged.update(PRESETS[key])
    return merged
