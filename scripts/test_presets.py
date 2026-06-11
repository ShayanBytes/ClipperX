"""Sanity checks for the preset policy layer (no video needed)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CONFIG
from presets import apply_preset, preset_names, PRESETS

checks = []

# auto is a no-op overlay (same values as base, but a distinct dict)
auto = apply_preset(CONFIG, "auto")
checks.append(("auto preserves max_people", auto["max_people"] == CONFIG["max_people"]))
checks.append(("apply_preset returns a copy", auto is not CONFIG))

# one_person locks to a single subject
one = apply_preset(CONFIG, "one_person")
checks.append(("one_person -> max_people 1", one["max_people"] == 1))

# two_podcast favours showing both: easier to enter, calmer switching
pod = apply_preset(CONFIG, "two_podcast")
checks.append(("two_podcast -> max_people 2", pod["max_people"] == 2))
checks.append(("two_podcast enters show-both sooner",
               pod["joint_hold_frames"] < CONFIG["joint_hold_frames"]))
checks.append(("two_podcast switches more calmly",
               pod["speaker_switch_hold_frames"] > CONFIG["speaker_switch_hold_frames"]))

# two_dynamic favours punch-in cuts: harder to enter show-both, quicker cuts
dyn = apply_preset(CONFIG, "two_dynamic")
checks.append(("two_dynamic harder to show-both",
               dyn["joint_hold_frames"] > CONFIG["joint_hold_frames"]))
checks.append(("two_dynamic cuts quicker",
               dyn["speaker_switch_hold_frames"] < CONFIG["speaker_switch_hold_frames"]))

# base config is never mutated
checks.append(("base CONFIG untouched", CONFIG["max_people"] == CONFIG["max_people"] and
               apply_preset(CONFIG, "one_person")["max_people"] == 1 and CONFIG["max_people"] != 1))

# unknown preset raises
try:
    apply_preset(CONFIG, "nope")
    checks.append(("unknown preset raises", False))
except ValueError:
    checks.append(("unknown preset raises", True))

print(f"presets available: {', '.join(preset_names())}\n")
ok = True
for name, passed in checks:
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    ok = ok and passed
sys.exit(0 if ok else 1)
