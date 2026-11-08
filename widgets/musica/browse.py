"""Search and browse — the catalogue half of the music card (V2-795).

`search {query}` and `open_view {kind: artist|album}` ask `connectors.music.catalog` (the connected streaming
account's catalogue, or the free iTunes metadata) and keep the answer in the card's store under `browse`, so the
card paints it with no network of its own and a re-render never asks twice. `play_album` plays a whole album, list or
podcast: by the provider's own uri when it can (Spotify), otherwise THE SAME object's tracks (read by that uri), the
first now and the rest queued by their words — the same road a list of the operator's takes. A uri is never traded
for a search of its name (V2-860 F1).

Every network call happens BEFORE the store is read, so a playback the connector writes meanwhile is never
overwritten by a stale snapshot (the V2-650 lesson).
"""
from __future__ import annotations

from loguru import logger as _log


#: What the card keeps of one answer — enough to paint and to play, small enough for the store.
_CAP = {"tracks": 10, "artists": 8, "albums": 12, "playlists": 8, "shows": 8, "top": 10}


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
    from search import media
    held: dict = {}

    def _catalogue(q: str) -> dict:
        held.update(catalog.search(q))
        return held
    got = media.find_media(query, catalogue=_catalogue, video=False)   # the one ranking voice, card and worker share
    res = held or {"query": query, "source": ""}
    _keep("search", res, {"kind": "search", "id": ""})
    counts = {k: len(res.get(k) or []) for k in ("tracks", "artists", "albums", "playlists", "shows")}
    out = {"ok": True, "query": query, "source": res.get("source", ""), **counts}
    # What the turn can NAME without a second look: the first few songs, the first artist and album.
    out["top"] = [f"{t.get('title')} — {t.get('artist')}".strip(" —") for t in (res.get("tracks") or [])[:3]]
    # …and what can be PLAYED, best fit first, each with its own handle (`play_album {uri}` for a whole) (V2-860 T2.4).
    out["candidates"] = [media.public(c) for c in got["candidates"][:6]]
    whole = media.named_whole(query, got["candidates"])
    if whole is not None:
        out["named"] = media.public(whole)
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
        # THE object of the uri, through the one rule the voice's «play X» takes (`music.play_whole`): its uri where
        # it can sound, else its own songs, else why not — never its name searched again (V2-860 T2.4: on the phone
        # the list «Sueñacuentos» became another album, chapter by chapter).
        page: dict = {}
        r = music.play_whole(uri, label, opened=page)
        if page.get("tracks"):
            meta = dict(page.get("context") or {})
            _keep("album", {"album": meta, "tracks": page["tracks"]}, {"kind": "album", "id": str(meta.get("id") or "")})
        elif r.ok:
            _d._save_view()
        out = {"ok": bool(r.ok), "message": r.message, "album": (page.get("context") or {}).get("name", "") or label,
               "uri": uri, **({"tracks": len(page["tracks"])} if page.get("tracks") else {})}
        return out if r.ok else {**out, "error": r.reason or "context_unreadable"}
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


# ── A request said to the agent (V2-861) ──────────────────────────────────────────────────────────────────────────
# «put some list in spotify, look for Sueñacuentos» left the card on the song that sounded before, and nothing on screen
# said what was found. A NEW request opens the card on its search, blank, with his words — and the act's answer (the
# catalogue's answer, the numbered candidates, the one started) is written back, so the card shows what was found and
# the turn can name the others («not this one» → the list with their owners). «Open the music» never comes here: the
# card then stays as it was.

def begin_search(query: str) -> None:
    """The card on the search for his words, blank, while the act runs. Never raises."""
    q = " ".join(str(query or "").split())
    if not q:
        return
    try:
        db = _d._load_db()
        browse = dict(db.get("browse") or {})
        browse["search"] = {"query": q, "pending": True}
        db["browse"] = browse
        db["view"] = {"kind": "search", "id": ""}
        _d._persist(db)
    except Exception as e:  # noqa: BLE001 — the card's look never breaks the act
        _log.debug(f"musica: search not begun for {q!r}: {e!r}")


