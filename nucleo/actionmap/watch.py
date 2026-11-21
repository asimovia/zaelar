"""nucleo/actionmap/watch.py — is the map any good? (V2-539)

The map logs its HITS at the moment they execute. What it could not show is the other half of the
question — **what it is missing**: phrases the operator says often that the model resolves with a single
canvas action, i.e. exactly the turns that should have been a table lookup and instead cost a full model
turn. Without that signal, "are we mapping well?" can only be answered by reading transcripts by hand.

The conversation manager's runs reach `candidate` from the host (`conversation_host/shortcut.listen`), which knows
its own declared canvas acts: a run whose only effect was one of them is a candidate.

It OBSERVES and nothing else: no rows are written, no entry is promoted. Growing the table from what is
seen here is Phase 2 (`actionmap_define` + shadow mode); this module exists so that phase starts from
measured evidence instead of intuition.
"""
from __future__ import annotations


def candidate(user: str, action: str, origin: str) -> bool:
    """One phrase the model resolved with a single canvas act — the turn a table entry would have served — logged as a
    map CANDIDATE (`origin`: `conversation`, a run of the conversation manager whose only effect was one declared canvas
    act). Writes no row. True when logged."""
    from . import enabled, match
    user = str(user or "").strip()
    if not user or not action or not enabled():
        return False
    # Already in the table but it did not fire → the entry exists yet something upstream took the turn (a pending
    # fragment chain, an unresolvable target). That is a DIFFERENT problem from a missing entry, and conflating the two
    # is how a table looks healthy while never being used.
    known = match(user) is not None
    from voice.observer import emit
    emit("actionmap", "🕵️ map candidate: the model resolved a single action", text=user[:160], role="system",
         extra={"cat": "flash", "action": action, "origin": origin, "known_entry": known, "phrase": user[:160]})
    return True
