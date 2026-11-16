"""nucleo/request/send_task_fields.py — what a retained leaving act LACKS, read by what the action declares (V2-919 M2).

Split from `nucleo/request/send_task` (nucleo files stay small): `required` says whether a declared slot must carry a
value before the act runs — the person always, any other slot unless its field is declared optional in the action's
payload (`payload_fill.declared_optional`), never the shape of a send — and `_missing_line` is the question for one
that lacks: a send's own line for its person or words, else ONE generic line naming the field by its declared label.
"""
from __future__ import annotations

from nucleo.request import base, note

#: The source rule whose slot is required whatever the payload says: the person a leaving act reaches. Every other slot
#: is required exactly when the action's payload declaration does not mark its field optional (V2-919 M2) — a held
#: draft's «to whom» stays asked as before, so a draft never leaves on a row with nobody named.
PERSON_RULE = "his_words"


def required(art: dict, slot: str) -> bool:
    """Must this slot of the retained act carry a value before it runs? The person always; any other declared slot
    unless the action's payload declaration marks its field optional (`payload_fill.declared_optional`)."""
    d = (art.get("slots") or {}).get(slot) or {}
    if str(d.get("rule") or "") == PERSON_RULE:
        return True
    from nucleo.flash import payload_fill
    pl = payload_fill._payload_spec(base(str(art.get("widget") or "")), str(art.get("action") or ""))
    key = str(d.get("key") or slot)
    return key in pl and not payload_fill.declared_optional(pl.get(key))


def _missing_line(art: dict, slot: str) -> str:
    """The question for a slot with no value: a send's own line (`send_missing_<slot>`, the person named), else ONE
    generic line naming the field by its declared label (`send_missing_field`, V2-919 M2)."""
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
        lang = langs.current_language()
        if tpl := str(getattr(lang, f"send_missing_{slot}", "") or ""):
            return tpl.format(who=who or "?")          # a send's person or words: the send's own line, as before
        label = str(payload_fill._payload_spec(base(str(art.get("widget") or "")), str(art.get("action") or ""))
                    .get(key) or key)
        if tpl := str(getattr(lang, "send_missing_field", "") or ""):
            return tpl.format(field=" ".join(label.split()), who=who or "?")   # any other field, by its declared label
    except Exception as e:  # noqa: BLE001
        note(e)
    return f"{slot}? ({who})"
