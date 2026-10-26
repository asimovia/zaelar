"""rules/prompt.py — what of the rules table reaches the MODEL, and only for the scopes in play (V2-806).

  · `gate` rows never enter as prose: code applies them. His own permission rows (`source=user`, key `consent`)
    get ONE compact line, so the model does not ask in words what the gate already decided.
  · `pref` rows whose key code reads (a style knob, a widget's enforceable value) reach the model only through the
    line their owner composes (`style_policy.prompt_line`, the card's own view).
  · `note` rows — his sentences no code applies — enter for the scopes in play: `global` and `voice` on the voice
    turn (this module), a widget's notes in that widget's row when it is on screen, named or recently used
    (`widgets/brief.py`), `global` and widget notes in a worker's dossier (`notes.for_surface("worker")`).

There is no always-on block of «the newest N rules»: the voice line carries what is in scope, newest first, inside
a budget no larger than the block it replaced.
"""
from __future__ import annotations

from . import cascade as _cascade
from . import notes as _notes

#: The voice line's budget in characters — the size of the block it replaced (eight rules × 90).
VOICE_BUDGET = 720
_NOTE_MAX = 200


def _fit(texts: list[str], budget: int) -> list[str]:
    """Newest first until the budget is spent, then back in the order they were said."""
    out, used = [], 0
    for t in reversed(texts):
        t = t[:_NOTE_MAX]
        if used + len(t) + 3 > budget and out:
            break
        out.append(t)
        used += len(t) + 3
    return list(reversed(out))


def scope_label(scope: str) -> str:
    """A scope as a person reads it: `messaging/email/send_new` → «messaging · email · send_new»."""
    s = str(scope or "").replace("widget:", "").replace("item:", "#").replace("/*/", " · ")
    return s.replace("/", " · ")


def gate_line() -> str:
    """One compact line with HIS permission rows («messaging · email · send_new = allow»), or ''."""
    import rules
    rows = [r for r in rules.all_rows(include_defaults=False)
            if r["kind"] == "gate" and r["key"] == "consent" and r["source"] == "user" and _cascade.live(r)]
    if not rows:
        return ""
    bits = [f"{scope_label(r['scope'])} = {r['value']}" for r in rows[-6:]]
    return ("PERMISOS QUE FIJÓ ÉL (allow = sin confirmación, ask = pregunta antes, never = nunca; los aplica el "
            "sistema, no los repitas en palabras): " + " · ".join(bits))


def voice_block() -> str:
    """The voice turn's rules: his in-scope notes and his permission line. '' when he has none."""
    texts = _fit(_notes.for_surface("voice"), VOICE_BUDGET)
    lines = []
    if texts:
        lines.append("REGLAS DEL OPERADOR (te las dio él; síguelas SIEMPRE): " + " · ".join(texts))
    g = gate_line()
    if g:
        lines.append(g)
    return ("\n\n" + "\n".join(lines)) if lines else ""
