"""connectors/music/ — SHARED music layer, provider-agnostic (V2-041).

Single facade used by FlashBrain (tool `play_music`) and — as a SEPARATE piece, later — the music widget. Routes the
intent ("play music", "play Frank Sinatra", "pause", "turn up the volume") to the CONNECTED provider (Spotify today;
the seam accepts any streaming connector). Never raises to the caller: returns a `MusicResult` with a speakable
sentence. Network I/O -> caller runs it with `asyncio.to_thread` (respects V2-011).
"""
from __future__ import annotations

import logging

from . import registry
from .base import MusicProvider, MusicResult, NowPlaying, Track

logger = logging.getLogger("zaelar.music")

# Control actions WITHOUT data (all except 'play', which may carry query/uri).
_CONTROL = {"pause", "resume", "next", "previous", "stop"}
_VOLUME = {"volume_up", "volume_down", "set_volume"}

def _msg(key: str) -> str:
    """A seam line (no provider / a provider failure) in the active language — the words live in the `voice`
    pack (`music.<key>`), so a generated language says its own and never inherits Spanish."""
    from i18n import langs as _langs
    return _langs.words(f"music.{key}", default="")


def active_provider(prefer: str = "") -> "MusicProvider | None":
    return registry.active(prefer)


def available() -> "list[str]":
    """Names of providers connected right now."""
    return [p.name for p in registry.available()]


def control(action: str, query: str = "", uri: str = "", percent: int = 0, prefer: str = "",
            seconds: float = 0.0, relative: bool = False) -> MusicResult:
    """Execute ONE music action against the active provider. `action`: play|pause|resume|next|previous|stop|
    volume_up|volume_down|set_volume|seek. FlashBrain facade — fail-safe, never raises."""
    action = (action or "play").strip().lower()
    prov = active_provider(prefer)
    if prov is None:
        return MusicResult(ok=False, action=action, reason="no_provider", message=_msg("no_provider"))
    try:
        if action == "play":
            return prov.play(query=query, uri=uri)
        if action == "pause":
            return prov.pause()
        if action in ("resume", "reanuda", "sigue"):
            return prov.resume()
        if action == "next":
            return prov.next()
        if action in ("previous", "prev", "back"):
            return prov.previous()
        if action == "stop":                       # 'stop' = pause (stop music, not kill processes)
            return prov.pause()
        if action == "queue":                       # V2-047 F4: add to queue (one after another)
            return prov.enqueue(query=query, uri=uri)
        if action == "ended":                       # V2-047 F4: widget says it ended -> next from queue
            return prov.on_ended()
        if action == "volume_up":
            np = prov.now_playing()
            cur = (np.volume if np and np.volume is not None else 60)
            return prov.set_volume(min(100, cur + 15))
        if action == "volume_down":
            np = prov.now_playing()
            cur = (np.volume if np and np.volume is not None else 60)
            return prov.set_volume(max(0, cur - 15))
        if action == "set_volume":
            return prov.set_volume(max(0, min(100, int(percent or 0))))
        if action == "seek":                        # V2-717: to a position, or by a number of seconds
            return prov.seek(float(seconds or 0.0), bool(relative))
    except Exception as e:  # noqa: BLE001 — a provider failure never breaks voice
        logger.warning(f"music.control({action}) falló: {e!r}")
        return MusicResult(ok=False, provider=prov.name, action=action, reason="error",
                           message=_msg("done"))
    return MusicResult(ok=False, provider=prov.name, action=action, reason="error", message=_msg("done"))


def resolve(query: str) -> "Track | None":
    """The playable track a «title — artist» names, WITHOUT playing it: the first connected provider that finds it,
    in the registry's priority order (a connected streaming account first, the free YouTube-audio last). None when
    no provider is connected or none finds it. Network I/O, fail-safe: never raises."""
    q = (query or "").strip()
    if not q:
        return None
    for prov in registry.available():
        try:
            hits = prov.search(q, limit=1)
        except Exception as e:  # noqa: BLE001 — one provider failing hands over to the next
            logger.warning(f"music.resolve via {prov.name} failed: {e!r}")
            continue
        if hits:
            return hits[0]
    return None


def now_playing(prefer: str = "") -> "NowPlaying | None":
    prov = active_provider(prefer)
    if prov is None:
        return None
    try:
        return prov.now_playing()
    except Exception:  # noqa: BLE001
        return None


def status() -> dict:
    """State of ALL known providers (for UI/wizard/diagnostics)."""
    out = {}
    for p in registry.providers():
        try:
            out[p.name] = p.status()
        except Exception:  # noqa: BLE001
            out[p.name] = {"provider": p.name, "connected": False}
    return {"providers": out, "available": available()}


__all__ = ["control", "resolve", "now_playing", "status", "available", "active_provider",
           "MusicProvider", "MusicResult", "NowPlaying", "Track", "registry"]
