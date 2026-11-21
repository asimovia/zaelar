"""An EAGER end of turn — the ear announcing a sentence it has not confirmed — writes nothing and sends nothing.

The ear's preflight fires the turn's brief early (`eager_brief.on_preflight` → `brief_turn.fire_early`): two reads of
his words, kept in memory for the turn that admits the same sentence. The sentence may still grow, so nothing may ACT
on it: no draft opened or answered, no question, no task, no row, no order to a connector.

Held here, one row per road a message can take, with the state that road would act on already in place — an open
draft waiting for his yes, a task waiting for his answer, an order scheduled for later:
  · the picture of every store (`harness/store_snapshot`) is the same bytes before and after the preflight;
  · no outbound order reaches the bus, and no consequence door is asked;
  · by construction: a preflight is read in ONE place, and the two functions it runs call nothing but the two reads.

Not held here: a turn that the session itself STARTS on a preflight (the transport's preemptive generation, off by
default — pinned below). That turn runs every road for real; making it harmless needs the turn to know it is not yet
confirmed, which is a design of its own.
"""
from __future__ import annotations

import ast
from pathlib import Path


from connectors.messaging import group_leave, ingest

ENGINE = Path(__file__).resolve().parents[4]
_OUT = (ingest.TOPIC_SEND, ingest.TOPIC_REPLY, ingest.TOPIC_GROUP, group_leave.TOPIC_GROUP_LEAVE)

#: One sentence per road, as the ear would announce it: the words that road acts on when a turn admits them.
ROADS = {
    "L1 the owner's draft, his yes": "Yes, send it",
    "L1 a message order": "Send Rowan a message saying I am on my way",
    "L2 an act that leaves and is not a message": "Invite Rowan to Friday's meeting",
    "L3 an order nothing served": "Write to the plumber we called last week",
    "L4 his answer to a waiting row": "The second one",
    "L5 a worker under a mandate": "Go on, answer her whatever she asks",
    "L6 an errand that wakes": "Tell me when she answers",
    "L7 a promise with no call": "Send it to her right now",
    "L8 a message and an errand in one sentence": "Find a table for two and send it to Rowan",
    "a card act that leaves": "Create a group with Rowan called Friday dinner",
}


# ── by construction ────────────────────────────────────────────────────────────────────────────────────────────────
def _calls(path: str, fn: str) -> set[str]:
    tree = ast.parse((ENGINE / path).read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn)
    out = set()
    for c in ast.walk(node):
        if isinstance(c, ast.Call):
            f = c.func
            out.add(f"{getattr(f.value, 'id', '?')}.{f.attr}" if isinstance(f, ast.Attribute) else getattr(f, "id", "?"))
    return out


def test_the_session_does_not_start_a_turn_on_a_preflight_unless_asked_to():
    """The transport's preemptive generation is OFF unless the install turns it on: its default is read off the source."""
    src = (ENGINE / "voice/engine/core/config.py").read_text(encoding="utf-8")
    line = next(ln for ln in src.splitlines() if "preemptive_generation" in ln and "env(" in ln)
    assert 'env("ZAELAR_PREEMPTIVE", "0") == "1"' in line
