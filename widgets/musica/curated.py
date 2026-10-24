"""Several songs into one list, each one mapped to a PLAYABLE track — the resource a list built by somebody else
(a Brain Worker, a second pass) appends with (`add_tracks`).

Why it is its own op and not N calls of `add_to_playlist`: a list somebody CURATES («forty songs for a birthday»)
arrives a few names at a time, and each name has to become something the player can start — the connected
streaming account if there is one, another connected account if not, the free YouTube-audio last
(`connectors.music.resolve`, the registry's own priority order). A name no provider finds is still kept, as its
words: playing the list re-resolves it then, so nothing he was promised is dropped on the way.

Bounded on purpose: at most `MAX_PER_CALL` names per call (the list grows call after call, which is what lets him
watch it grow) and a wall-clock budget for the lookups, so one slow provider never holds the card.
"""
from __future__ import annotations

import concurrent.futures as _cf
import time

from loguru import logger as _log

#: Names one call may carry. A longer list is several calls — that is the «little by little» he sees.
MAX_PER_CALL = 25
#: Seconds the lookups of one call may take, all together. What is not resolved by then keeps its words.
RESOLVE_BUDGET_S = 20.0
_WORKERS = 6


def _names(raw) -> list:
    """The payload's songs as a list of `str | dict`, whatever shape the caller used (a list, or one string with a
    song per line)."""
    if isinstance(raw, str):
        raw = [ln for ln in raw.splitlines()]
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if isinstance(item, dict) and (item.get("title") or item.get("query")):
            out.append(item)
        elif isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _resolve_one(track: dict) -> dict:
    from connectors import music
    from . import data as _d
    hit = music.resolve(_d._track_query(track))
    if hit is None:
        return track
    resolved = _d._track_from_resolved(_d._track_query(track), hit)
    # The caller's own title/artist win over a provider's label («Official Video», a channel name as artist).
    for key in ("title", "artist"):
        if track.get(key):
            resolved[key] = track[key]
    resolved["provider"] = _provider_of(hit)
    return resolved


def _provider_of(hit) -> str:
    uri = str(getattr(hit, "uri", "") or "")
    return uri.split(":", 1)[0] if ":" in uri else ""


def resolve(raw) -> tuple[list, int]:
    """`(tracks, resolved_count)` for the payload's songs, in the order given. Never raises."""
    from . import data as _d
    tracks = []
    for item in _names(raw)[:MAX_PER_CALL]:
        tr = _d._track_from_payload(item if isinstance(item, dict) else {"query": item})
        if tr:
            if tr.get("artist") and tr.get("query") == tr.get("title"):
                tr["query"] = f"{tr['title']} {tr['artist']}"      # what a provider (and a later replay) searches
            tracks.append(tr)
    if not tracks:
        return [], 0
    out = list(tracks)
    deadline = time.monotonic() + RESOLVE_BUDGET_S
    ex = _cf.ThreadPoolExecutor(max_workers=_WORKERS)
    try:
        futs = {ex.submit(_resolve_one, t): i for i, t in enumerate(tracks)}
        for fut in futs:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            try:
                out[futs[fut]] = fut.result(timeout=left)
            except Exception as e:  # noqa: BLE001 — a lookup that fails or overruns keeps the song's words
                _log.debug(f"musica: track lookup failed, the song keeps its words: {e!r}")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return out, sum(1 for t in out if t.get("uri"))


def playable_uri(track: dict, active: str) -> str:
    """The uri to hand the player: the track's own when it was resolved by the provider playing now (or carries no
    provider mark), "" otherwise — then the player resolves the song by its words. A list resolved on YouTube keeps
    playing after a streaming account is connected, and the other way round."""
    uri = str(track.get("uri") or "")
    prov = str(track.get("provider") or "")
    if not uri or not prov or not active:
        return uri
    return uri if prov == _scheme_of(active) else ""


def _scheme_of(provider_name: str) -> str:
    return {"youtube": "yt"}.get(provider_name, provider_name)
