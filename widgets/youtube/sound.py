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


def player_adopt(action, p, db) -> dict:
    """Internal, run by the state door when his HAND moved the player's own control after the player had confirmed the
    order (V2-884 C10 A1, `widgets/state_adopt.py`): the card follows, as his button would have — a mute by hand is
    HIS mute (kept for the next video), a sound by hand ends it; a volume by hand is his volume. Never an autoplay
    start, never a report that acked less than the current order: those never reach here."""
    order, value = str(p.get("order") or ""), p.get("value")
    if order == "muted" and isinstance(value, bool):
        db["muted"] = value
        kept_mute(db, value)
    elif order == "volume" and isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100:
        db["volume"] = value
    else:
        return {"ok": False, "error": "not an adoptable field"}
    store.save(WID, db)
    return {"ok": True, "adopted": order}


def facts(order: dict, report: dict) -> dict:
    """The derived facts the manifest declares, from what was ORDERED and what the surface REPORTS (V2-884 C1)."""
    playing, muted = report.get("playing") is True, report.get("muted")
    return {"audio_blocked": playing and muted is True and order.get("muted") is False,
            "sound_on": playing and muted is False}
