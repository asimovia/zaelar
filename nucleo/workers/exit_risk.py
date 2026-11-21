"""nucleo/workers/exit_risk.py — what the exit door ASKS: the risk an act declares, and the act's own question (V2-931).

Measured on his engine (2026-11-18): «create a WhatsApp group with her called X» crossed the message door, which asked
every act that leaves the same way — three times, each as «the message for her is written — shall I send it?». Asking
is read here off what the act's EVENT TYPE declares (`nucleo/events/vocabulary`), never off its name: a type declared
harmless runs on his order; a message, and any act of no declared type, asks once — with the act's OWN question.
"""
from __future__ import annotations

from loguru import logger


def klass(wid: str, act: str, inner: dict | None) -> str:
    """The act's declared EVENT TYPE with its channel (`messaging.create_group@whatsapp`): the manifest's class, refined
    by the card's own `consent_scope` for this call. "" when the act declares none."""
    try:
        from nucleo.acts import frontend as _fe
        from widgets import runtime
        sp = ((runtime.get(wid) or {}).get("actions") or {}).get(act)
        return str(_fe._policy_key(wid, act, sp if isinstance(sp, dict) else {}, dict(inner or {})) or "")
    except Exception as e:  # noqa: BLE001 — unread: no class, and an act of no class asks
        logger.debug(f"exit_gate: the class of {wid}:{act} unread ({e!r})")
        return ""


def family(wid: str, act: str, inner: dict | None = None) -> str:
    """The lines he hears for this act (`nucleo/wording.LINES`): "send" for a message, "act" for anything else. Read
    off the type its MANIFEST declares — a group born with a first message asks like a send and is still told as a
    group — else off what its card says this call is."""
    from nucleo.events import vocabulary as _evoc
    declared = ""
    try:
        from widgets import effects
        sp = (effects._manifest(wid).get("actions") or {}).get(act)
        declared = str((sp or {}).get("consent_class") or "") if isinstance(sp, dict) else ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"exit_risk: the manifest of {wid}:{act} unread ({e!r})")
    return _evoc.says(declared or klass(wid, act, inner))


def asks_by_itself(wid: str, act: str, inner: dict | None) -> bool:
    """Does this leaving act ask him before it runs, by the RISK its event type declares
    (`nucleo/events/vocabulary.asks_by_itself`)? A type declared harmless — reversible, carrying nothing he did not
    say: a group created with people he named — runs on his order; anything else, and any act of no declared type,
    asks once. His standing rule «ask» for that type still asks."""
    from nucleo.events import vocabulary as _evoc
    cls = klass(wid, act, inner)
    if not cls or _evoc.asks_by_itself(cls):
        return True
    try:
        from nucleo import consent
        return consent.class_policy(cls) == "ask"
    except Exception as e:  # noqa: BLE001 — his rules unread: the declared type stands
        logger.debug(f"exit_gate: his rule for {cls} unread ({e!r})")
        return False


def own_question(wid: str, act: str, inner: dict | None) -> str:
    """The act's OWN declared question (`confirm_q`, in his language) with what this call carries in its blanks, and
    the words it would send when it carries any. "" when the act declares none."""
    try:
        from nucleo.request import consent_ask
        tpl = consent_ask.question(wid, act, inner)
        if not tpl:
            return ""
        vals = {k: (", ".join(str(x.get("name") if isinstance(x, dict) else x) for x in v)
                    if isinstance(v, (list, tuple)) else str(v)) for k, v in (inner or {}).items()}
        vals.update(_card_values(wid, act, inner))
        q = tpl.format_map(type("_Blank", (dict,), {"__missing__": lambda self, k: ""})(vals)).strip()
        text = " ".join(str((inner or {}).get("text") or "").split())
        return f"{q} «{text[:160]}»" if q and text and text not in q else q
    except Exception as e:  # noqa: BLE001
        logger.debug(f"exit_gate: the act's own question unread ({e!r})")
        return ""


def _card_values(wid: str, act: str, inner: dict | None) -> dict:
    """The blanks the CARD fills for this call (its data module's `confirm_values(action, payload)`, when it declares
    one): what it found for the call's words, so he confirms the thing that will be acted on. {} otherwise."""
    try:
        import importlib
        card = str(wid or "").split("::", 1)[0].strip().lower()
        hook = getattr(importlib.import_module(f"widgets.{card}.data"), "confirm_values", None)
        got = hook(str(act or ""), dict(inner or {})) if callable(hook) else None
        return {str(k): str(v) for k, v in got.items() if str(v)} if isinstance(got, dict) else {}
    except Exception as e:  # noqa: BLE001 — unread: the call's own words fill the blanks
        logger.debug(f"exit_risk: the card's values for {wid}:{act} unread ({e!r})")
        return {}


def ready_question(wid: str, act: str, inner: dict, cls: str = "") -> str:
    """The door's ONE question, in his language. A message: «the message for <her> is ready — shall I send it?», naming
    his contact by the first word of the name he keeps her under (never a raw id); with several people, all of them.
    An act whose declared type is not a message asks its OWN declared question — never the message's sentence."""
    from nucleo import on_his_behalf as _ob
    if family(wid, act, inner) != "send" and (q := own_question(wid, act, inner)):
        return q
    who = _ob.shown_who(wid, act, inner) or ", ".join(_ob.who_of(wid, act, inner)) or ""
    try:
        from i18n import langs as _lg
        tpl = str(getattr(_lg.current_language(), "send_ready_confirm", "") or "")
        if tpl and who:
            return tpl.format(who=_short(who))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"exit_gate: the ready line unread ({e!r})")
    return _ob.question(wid, act, inner)


def _short(who: str) -> str:
    """One person's name as he says it aloud: its first word, when the name has several and is a name (no address, no
    number). Several people, or anything else, as they are."""
    w = " ".join(str(who or "").split())
    first = w.split(" ", 1)[0]
    plain = "," not in w and "@" not in w and not any(ch.isdigit() for ch in w)
    return first if plain and " " in w and len(first) > 2 else w
