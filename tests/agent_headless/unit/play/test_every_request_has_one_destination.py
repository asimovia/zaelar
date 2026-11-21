"""Every request has ONE destination — the conversation, the programme or a worker — and for every declared action it
is the one today's router gives (V2-909, `nucleo/play/route.py`, `nucleo/play/programme.py`).

Parametrized over every action every shipped widget declares: each has a programme read from its manifest; a leaving
one has an end state or says why it has none; one declared action goes to the programme unless its class declares the
worker; under a sure errand reading the action stays home exactly when `route_by_verdict.stays_home` says so.

Disarm: `destination` answers the programme for everything → red.
"""
from __future__ import annotations

import pathlib


from widgets import actions, effects, runtime

ROOT = pathlib.Path(__file__).resolve().parents[4]
ACTS = sorted((m["id"], a) for m in runtime.catalog() for a, s in (m.get("actions") or {}).items()
              if isinstance(s, dict))
IDS = [f"{w}:{a}" for w, a in ACTS]


def _spec(wid, action):
    return (runtime.get(wid).get("actions") or {})[action]


def test_the_catalogue_is_read():
    assert len(ACTS) > 100 and any(effects.leaves(w, a) for w, a in ACTS)


ACTS_OF = {w: a for w, a in ACTS if not effects.leaves(w, a)
           and actions.classify(_spec(w, a), a) != actions.ESCALATE}

