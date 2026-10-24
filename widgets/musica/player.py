"""Play modes, the queue and the volume — the transport half a real player has and the card lacked (V2-795).

All of it goes through the music facade (`connectors.music`), which hands it to whichever provider is playing:
Spotify does shuffle/repeat/its queue over its own API; the free YouTube audio keeps them in the store and applies
them when a song ends. The card never moves a playhead or a queue itself.

What the card SHOWS is composed here too (`modes`, `queue_view`, `volume`): read from what the connector already
wrote — never a network call on the render path. Spotify's queue is the one thing that lives elsewhere, so it is
read when the queue face is opened (`refresh_spotify_queue`) and painted from that snapshot.
"""
from __future__ import annotations

from loguru import logger as _log

from . import data as _d

_REPEATS = ("off", "one", "all")
#: The repeat button's cycle, the one every mainstream player uses: off → the whole queue → this song → off.
_CYCLE = {"off": "all", "all": "one", "one": "off"}


def _result(r) -> dict:
    return {"ok": bool(getattr(r, "ok", False)), "message": getattr(r, "message", ""),
            "reason": getattr(r, "reason", "")}


def _flag(v, default: bool = True) -> bool:
    if v is None or v == "":
        return default
    if isinstance(v, str):
        return v.strip().lower() not in ("false", "0", "off", "no")
    return bool(v)


# ── play modes ───────────────────────────────────────────────────────────────────────────────────────────
def a_shuffle(action: str, p: dict) -> dict:
    from connectors import music
    on = _flag(p.get("on", p.get("state")))
    res = _result(music.set_mode(shuffle=on))
    _d._save_view()
    return {**res, "shuffle": on}


def a_repeat(action: str, p: dict) -> dict:
    from connectors import music
    mode = str(p.get("mode") or p.get("state") or "").strip().lower()
    if mode not in _REPEATS:
        cur = modes(_d._live_fields(_d._load_db())).get("repeat", "off")
        mode = _CYCLE.get(cur, "all")      # no mode = the next step of the button's own cycle
    res = _result(music.set_mode(repeat=mode))
    _d._save_view()
    return {**res, "repeat": mode}


def modes(live: dict) -> dict:
    """{shuffle, repeat, supported} for the bar — read from the store / the last Spotify reading."""
    np = live.get("now_playing") or {}
    if live.get("mode") == "spotify":
        return {"shuffle": bool(np.get("shuffle")), "repeat": str(np.get("repeat") or "off"), "supported": True}
    yt = live.get("yt") or {}
    if live.get("mode") == "youtube":
        return {"shuffle": bool(yt.get("shuffle")), "repeat": str(yt.get("repeat") or "off"), "supported": True}
    return {"shuffle": False, "repeat": "off", "supported": False}


# ── volume ───────────────────────────────────────────────────────────────────────────────────────────────
def volume(live: dict, db: dict) -> dict:
    np = live.get("now_playing") or {}
    yt = live.get("yt") or {}
    level = np.get("volume") if live.get("mode") == "spotify" else yt.get("volume")
    level = int(level) if isinstance(level, (int, float)) else None
    return {"level": level, "muted": level == 0 or bool(yt.get("muted") and live.get("mode") == "youtube"),
            "restore": int(db.get("mute_restore") or 0)}


def mute(p: dict) -> "dict | None":
    """`set_volume {mute}`: silence remembering the level, or give the remembered level back. None = not a mute
    call (an ordinary `set_volume {level}`)."""
    if "mute" not in p:
        return None
    from connectors import music
    db = _d._load_db()
    vol = volume(_d._live_fields(db), db)
    if _flag(p.get("mute")):
        if vol["level"]:
            db["mute_restore"] = vol["level"]
            _d._persist(db)
        r = music.control("set_volume", percent=0)
    else:
        r = music.control("set_volume", percent=int(db.get("mute_restore") or 0) or 60)
    _d._save_view()
    return _result(r)


# ── the queue ────────────────────────────────────────────────────────────────────────────────────────────
def _known(db: dict) -> dict:
    """query → the richest track the card already holds for it (lists, recent, top), to paint a bare query."""
    out: dict = {}
    pools = [t for pl in (db.get("playlists") or []) for t in (pl.get("tracks") or [])]
    pools += list(db.get("recent") or []) + list((db.get("counts") or {}).values())
    for t in pools:
        q = _d._norm(_d._track_query(t))
        if q and (q not in out or (t.get("art") and not out[q].get("art"))):
            out[q] = t
    return out


