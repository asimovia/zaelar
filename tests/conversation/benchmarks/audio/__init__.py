"""Audio scenarios for the conversation ear: synthetic voice streams with exact ground truth, scored through the real
Flux (V2-941).

    voices.py     utterances from the engine's TTS providers (Inworld, OpenAI; macOS `say` as a fallback), cached
    compose.py    a scenario spec → one 16 kHz mono WAV + a label file (who said what, when, what is the user's turn)
    scenarios.py  the catalog of scenarios
    flux.py       a raw Flux dump (`flux_probe.raw`) + a VAD → the ear's signals, on the audio clock
    score.py      units (Flux turns, ear interventions, manager batches) against the labels
    probe.py      the runner: compose → Flux in real time → the ear and the manager → the score

Everything this writes goes under `tests/runs/conversation/audio/` (gitignored): synthetic voices only, no real
person's voice or words. Nothing is ever played through a speaker.
"""
