"""One order across channels: by ONSET — when the person began — never by channel or by arrival (§7.1).

Pure functions over inbox rows. A typed text that arrives while a voice intervention of the same account began
earlier and is still open waits behind it (bounded by `cross_channel_hold_ms`); when the voice closes, both go in one
batch in the order they were begun, each with its channel label. Nothing here compares the two texts: whether the text
corrects what was said is the model's to read.
"""
from __future__ import annotations


def batch_key(row: dict) -> tuple:
    """Within a batch: onset, then acceptance, then id."""
    return (row["onset"], row["accepted"], row["id"])


def order(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=batch_key)


def waits_for_voice(entries: list[tuple[int, str | None]], voices: list[tuple[str, int, str | None]], now: int,
                    window_ms: int, bound_ms: int) -> str | None:
    """The publication hold — ONE predicate for the inbox (before a run starts), an onset during a run, and the check
    before sealing: the open voice a batch waits for, or None.

    `entries` are the batch's (close, device); `voices` the open ones (intervention, onset, device). A voice holds the
    batch when it is open on ANY device that contributed an entry, and began within `window_ms` of the close of the
    last entry that device contributed — even before it (he went on while the provider was ending). Bounded: never
    once `bound_ms` have passed since the close of the batch's last entry."""
    if not entries or now - max(at for at, _ep in entries) >= bound_ms:
        return None
    last: dict = {}
    for at, ep in entries:
        if ep:
            last[ep] = max(last.get(ep, at), at)
    return next((iv for iv, onset, ep in voices if ep in last and onset - last[ep] <= window_ms), None)


def publish_at(voice_entries: list[tuple[int, bool | None]], terminal_ms: int, nonterminal_ms: int) -> int | None:
    """When a batch may publish: the latest grace of its voice entries (close, terminal) — a long one after a close
    with no sentence mark, a short one otherwise (unknown reads as a mark). None: no voice entry, no grace."""
    return max((at + (nonterminal_ms if terminal is False else terminal_ms) for at, terminal in voice_entries),
               default=None)


def hold_behind(text_onset: int, open_voice: dict[str, dict]) -> str | None:
    """The open voice intervention a text must wait behind: the EARLIEST one that began before the text."""
    earlier = [(v["onset"], iv) for iv, v in open_voice.items() if v["onset"] < text_onset]
    return min(earlier)[1] if earlier else None
