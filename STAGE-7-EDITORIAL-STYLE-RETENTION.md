# ClipperX Stage 7 — Editorial Style and Retention Director

Stage 7 gives the verified story and composition plan a consistent editorial language. It does not invent events, remove required subjects or reorder cause and effect.

## Retention map

Each composition segment receives a bounded score from:

- Stage 1 narrative importance;
- Stage 5 utterance arousal and questions;
- multimodal reaction confidence;
- Stage 6 verified action outcomes.

Segments are labeled as setup hook, dialogue, action, action payoff, reaction payoff or breathing space. An early hook candidate is identified for reporting and emphasis, but cold-open reordering is disabled so causal chronology remains intact.

## Profile-specific camera language

- **Podcast:** stable cameras, longer minimum cut intervals, conversational captions and generous reaction holds.
- **Sports:** wider action coverage, faster predictive response and energetic but bounded transitions.
- **Cinematic:** contextual framing, slower camera response, restrained separators and editorial typography.
- **Social:** tighter framing, denser captions and faster—but still limited—cut rhythm.
- **Balanced:** neutral defaults suitable for mixed footage.

The renderer executes the selected crop scale, smoothing, canvas color, separator color and gap scale per segment.

## Transition discipline

Stage 7 suppresses unnecessary cuts when segments are too close or use the same visual language. Continuous actions retain `action_continuity`. Reaction and action payoffs receive profile-specific hold guidance. The number, timestamps and must-show tracks of Stage 2 segments are preserved.

## Subtitle direction

ASS generation now accepts profile-specific font, size, density, outline, safe margins, primary color and highlight color. Subtitle placement remains inside the vertical title-safe region.

## Artifacts

- `editorial-plan.json`
- Updated `composition-plan.json` with per-segment editorial instructions
- Profile-styled `subtitles.ass`
- Stage 3 render telemetry includes the active editorial beat role
