"""nucleo/flash/committed_reply.py — does a reply promise, in the first person, to go and do something?

Moved out of `voice/engine/llm/providers/promise_backstop.py` (2026-10-26) so the promise harness in `nucleo/turn/`
can read the same rule without reaching into the voice motor's internals (the dependency-direction ratchet). The
backstop re-exports it; there is still ONE copy of the rule.
"""
from __future__ import annotations

import re as _re
import unicodedata as _ud

# First person committing to act. Deliberately narrower than `router_guards.promises_action` (which also
# serves the show/music backstops): this one gates real spending.
_COMMITTED_RE = _re.compile(
    r"\b(me pongo con|me pongo a|ahora mismo|lo hago|lo hago ya|te lo (?:reservo|busco|"
    r"miro|preparo|hago|gestiono)|arranco|voy (?:con|a por|alla|alli|ya)|me meto en|"
    r"enseguida|me encargo|lo pongo en marcha|voy alla|entro (?:en|a) la web)\b")


def _norm(s: str) -> str:
    n = _ud.normalize("NFKD", s or "")
    return "".join(c for c in n if not _ud.combining(c)).lower()


def committed(spoken_text: str) -> bool:
    """True if the reply promises, in the first person, to go and do something. A NEGATED clause does not
    («ahora mismo NO tengo ninguna tarea corriendo» — four of the gate's ten measured firings): the rule and
    its clause arithmetic live once, in `router_guards`, and both promise gates read them."""
    from nucleo.flash.router_guards import unnegated_match
    return unnegated_match(_COMMITTED_RE, _norm(spoken_text))
