"""The player's SOUND: what was ordered, and what the browser actually let through (V2-791).

Two facts used to be one field. `muted` is what the operator (or the agent, on his order) WANTS; the embedded
player starts muted for the autoplay policy, and whether it can be unmuted from a voice order depends on the page
— a cross-origin iframe with `allow="autoplay"` may take sound only once the page has had a real user gesture. The
store said `muted: false` the moment `unmute` ran, the card hid its «tap for sound» hint, and nothing ever checked
whether the player obeyed.

So the player now REPORTS what it really does — since V2-884 1a through the card's one state door (`ctx.state`,
`widgets/state.py`), never into this store. Sound wanted and the player reported silent is the fact `audio_blocked`
(`facts` below), derived on every read: the hint follows it, the brain's state line says it, and the declared tell
reaches him only when it contradicts an agent order and outlives `late_report.SETTLE_S` (the muted autoplay start
that sounds a second later is never said — measured 2026-10-30 and 2026-11-11).

A video that arrives on an order to watch it wants sound unless he muted the player himself (`mute_kept`): the
default silence was the autoplay policy's, never his.
"""
from __future__ import annotations

from .. import store

WID = "youtube"


def wants_sound(db: dict) -> None:
    """A video he asked to watch: sound, unless the last word on sound was HIS mute."""
    if not db.get("mute_kept"):
        db["muted"] = False


def kept_mute(db: dict, muted: bool) -> None:
    """An explicit mute is his choice and survives the next video; any order for sound ends it."""
    db["mute_kept"] = bool(muted)


def player_audio(action, p, db) -> dict:
    """Internal, fired by widget.js when the player's OWN control gave it sound: his hand is his order, so the card's
    `muted` follows the player (and his kept mute ends). Whether the player is silent is no longer stored here: it is
    the surface's report (`widgets/state.py`), and «blocked» is the fact `audio_blocked` derived from it (V2-884 1a).
    A report about another video than the current one is stale."""
    vid = str(p.get("videoId") or "").strip()
    if vid and vid != str(db.get("videoId") or ""):
        return {"ok": True, "stale": True}
    silent = str(p.get("muted")).strip().lower() in ("true", "1", "yes")
    if not silent and db.get("muted"):
        db["muted"] = False
        db["mute_kept"] = False
        store.save(WID, db)
    return {"ok": True}


def player_state(action, p, db) -> dict:
    """Internal, fired by widget.js from the embedded player's own `onStateChange` (V2-873): WHICH video the player
    plays (`playing_id`) and WHETHER it plays (`playing`). The end states of every start and of pause read these —
    `videoId`/`paused` are the ORDER, and a «Hecho» was said over a video the player never changed. A report about
    another video than the current one is stale."""
    vid = str(p.get("videoId") or "").strip()[:20]
    if vid and vid != str(db.get("videoId") or ""):
        return {"ok": True, "stale": True}
    playing = str(p.get("playing")).strip().lower() in ("true", "1", "yes")
    was = (str(db.get("playing_id") or ""), bool(db.get("playing")))
    if playing:   # a stream of ours (library, torrent) has no videoId: its source names it
        db["playing_id"] = vid or str(db.get("videoId") or db.get("src") or "")
    db["playing"] = playing
    if (str(db.get("playing_id") or ""), playing) != was:
        store.save(WID, db)
    return {"ok": True, "playing": playing, "playing_id": str(db.get("playing_id") or "")}


def facts(order: dict, report: dict) -> dict:
    """The derived facts the manifest declares, from what was ORDERED and what the surface REPORTS (V2-884 C1)."""
    playing, muted = report.get("playing") is True, report.get("muted")
    return {"audio_blocked": playing and muted is True and order.get("muted") is False,
            "sound_on": playing and muted is False}
