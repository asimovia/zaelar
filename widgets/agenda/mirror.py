"""widgets/agenda/mirror.py — the Google mirror of a write, as the operator hears it: which calendar he named, and
what the answer offers when a connected calendar did not take the write (split from `gcal.py`, which does the
round trip and fills the status this module reads)."""
from __future__ import annotations


def calendar_named(db: dict, name) -> str:
    """The id of the Google calendar he NAMED («put it in Work»), or "" when it names none we know. Matched by id,
    then by its name folded; a name that matches nothing is not a refusal — the write goes to the default calendar
    and the answer says the name was not found (a destination is a preference, never a gate)."""
    want = str(name or "").strip()
    if not want:
        return ""
    from .details import _strip_accents
    cals = [c for c in ((db.get("google") or {}).get("calendars") or []) if isinstance(c, dict) and c.get("id")]
    hit = next((c for c in cals if str(c["id"]) == want), None)
    if hit is None:
        f = _strip_accents(want.lower())
        hit = next((c for c in cals if _strip_accents(str(c.get("summary") or "").lower()) == f), None) or \
            next((c for c in cals if f in _strip_accents(str(c.get("summary") or "").lower())), None)
    return str(hit["id"]) if hit else ""


def mirror_offer(status: dict | None) -> dict:
    """What the reply says when a CONNECTED calendar did not take the write: the extra keys of the action's answer
    (`mirror` + a spoken `message` that offers to reconnect), or {} when there is nothing to offer — mirrored, or no
    calendar connected at all (an operator who never linked Google is not asked to, at every appointment).
    The line is the `voice` pack's `agenda.mirror_failed`, in the active language."""
    st = status if isinstance(status, dict) else {}
    if st.get("mirrored") or not str(st.get("reason") or "") or st.get("reason") == "not_connected":
        return {}
    try:
        from i18n import langs as _langs
        line = _langs.words("agenda.mirror_failed", default="") or ""
    except Exception:  # noqa: BLE001
        line = ""
    return {"mirror": {"mirrored": False, "reason": str(st.get("reason") or ""), "offer": "reconnect_calendar"},
            "message": str(line)}
