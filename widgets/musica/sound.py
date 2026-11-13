"""The page player's SOUND: what was ordered, and what the browser actually let through (V2-812, V2-884 step 2).

Music that plays in the page (the hidden YouTube audio) starts muted, because muted autoplay is the only autoplay
every browser allows, and is unmuted a moment later. A phone browser may refuse that unmute — or refuse to start at
all — until a real tap on the page. The store said «playing», the card drew the song, the agent said «suena», and
the phone was silent.

So the card's players REPORT what they really do through the card's one state door (`ctx.state`, `widgets/state.py`;
the protocol shared with the video card, `/frontend/app/lib/player-report.js`), never into this store: whether the page
player plays, which song, its sound and volume. Sound wanted (a song loaded, not paused, not muted by him, not refused)
and the player reported silent or not playing is the fact `audio_blocked`, derived on every read (`facts` below): the
card's «tap for sound» row follows it, the brain's state line says it, and the declared tell reaches him only when it
contradicts an agent order and outlives `late_report.SETTLE_S`. Same class as the video card (`widgets/youtube/sound.py`).
"""
from __future__ import annotations

from . import data as _d


def facts(order: dict, report: dict) -> dict:
    """The derived facts the manifest declares, from what was ORDERED and what the page player REPORTS (V2-884 C1). A
    refused song is not a blocked browser (`refused`), and a field not yet confirmed is absent — never a value."""
    wanted = bool(order.get("video")) and not order.get("paused") and not order.get("muted") and not order.get("refused")
    return {"audio_blocked": wanted and (report.get("muted") is True or report.get("playing") is False)}


#: The IFrame API's fatal codes (101/150 the owner refuses embedding, 100 removed, 2/5 broken) — the video card's set.
from widgets.youtube import availability as _avail  # noqa: E402


def player_error(action: str, p: dict) -> dict:
    """Internal, fired by widget.js from the page player's own `onError` (V2-873). A song the player REFUSED is a fact:
    it is never offered again, and a song WE picked for his words is replaced by the next one the same words find;
    his own pick, or no other, leaves `player_error` set — nothing sounds, and the card and the brain say so. Measured
    on a demo pass: «pon algo de rosalía» → «(Official Audio)», refused with 150, and «Now playing» was said over it."""
    db = _d._load_db()
    yt = dict(db.get("yt") or {})
    vid, code = str(p.get("videoId") or "").strip(), str(p.get("code") or "").strip()
    fatal = code in _avail.FATAL_CODES
    if fatal and vid:
        yt["refused"] = ([v for v in (yt.get("refused") or []) if v != vid] + [vid])[-30:]
    if not yt.get("videoId") or (vid and vid != str(yt.get("videoId"))):
        db["yt"] = yt
        _d._persist(db)
        return {"ok": True, "stale": True}
    nxt = ("", "")
    walk = _avail.walk_step(yt, vid, str(yt.get("title") or yt.get("query") or "")) if fatal else {}
    if fatal and str(yt.get("query") or "").strip() and walk["n"] < _avail.WALK_MAX:   # bounded per order
        from connectors.music import youtube_audio as _ya
        from connectors.music import youtube_resolve as _yr
        nxt = _yr.resolve(str(yt["query"]), skip=_ya.refused_ids(yt))[:2]
    out, _ = {"ok": True}, yt.pop("refused_at", None)
    if nxt[0]:
        yt.update({"videoId": nxt[0], "title": nxt[1] or yt.get("query"), "player_error": "",
                   "paused": False, "last_cmd": "load", "cmd_seq": int(yt.get("cmd_seq") or 0) + 1})
        yt.pop("seek", None)
        walk["at"] = nxt[0]
    else:
        yt["player_error"] = code
        if fatal:   # the declared fallback as DATA (the site); the tell is said only against an agent order
            from i18n import langs as _langs
            yt["refused_at"] = f"https://www.youtube.com/watch?v={vid}"
            out["tell"] = _langs.words("music.youtube.refused", default="").format(title=walk["from"][:100])
    db["yt"] = yt
    _d._persist(db)
    return {**out, "player_error": yt["player_error"], "swapped_to": nxt[0]}


def digest_line(live: dict) -> str:
    """A song the page player REFUSED is the server's fact (its `player_error`): nothing is heard. Whether the browser
    keeps it silent is the app's state line (`facts: audio_blocked`), never a stored flag."""
    yt = live.get("yt") or {}
    if live.get("mode") == "youtube" and yt.get("player_error"):
        site = f" It plays on the site itself: {yt['refused_at']} — offer that." if yt.get("refused_at") else ""
        return (f"SOUND: the page player REFUSED this song (YouTube error {yt['player_error']}) — nothing is heard. "
                f"Do not say it is playing.{site}")
    return ""
