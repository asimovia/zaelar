"""nucleo/request/send_task_fields.py — what a retained leaving act LACKS, read by what the action declares (V2-919 M2).

Split from `nucleo/request/send_task` (nucleo files stay small): `required` says whether a declared slot must carry a
value before the act runs, and `_missing_line` is the question for one that lacks: a send's own line for its person or
words, else ONE generic line naming the field by its declared label. The hand-off requires only what the EXIT DOOR
must judge — whom the act reaches, and a text it must carry — and a text the action declares optional
(`payload_fill.declared_optional`) is not one; anything else that lacks is the widget's to know and to refuse.
"""
from __future__ import annotations

from nucleo.request import base, note

#: The source rules the exit door judges: the person a leaving act reaches (always required — a held draft's «to whom»
#: stays asked, so a draft never leaves on a row with nobody named) and the text it carries (required unless the
#: action declares that field optional, V2-919 M2). `reading`, `card` and `held` slots are the widget's to answer.
PERSON_RULE, TEXT_RULE = "his_words", "composed"


def required(art: dict, slot: str) -> bool:
    """Must this slot of the retained act carry a value before it runs? The person always; a composed text unless the
    action's payload declaration marks its field optional (`payload_fill.declared_optional`); nothing else."""
    d = (art.get("slots") or {}).get(slot) or {}
    rule = str(d.get("rule") or "")
    if rule == PERSON_RULE:
        return True
    if rule != TEXT_RULE:
        return False
    from nucleo.flash import payload_fill
    pl = payload_fill._payload_spec(base(str(art.get("widget") or "")), str(art.get("action") or ""))
    return not payload_fill.declared_optional(pl.get(str(d.get("key") or slot)))


def _missing_line(art: dict, slot: str) -> str:
    """The question for a slot with no value: a send's own line (`send_missing_<slot>`, the person named) for a field
    of one value, else ONE generic line naming the field by its declared label (`send_missing_field`, V2-919 M2) — a
    field declared another kind (a list of people) is never asked as «who do I send it to?»."""
    who = ""
    try:
        from nucleo import on_his_behalf as _ob
        who = ", ".join(_ob.who_of(str(art.get("widget") or ""), str(art.get("action") or ""), art.get("payload")))
    except Exception as e:  # noqa: BLE001
        note(e)
    key = str(((art.get("slots") or {}).get(slot) or {}).get("key") or slot)
    try:
        from i18n import langs
        from nucleo.flash import payload_fill
        from widgets import field_types
        lang = langs.current_language()
        wid, act = base(str(art.get("widget") or "")), str(art.get("action") or "")
        text_kind = not field_types.declared(wid, act).get(key)     # the send's line is for a field of ONE value
        if text_kind and (tpl := str(getattr(lang, f"send_missing_{slot}", "") or "")):
            return tpl.format(who=who or "?")          # a send's person or words: the send's own line, as before
        label = str(payload_fill._payload_spec(wid, act).get(key) or key)
        if tpl := str(getattr(lang, "send_missing_field", "") or ""):
            return tpl.format(field=" ".join(label.split()), who=who or "?")   # any other field, by its declared label
    except Exception as e:  # noqa: BLE001
        note(e)
    return f"{slot}? ({who})"
