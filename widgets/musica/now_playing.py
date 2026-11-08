# musica — the LIVE reading: the Spotify connection, what is playing now (with a short-lived cache for the digest's
# per-turn read), and the live fields the card composes over the stored db (`data.py` re-exports every name).
import logging
import time

from . import local_audio as _local   # V2-638: a track that is a FILE in the agent's own library

_log = logging.getLogger("zaelar.widgets.musica")


def _spotify_status() -> dict:
    try:
        from connectors.spotify import auth
        return auth.status()
    except Exception as _e:
        _log.debug("_spotify_status: degraded, carrying on without it: %s", _e)
        return {}


#: The last Spotify reading and when it was taken (V2-812): the brain's digest rides every turn while the card is
#: open, and a network read per turn is a price; a reading this fresh is the same fact.
_NP_FRESH_S = 5.0
_np_last: dict = {"at": 0.0, "np": None, "src": None}


def _now_playing() -> "dict | None":
    """What is playing NOW on the provider making the sound. Fail-open: never breaks the card."""
    np = _read_now_playing()
    _np_last.update(at=time.time(), np=np)
    return np


def _fresh_now_playing(db: dict, fresh_s: float) -> "dict | None":
    """A reading at most `fresh_s` old, of the SAME start: a new start (another provider, another device) is never
    answered with the reading of the old one."""
    src = db.get("source")
    if fresh_s and time.time() - _np_last["at"] < fresh_s and _np_last.get("src") == src:
        return _np_last["np"]
    np = _d._now_playing()
    _np_last["src"] = src
    return np


def _read_now_playing() -> "dict | None":
    try:
        from connectors import music
        np = music.now_playing()
        if not np:
            return None
        t = np.track
        # Where the song IS, for a remote device's progress bar: `progress_ms` is taken at THIS read (the card
        # advances it); either at 0 means «not reported» and no bar is drawn (V2-717).
        return {"playing": bool(np.playing), "device": np.device or "", "device_id": getattr(np, "device_id", "") or "",
                "volume": np.volume, "provider": np.provider,
                "title": (t.title if t else ""), "artist": (t.artist if t else ""),
                "album": (t.album if t else ""), "art": (t.art if t else ""),
                "progress_ms": int(getattr(np, "progress_ms", 0) or 0),
                "duration_ms": int(t.duration_ms if t else 0),
                "shuffle": bool(getattr(np, "shuffle", False)), "repeat": str(getattr(np, "repeat", "off") or "off")}
    except Exception as _e:
        _log.debug("_read_now_playing: degraded, carrying on without it: %s", _e)
        return None


def _live_fields(db: dict, fresh_s: float = 0.0) -> dict:
    """Live state recomputed on each read: Spotify connection + card display mode + now_playing. `fresh_s` > 0 lets
    a reading that young stand in for a new one (the digest's per-turn read, V2-812)."""
    st = _spotify_status()
    connected = bool(st.get("logged_in"))
    yt = dict(db.get("yt") or {})
    # mode = what the bar shows: spotify (remote device), youtube (hidden audio), or idle.
    loc = _local.display(db)
    # A library file wins over the connector modes: it plays IN the page, and `local_audio.play` clears the yt
    # block (V2-638). The bar shows the player that MAKES the sound: a page-player song beats a Spotify reading
    # of a device elsewhere (V2-812).
    in_page = (db.get("source") or {}).get("provider") == "youtube" and yt.get("videoId")
    mode = "local" if loc else ("youtube" if in_page else ("spotify" if connected else
                                                           ("youtube" if yt.get("videoId") else "idle")))
    now = (None if mode != "spotify" else _fresh_now_playing(db, fresh_s) if fresh_s else _d._now_playing())
    away = _elsewhere(db, now) if mode == "spotify" else {}
    if away and not _ours_taken(db):
        # The account plays on somebody else's device and it was never our session: the card is OUR player, so it
        # stays blank — what another person listens to is not ours to show (operator, 2026-11-08).
        mode, now, away = ("youtube" if yt.get("videoId") else "idle"), None, {}
    return {
        **_d._SEED,
        "connected": connected,
        "can_connect": bool(st.get("can_connect")),
        "own_client_id_set": bool(st.get("own_client_id_set")),
        "default_available": bool(st.get("default_available")),
        "redirect_uri": st.get("redirect_uri", ""),
        "now_playing": now,
        "elsewhere": away,                                   # set = our session was taken: controls locked
        "here": _here(mode, loc, yt, now, away),
        "yt": _d._yt_display(yt),
        "local": loc,
        "mode": mode,
        "empty": mode == "idle",                             # V2-776 L2 — nothing playing, nothing to attest
    }


