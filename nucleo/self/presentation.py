"""The agent's first-run PRESENTATION — said once per install, in his language, then never again (V2-929).

Who it is, how it listens, that its name is his to change, that it answers to one operator, and his name asked: the
words are LANGUAGE DATA (`i18n/genesis/<lang>/voice.json › introduction.presentation`, `{name}` = its current name).
Said for good when a reply that carried it NAMED the agent — which is what saying it means; the flag lives on the agent
side (`config/settings.AGENT_KEYS`), so a reset that starts the relationship over says it again. The presentation carries
the name-and-voice offer, so it settles that flag too. Both turn paths read it here: the old one through its
introduction pack, the conversation manager as a block of its state while it is owed (`pending`).
"""
from __future__ import annotations

from loguru import logger

FLAG = "intro_presentation_said"
#: that he was told, once, that the agent's name and voice are his to change (A7) — the presentation tells it
OFFER_FLAG = "intro_offer_told"
#: the relationship's introduction is over: nothing of it is owed any more
DONE_FLAG = "intro_done"


def said() -> bool:
    try:
        from config import settings
        return bool(settings.get(FLAG))
    except Exception as e:  # noqa: BLE001 — unreadable: never repeat it on a guess
        logger.debug(f"presentation: {FLAG} unreadable ({e!r})")
        return True


def text(name: str) -> str:
    """The presentation in the active language with `name` in it ('' when no pack carries one)."""
    from i18n import langs as _lg
    tpl = str(_lg.words("introduction.presentation", default="") or "")
    return tpl.replace("{name}", name) if tpl else ""


def pending(name: str) -> str:
    """The presentation still owed on this install, or '': not said, the introduction not over, and his language
    chosen (before the language ceremony nobody has spoken yet)."""
    try:
        from config import settings
        if said() or settings.get(DONE_FLAG) or not str(settings.get("stt_language") or "").strip():
            return ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"presentation: settings unreadable ({e!r})")
        return ""
    return text(name)


def settle(reply: str, name: str) -> bool:
    """A reply that carried the presentation: said for good when it names the agent. True when it settled now."""
    from nucleo.turn import identity as _identity
    if not str(reply or "").strip() or not _identity.sentences_with(name, reply):
        return False                    # it did not present itself: the presentation rides the next turn
    try:
        from config import settings
        settings.update({FLAG: True, OFFER_FLAG: True})
        logger.info("presentation: the first-run presentation has been said")
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"presentation: could not persist {FLAG}: {e!r}")
        return False