def queue_view(live: dict, db: dict) -> dict:
    """{items, editable, source} — the free player's queue straight from the store; Spotify's from its snapshot."""
    if live.get("mode") == "youtube":
        known = _known(db)
        items = []
        for q in ((db.get("yt") or {}).get("queue") or []):
            t = known.get(_d._norm(q))
            items.append({"title": (t or {}).get("title") or q, "artist": (t or {}).get("artist") or "",
                          "art": (t or {}).get("art") or "", "query": q})
        return {"items": items, "editable": True, "source": "youtube"}
    if live.get("mode") == "spotify":
        return {"items": list(db.get("spotify_queue") or []), "editable": False, "source": "spotify"}
    return {"items": [], "editable": False, "source": ""}


def refresh_spotify_queue() -> None:
    """Read Spotify's queue once (network) and keep it for the card to paint."""
    from connectors import music
    prov, items = music.queue_list()
    if prov != "spotify" or items is None:
        return
    from connectors.music import catalog
    db = _d._load_db()
    db["spotify_queue"] = [catalog.track_dict(t, "spotify") for t in items[:30]]
    _d._persist(db)


def _index(p: dict, items: list) -> "int | None":
    """`item` as a 1-based number or as words of a queued song; None when it names nothing."""
    return _d._resolve_track_index([{"title": i.get("title"), "artist": i.get("artist"), "query": i.get("query")}
                                    for i in items], p.get("item"))


def _queue_edit(op: str, p: dict) -> dict:
    from connectors import music
    db = _d._load_db()
    q = queue_view(_d._live_fields(db), db)
    if op != "clear":
        if not q["items"]:
            return {"ok": False, "error": "queue_empty", "message": "The queue is empty: nothing plays after this song."}
        idx = _index(p, q["items"])
        if idx is None:
            names = ", ".join(i["title"] for i in q["items"][:5])
            return {"ok": False, "error": "track_not_found", "item": p.get("item"),
                    "message": f"That song is not in the queue. Next up: {names}."}
    else:
        idx = -1
    to = -1
    if op == "move":
        to = _d._resolve_track_index(q["items"], p.get("to"))
        if to is None:
            try:
                to = max(0, int(p.get("to")) - 1)
            except (TypeError, ValueError):
                to = 0                                  # «move it up» with no place = play it next
    r = music.queue_edit(op, idx, to)
    out = _result(r)
    if not out["ok"] and out["reason"] == "unsupported":
        out["message"] = "This player's queue can be seen but not edited from here."
    _d._save_view()
    return out


def a_queue_remove(action: str, p: dict) -> dict:
    return _queue_edit("remove", p)


def a_queue_move(action: str, p: dict) -> dict:
    return _queue_edit("move", p)


def a_queue_clear(action: str, p: dict) -> dict:
    return _queue_edit("clear", p)


# ── what the card saw playing ────────────────────────────────────────────────────────────────────────────
def a_played(action: str, p: dict) -> dict:
    """INTERNAL: the card reports a song it shows playing. A song started by VOICE never crossed the card's own
    play path, so Recent and Most played never heard of it; the card is where it is visibly playing, so the card
    says so — once: the same song already at the head of Recent is not counted twice (a re-render, a reload)."""
    tr = _d._track_from_payload({"title": p.get("title"), "artist": p.get("artist"),
                                 "query": p.get("query") or p.get("title")})
    if not tr:
        return {"ok": False, "error": "missing_title"}
    tr["art"] = str(p.get("art") or "")
    db = _d._load_db()
    head = (db.get("recent") or [{}])[0] if db.get("recent") else {}
    if head.get("_k") == _d._norm((tr.get("title") or "") + "|" + (tr.get("artist") or "")):
        return {"ok": True, "counted": False}
    _d._push_recent(db, tr)
    _d._persist(db)
    _log.debug(f"musica: recorded a play the card saw: {tr.get('title')!r}")
    return {"ok": True, "counted": True}
