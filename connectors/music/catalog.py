"""connectors/music/catalog.py — ONE door to the music CATALOGUE: search, an artist, an album (V2-795).

The player (`connectors.music.control`) answers «play this»; this answers «what is there». Two sources, in order:

1. a CONNECTED provider whose contract implements the catalogue (`search_catalog` / `artist_page` /
   `album_page` — Spotify today): its results carry the provider's own `uri`, so they play exactly;
2. otherwise the free iTunes Search metadata (`itunes.py`): results carry no `uri` and play by their WORDS
   through whichever player is active (the free YouTube audio with no account at all).

If neither answers, a search still returns the tracks the first connected provider's plain `search()` finds, so
«search» never comes back emptier than «play» would have been.

Every item is a plain dict, the same keys whatever the source (`track_dict` and the provider/iTunes builders):
  track    {title, artist, album, art, uri, id, duration_ms, query, provider, source}
  artist   {id, name, art, uri, source}
  album    {id, name, artist, art, year, uri, source}
  playlist {id, name, owner, art, uri, count, source}
Network I/O, synchronous, never raises.
"""
from __future__ import annotations

import logging

from . import itunes, registry
from .base import Track

logger = logging.getLogger("zaelar.music.catalog")

_EMPTY = ("tracks", "artists", "albums", "playlists")


def track_dict(t: Track, provider: str = "") -> dict:
    title, artist = t.title or "", t.artist or ""
    return {"title": title, "artist": artist, "album": t.album or "", "art": t.art or "", "uri": t.uri or "",
            "id": t.id or "", "duration_ms": int(t.duration_ms or 0),
            "query": " ".join(x for x in (title, artist) if x), "provider": provider, "source": provider}


def _providers() -> list:
    try:
        return registry.available()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"music catalogue: provider registry failed: {e!r}")
        return []


def _ask(prov, method: str, *args):
    try:
        return getattr(prov, method)(*args)
    except Exception as e:  # noqa: BLE001 — one provider failing hands over to the next source
        logger.warning(f"music catalogue: {prov.name}.{method} failed: {e!r}")
        return None


def search(query: str, limit: int = 8) -> dict:
    """{query, source, tracks, artists, albums, playlists}."""
    q = (query or "").strip()
    out = {"query": q, "source": "", **{k: [] for k in _EMPTY}}
    if not q:
        return out
    provs = _providers()
    for prov in provs:
        got = _ask(prov, "search_catalog", q, limit)
        if got and any(got.get(k) for k in _EMPTY):
            return {**out, **{k: list(got.get(k) or []) for k in _EMPTY}, "source": prov.name}
    got = itunes.search(q, limit)
    if any(got.get(k) for k in _EMPTY):
        return {**out, **got, "source": "itunes"}
    for prov in provs:
        hits = _ask(prov, "search", q, 3) or []
        if hits:
            return {**out, "tracks": [track_dict(t, prov.name) for t in hits], "source": prov.name}
    return out


def _page(kind: str, ref: dict) -> "dict | None":
    method = "artist_page" if kind == "artist" else "album_page"
    src, rid = str(ref.get("source") or ""), str(ref.get("id") or "")
    if rid:
        if src == "itunes":
            return (itunes.artist if kind == "artist" else itunes.album)(rid)
        for prov in _providers():
            if not src or prov.name == src:
                got = _ask(prov, method, rid)
                if got:
                    return got
    name = str(ref.get("name") or "").strip()
    if not name:
        return None
    words = " ".join(x for x in (name, str(ref.get("artist") or "")) if x)
    hits = search(words, 6).get("artists" if kind == "artist" else "albums") or []
    first = next((h for h in hits if h.get("id")), None)
    if first is None:
        return None
    return _page(kind, {"id": first["id"], "source": first.get("source", "")})


def artist(ref: dict) -> "dict | None":
    """{artist, top, albums} for `{id, source}` — or for `{name}`, found by searching it first."""
    return _page("artist", ref or {})


def album(ref: dict) -> "dict | None":
    """{album, tracks} for `{id, source}` — or for `{name[, artist]}`, found by searching it first."""
    return _page("album", ref or {})
