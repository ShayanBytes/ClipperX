# ClipperX Stage 5 — Social and Audio Intelligence

Stage 5 converts speech and reaction audio into structured social evidence before Stage 1 builds the causal story graph.

## Local acoustic analysis

The extracted 16 kHz waveform is analyzed without another cloud service. At regular intervals ClipperX measures:

- RMS energy and normalized loudness;
- fundamental pitch and voicing confidence;
- pitch range and variation;
- spectral centroid and zero-crossing rate;
- speaking rate, emphasis and arousal per utterance.

Only a downsampled acoustic timeline is stored in the output artifact.

## Conversation reconstruction

Whisper word timestamps and optional pyannote speakers are converted into bounded utterances. Stage 5 labels questions, statements, joke setups, laughter, agreement and disagreement, then creates social edges for:

- responses;
- interruptions;
- agreement and disagreement;
- laughter directed at a preceding utterance.

Raw pyannote overlap regions are preserved even when two speakers talk simultaneously.

## Multimodal reaction detection

Reaction candidates combine three independent evidence sources:

- laughter language in the transcript;
- acoustic rhythm, pitch variability and energy bursts;
- simultaneous visible mouth motion from persistent people.

Nearby candidates are merged. Multiple visible participants produce a `groupReaction`, ensuring the story brain can require all meaningful reactors rather than framing only one person.

## Setup and payoff chains

A high-confidence reaction occurring shortly after a question, joke phrase or conversational setup creates a bounded causal hypothesis linking the setup utterance to the reaction payoff. The Stage 1 API still verifies this against the full video and supplied evidence.

## Visible identity attachment

After active-speaker mapping, utterance speakers are attached to Stage 4 canonical person identities. This makes speaker changes, interruptions, joke setups and reactions usable by composition and rendering.

## Artifact

`social-intelligence.json` contains utterances, prosody, conversation edges, overlap regions, reactions, joke chains, speaker-person mappings and a compact acoustic timeline.