def _here(mode: str, loc: dict, yt: dict, now: "dict | None", away: dict) -> dict:
    """What OUR player is sounding right now — {title, source} — and {} when nothing sounds here. The end state of
    every start declares its title CHANGED (manifest `done_when`), so a start is met only when the asked music sounds
    on our side: another device of the account changing songs never satisfies it (live 2026-11-08: `now_playing`
    changed on a household speaker and the harness called a request met while nothing played here)."""
    # Nothing sounding is a VALUE ("" title), never a missing key: a missing key reads as «unverifiable», and a failed
    # start must read unmet. A page player the browser keeps silent (`audio_blocked`) is not sounding.
    if mode == "local" and loc.get("src") and not loc.get("paused"):
        return {"title": loc.get("title") or loc.get("src", ""), "source": "local"}
    if mode == "youtube" and yt.get("videoId") and not yt.get("paused") and not yt.get("audio_blocked"):
        return {"title": yt.get("title") or yt.get("videoId", ""), "source": "youtube"}
    if mode == "spotify" and now and now.get("playing") and not away:
        return {"title": now.get("title") or "", "source": "spotify"}
    return {"title": "", "source": ""}


def _ours_taken(db: dict) -> bool:
    """Was this OUR session, now taken elsewhere — our last start went to this provider and he has not let it go
    (`placement.release`), or he asked for something that waits for him to take control (`placement.held`)?"""
    src = db.get("source") or {}
    if src.get("provider") == "spotify" and src.get("live", True):
        return True
    try:
        from connectors.music import placement
        return bool(placement.held())
    except Exception as _e:
        _log.debug("_ours_taken: degraded, carrying on without it: %s", _e)
        return False


def _elsewhere(db: dict, now: "dict | None") -> dict:
    """{provider, device} when the account's playback sits on somebody else's device (playing or paused there) —
    the card locks its controls and offers to take control (operator, 2026-11-08). Only asked when what plays is not
    where our last start went, so the usual read (our own device) costs nothing more."""
    if not (now and now.get("device_id")):
        return {}
    src = db.get("source") or {}
    if src.get("provider") == now.get("provider") and src.get("device_id") == now.get("device_id"):
        return {}
    try:
        from connectors import music
        return music.elsewhere(playing_only=False)
    except Exception as _e:
        _log.debug("_elsewhere: degraded, carrying on without it: %s", _e)
        return {}


def _current_track_from_live(live: dict) -> "dict | None":
    """Currently playing song (Spotify or YouTube-audio), so it can be saved into a favorites list. Takes the
    already-composed LIVE state so `_compose` need not pay for `_spotify_status()` twice."""
    np = live.get("now_playing")
    if np and np.get("title"):
        return {"title": np.get("title") or "", "artist": np.get("artist") or "",
                "album": np.get("album") or "", "art": np.get("art") or "", "query": np.get("title") or ""}
    yt = live.get("yt") or {}          # already DISPLAY-shaped (V2-629): clean title, split artist, free art
    if yt.get("videoId"):
        return {"title": yt.get("title") or "Música", "artist": yt.get("artist") or "", "album": "",
                "art": yt.get("art") or "", "query": yt.get("title") or "", "videoId": yt.get("videoId")}
    return None


from . import data as _d  # noqa: E402 — read back at call time: data owns the store and re-exports these
