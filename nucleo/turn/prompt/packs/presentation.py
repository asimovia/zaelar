"""The first-run PRESENTATION — said once per install, in his language, then never again (V2-929).

The operator, 2026-11-17: the agent's first words on a new install say who it is («I'm Johnny»), that it answers
everything and listens all the time now but that word activation makes it answer only when called by name, that its
name is his to change, that it answers to one operator though others may talk with it, and asks his name.

The words are LANGUAGE DATA (`i18n/genesis/<lang>/voice.json › introduction.presentation`, `{name}` = the agent's
current name), written per language so each says it the way that language would; a language without the entry gets the
English one and the block tells the model to say it in his. The introduction phase carries it: on the kickoff it IS the
greeting, on any other first turn it rides the answer. The turn that carried it settles it — only if the reply NAMED the
agent, which is what saying it means — and the flag lives on the agent side (`config/settings.AGENT_KEYS`), so a reset
that starts the relationship over says it again. The presentation carries the name-and-voice offer, so it settles that
flag too.
"""
from __future__ import annotations

from nucleo.self.presentation import FLAG, said, text  # noqa: E402,F401 — one home for both turn paths

#: The TRACE of the turn whose block carried the presentation; that turn's close settles it.
_pending = ""


def line(name: str, first: bool, trace: str) -> str:
    """The block's line for this turn, or '' once said. Marks `trace` as the turn that carries it."""
    global _pending
    words = "" if said() else text(name)
    _pending = trace if words else ""
    if not words:
        return ""
    when = ("Tu saludo ES esta presentación" if first else
            "Atiende primero lo que te pide y, en ese mismo turno, preséntate con esto")
    return (f"PRESENTACIÓN — solo esta vez en toda la vida de esta instalación. {when}; dila CASI TAL CUAL, en su "
            f"idioma, sin añadir capacidades ni quitar ninguna parte: «{words}». Si por tu memoria ya sabes cómo se "
            f"llama, cambia solo la pregunta final por saludarle por su nombre.")


def settle(payload, name: str) -> bool:
    """The turn that carried it closed: said for good when its reply names the agent. True when it settled now."""
    global _pending
    if not _pending or (payload or {}).get("trace") != _pending:
        return False
    _pending = ""
    win = (payload or {}).get("window") if isinstance(payload, dict) else None
    last = ((win or [])[-1:] or [{}])[0] or {}
    reply = str(last.get("text") or "") if last.get("role") == "assistant" else ""
    from nucleo.self import presentation as _said_once
    return _said_once.settle(reply, name)
