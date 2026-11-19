"""One order across channels: by ONSET — when the person began — never by channel or by arrival (§7.1).

Pure functions over inbox rows. A typed text that arrives while a voice intervention of the same account began
earlier and is still open waits behind it (bounded by `cross_channel_hold_ms`); when the voice closes, both go in one
batch in the order he began them, each with its channel label. Nothing here compares the two texts: whether the text
corrects what was said is the model's to read.
"""
from __future__ import annotations


def batch_key(row: dict) -> tuple:
    """Within a batch: onset, then acceptance, then id."""
    return (row["onset"], row["accepted"], row["id"])


def order(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=batch_key)


def hold_behind(text_onset: int, open_voice: dict[str, dict]) -> str | None:
    """The open voice intervention a text must wait behind: the EARLIEST one that began before the text."""
    earlier = [(v["onset"], iv) for iv, v in open_voice.items() if v["onset"] < text_onset]
    return min(earlier)[1] if earlier else None