def after_play(query: str, res) -> None:
    """Write back what the act found and started, and move the view: the whole that sounds opens on its page, a song
    on Now playing, and a start that failed stays on the search so he sees what was found. Never raises."""
    q = " ".join(str(query or "").split())
    if not q:
        return
    try:
        extra = getattr(res, "extra", None) or {}
        found = extra.get("found") or {}
        ok = bool(getattr(res, "ok", False))
        chosen = str(found.get("chosen") or "")
        page: dict = {}
        if ok and chosen and chosen.split(":")[1:2] != ["track"]:
            from connectors.music import catalog
            page = catalog.context(chosen) or {}                 # network BEFORE the store is read (V2-650)
        db = _d._load_db()
        browse = dict(db.get("browse") or {})
        browse["search"] = {**_trim(found.get("answer") or {}), "query": q,
                            "candidates": list(found.get("candidates") or []), "chosen": chosen,
                            **({} if ok else {"failed": str(getattr(res, "reason", "") or "")})}
        if page.get("tracks"):
            meta = dict(page.get("context") or {})
            browse["album"] = _trim({"album": meta, "tracks": page["tracks"]})
            db["view"] = {"kind": "album", "id": str(meta.get("id") or "")}
        elif ok:
            db["view"] = {"kind": "now", "id": ""}
        else:
            db["view"] = {"kind": "search", "id": ""}
        db["browse"] = browse
        _d._persist(db)
    except Exception as e:  # noqa: BLE001
        _log.debug(f"musica: the act's findings not kept for {q!r}: {e!r}")


def found_rows() -> list:
    """The candidates on the card's search, numbered as the digest numbers them: [{kind, name, owner, uri, …}]."""
    try:
        return list(((_d._load_db().get("browse") or {}).get("search") or {}).get("candidates") or [])
    except Exception as e:  # noqa: BLE001
        _log.debug(f"musica: candidates unreadable: {e!r}")
        return []


def a_play_result(action: str, p: dict) -> dict:
    """`play_result {item: N | name | owner}` — one of the candidates the card found, picked by its number, its name
    or its owner («the one by irene»), through the resolver the video card uses (`widgets/result_refs`). A whole plays
    by its uri (`music.play_whole`), a song by its uri or its words. Two rows carrying his words are asked, never
    guessed."""
    from widgets import result_refs as _rr
    rows = found_rows()
    if not rows:
        return {"ok": False, "error": "no_results", "message": "There are no search results on the card right now."}
    ref = p.get("item") if p.get("item") is not None else p.get("n")
    i = _rr.resolve([{"title": r.get("name", ""), "channel": r.get("owner", "")} for r in rows], ref)
    if i is None:
        return {"ok": False, "error": "item_not_found", "item": ref, "count": len(rows),
                "options": [f"{n}. {r.get('name', '')}" + (f" — {r['owner']}" if r.get("owner") else "")
                            for n, r in enumerate(rows, 1)],
                "message": "Which one? Say its number, its name or who made it."}
    row = rows[i]
    from connectors import music
    if row.get("kind") in ("show", "playlist", "album") and row.get("uri"):
        r = music.play_whole(str(row["uri"]), str(row.get("name") or ""), str(row.get("kind") or ""))
    else:
        r = music.control("play", "" if row.get("uri") else str(row.get("name") or ""), str(row.get("uri") or ""))
    # the pick becomes the chosen one, and the card moves exactly as a spoken request does
    found = {"answer": {k: v for k, v in ((_d._load_db().get("browse") or {}).get("search") or {}).items()
                        if k in _CAP}, "candidates": rows, "chosen": str(row.get("uri") or "")}
    r.extra = {**(r.extra or {}), "found": found}
    after_play(str(((_d._load_db().get("browse") or {}).get("search") or {}).get("query") or row.get("name") or ""), r)
    return {"ok": bool(r.ok), "message": r.message, "position": i + 1, "name": row.get("name", ""),
            "owner": row.get("owner", ""), **({} if r.ok else {"error": r.reason or "error"})}


from . import data as _d  # noqa: E402 — read at call time: data owns the store and imports this module's actions
