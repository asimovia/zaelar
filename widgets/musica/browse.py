"""Search and browse — the catalogue half of the music card (V2-795).

`search {query}` and `open_view {kind: artist|album}` ask `connectors.music.catalog` (the connected streaming
account's catalogue, or the free iTunes metadata) and keep the answer in the card's store under `browse`, so the
card paints it with no network of its own and a re-render never asks twice. `play_album` plays a whole album: by
the provider's own uri when it can (Spotify), otherwise first track now and the rest queued by their words — the
same road a list of the operator's takes.

Every network call happens BEFORE the store is read, so a playback the connector writes meanwhile is never
overwritten by a stale snapshot (the V2-650 lesson).
"""
from __future__ import annotations

from loguru import logger as _log

from . import data as _d

#: What the card keeps of one answer — enough to paint and to play, small enough for the store.
_CAP = {"tracks": 10, "artists": 8, "albums": 12, "playlists": 8, "top": 10}


def _trim(page: dict) -> dict:
    return {k: (v[:_CAP[k]] if k in _CAP and isinstance(v, list) else v) for k, v in (page or {}).items()}


def _keep(kind: str, page: dict, view: dict) -> dict:
    db = _d._load_db()
    browse = dict(db.get("browse") or {})
    browse[kind] = _trim(page)
    db["browse"] = browse
    db["view"] = view
    _d._persist(db)
    return db


def a_search(action: str, p: dict) -> dict:
    query = str(p.get("query") or p.get("q") or "").strip()
    if not query:
        return {"ok": False, "error": "missing_query", "message": "What should I search for? Say a song, an artist or an album."}
    from connectors.music import catalog
    res = catalog.search(query)
    _keep("search", res, {"kind": "search", "id": ""})
    counts = {k: len(res.get(k) or []) for k in ("tracks", "artists", "albums", "playlists")}
    out = {"ok": True, "query": query, "source": res.get("source", ""), **counts}
    # What the turn can NAME without a second look: the first few songs, the first artist and album.
    out["top"] = [f"{t.get('title')} — {t.get('artist')}".strip(" —") for t in (res.get("tracks") or [])[:3]]
    if not any(counts.values()):
        out["message"] = f"Nothing found for «{query}»."
    return out


def open_page(kind: str, p: dict) -> dict:
    """`open_view {kind: artist|album, id|name[, artist, source]}` — fetch the page, keep it, show it."""
    from connectors.music import catalog
    ref = {"id": str(p.get("id") or "").strip(), "source": str(p.get("source") or "").strip(),
           "name": str(p.get("name") or p.get(kind) or "").strip(), "artist": str(p.get("artist") or "").strip()}
    if ref["id"] and not ref["source"]:
        held = (((_d._load_db().get("browse") or {}).get(kind) or {}).get(kind) or {})
        if held.get("id") == ref["id"]:
            return _show(kind, held)                   # already on the card: no second trip
    if not ref["name"] and not ref["id"]:
        ref["name"] = ref["id"]
    page = (catalog.artist if kind == "artist" else catalog.album)(ref)
    if not page:
        what = ref["name"] or ref["id"]
        return {"ok": False, "error": f"{kind}_not_found", "message": f"I could not find «{what}» in the catalogue."}
    db = _keep(kind, page, {"kind": kind, "id": str((page.get(kind) or {}).get("id") or "")})
    return {"ok": True, "view": db["view"], "name": (page.get(kind) or {}).get("name", "")}


def _show(kind: str, held: dict) -> dict:
    db = _d._load_db()
    db["view"] = {"kind": kind, "id": held.get("id", "")}
    _d._persist(db)
    return {"ok": True, "view": db["view"], "name": held.get("name", "")}


def a_play_album(action: str, p: dict) -> dict:
    """A whole album (or a catalogue playlist): `{uri}` / `{id, source}` / `{album|name[, artist]}`."""
    from connectors import music
    from connectors.music import catalog
    uri = str(p.get("uri") or "").strip()
    label = str(p.get("album") or p.get("name") or "").strip()
    if uri:
        r = music.play_context(uri, label)
        if r.ok:
            _d._save_view()
            return {"ok": True, "message": r.message, "album": label}
    ref = {"id": str(p.get("id") or "").strip(), "source": str(p.get("source") or "").strip(),
           "name": label, "artist": str(p.get("artist") or "").strip()}
    if not ref["id"] and not ref["name"]:
        return {"ok": False, "error": "missing_album", "message": "Which album? Say its name (and the artist if you know it)."}
    page = catalog.album(ref)
    if not page or not page.get("tracks"):
        return {"ok": False, "error": "album_not_found", "message": f"I could not find the album «{label or ref['id']}»."}
    meta = page.get("album") or {}
    if meta.get("uri"):
        r = music.play_context(meta["uri"], meta.get("name", ""))
        if r.ok:
            _keep("album", page, {"kind": "album", "id": str(meta.get("id") or "")})
            return {"ok": True, "message": r.message, "album": meta.get("name", "")}
        _log.debug(f"musica: album by uri refused ({r.reason}), playing it track by track")
    from .actions import play_sequence
    r = play_sequence(list(page["tracks"]))
    _keep("album", page, {"kind": "album", "id": str(meta.get("id") or "")})
    return {"ok": r.get("ok", False), "message": r.get("message", ""), "album": meta.get("name", ""),
            "tracks": len(page["tracks"])}
