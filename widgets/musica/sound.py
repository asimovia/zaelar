"""The page player's SOUND: what was ordered, and what the browser actually let through (V2-812).

Music that plays in the page (the hidden YouTube audio) starts muted, because muted autoplay is the only autoplay
every browser allows, and is unmuted a moment later. A phone browser may refuse that unmute — or refuse to start at
all — until a real tap on the page. The store said «playing», the card drew the song, the agent said «suena», and
the phone was silent.

So the card REPORTS what its player really does (widget.js reads the IFrame API's own `infoDelivery`): `player_audio`
with `muted` = silent. Sound wanted (not paused, not muted by him) and the player silent is `audio_blocked`: the
card shows a «tap for sound» row, the brain's digest says it, and when an agent order is being contradicted the
card's `late_report` seam tells him. The first tap on the page gives it sound and the flag clears on the player's
next report. Same mechanism as the video card (`widgets/youtube/sound.py`), on this card's own `yt` block.
"""
from __future__ import annotations

from . import data as _d


def _flag(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def player_audio(action: str, p: dict) -> dict:
    """Internal, fired by widget.js. A report about another song than the current one is stale."""
    db = _d._load_db()
    yt = dict(db.get("yt") or {})
    vid = str(p.get("videoId") or "").strip()
    if not yt.get("videoId") or (vid and vid != str(yt.get("videoId"))):
        return {"ok": True, "stale": True}
    silent = _flag(p.get("muted"))
    wanted = not yt.get("paused") and not yt.get("muted")
    was = bool(yt.get("audio_blocked"))
    if silent and wanted:
        if was:
            return {"ok": True, "audio_blocked": True}
        yt["audio_blocked"] = True
        db["yt"] = yt
        _d._persist(db)
        from i18n import langs as _langs
        out = {"ok": True, "audio_blocked": True}
        tell = str(_langs.words("music.audio_blocked", default="") or "")
        if tell:
            out["tell"] = tell          # said only if an agent order is being contradicted (`widgets/late_report.py`)
        return out
    if not silent and was:
        yt["audio_blocked"] = False
        db["yt"] = yt
        _d._persist(db)
        return {"ok": True, "audio_blocked": False}
    return {"ok": True, "audio_blocked": was}


def digest_line(live: dict) -> str:
    """The brain must not say «it is playing» over a page player the browser keeps silent."""
    yt = live.get("yt") or {}
    if live.get("mode") == "youtube" and yt.get("audio_blocked") and not yt.get("paused") and not yt.get("muted"):
        return ("SOUND: BLOCKED by the browser of the screen the card is on — the song is loaded but nothing is heard. "
                "Do not say it is playing; tell him to tap the card once and it will sound.")
    return ""
