"""Composing a message is declared once, and read by type — never by a widget's or an action's name (C2 A1, pins 1-2).

A message being written in its card is a LOCAL event type the send owner owns (`messaging.draft_write`,
`messaging.draft_discard`, `nucleo/events/vocabulary.py`): it never leaves, asks nothing, and no reader of what leaves
or arrives sees it. A manifest action says which type it is (`"event"`), and the engine reads it by type
(`widgets.effects.event_of` / `acts_of`, `nucleo.send.turn.composes`). Every `event` a manifest declares names a type
the vocabulary knows; and the code that reads the composition names no widget and no action.
"""
from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from nucleo.events import vocabulary as voc
from nucleo.send import turn
from widgets import effects

ENGINE = Path(__file__).resolve().parents[4]
WRITE, DISCARD = "messaging.draft_write", "messaging.draft_discard"


def _manifests() -> dict[str, dict]:
    out = {}
    for p in sorted((ENGINE / "widgets").glob("*/manifest.json")):
        try:
            out[p.parent.name] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return out


def test_every_declared_event_is_a_type_and_composing_is_local_and_owned_by_the_send_owner():
    declared = [(w, a, s["event"]) for w, m in _manifests().items() for a, s in (m.get("actions") or {}).items()
                if isinstance(s, dict) and s.get("event")]
    assert declared, "no manifest declares a composition"
    assert [d for d in declared if not voc.declared(d[2])] == [], "an event no vocabulary type names"
    for name in (WRITE, DISCARD):
        t = voc.of(name)
        assert t is not None and t.direction == voc.LOCAL and voc.owner_of(name) == "send"
        assert name not in voc.names(voc.OUT) and name not in voc.names(voc.IN) and name not in dict(voc.topics())
    from rules import vocabulary as rules_voc
    assert not {WRITE, DISCARD} & set(rules_voc.classes()), "a rule may never be scoped to a draft on his screen"
    for w, a, _e in declared:
        assert turn.composes(w, a), (w, a)


def test_the_acts_of_a_type_are_read_from_the_manifest_its_own_first(monkeypatch):
    m = {"actions": {"w_b": {"event": WRITE, "internal": True}, "w_a": {"event": WRITE}, "w_c": {"event": DISCARD},
                     "w_send": {"consent_class": "messaging.send_new"}}}
    monkeypatch.setattr(effects, "_manifest", lambda wid: m)
    assert effects.acts_of("w_card", WRITE) == ["w_a", "w_b"] and effects.acts_of("w_card", DISCARD) == ["w_c"]
    assert effects.event_of("w_card", "w_send") == "messaging.send_new" and not turn.composes("w_card", "w_send")
    assert turn.composes("w_card", "w_a") and turn.composes("w_card", "w_c")


def test_disarm_a_misspelt_event_or_a_type_without_its_owner_is_named(monkeypatch):
    m = {"actions": {"w_a": {"event": "messaging.draft_wirte"}}}
    monkeypatch.setattr(effects, "_manifest", lambda wid: m)
    assert not voc.declared("messaging.draft_wirte") and not turn.composes("w_card", "w_a")
    m["actions"]["w_a"]["event"] = WRITE
    monkeypatch.setitem(voc._BY_NAME, WRITE, voc.of(WRITE)._replace(owner=""))
    assert not turn.composes("w_card", "w_a"), "a composition without its owner is nobody's"


def _names() -> set[str]:
    """Every widget id and every action name any manifest declares."""
    return {n for w, m in _manifests().items() for n in [w, *((m.get("actions") or {}).keys())] if len(n) > 3}


def _strings(src: str) -> set[str]:
    return {n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def test_the_code_that_reads_a_composition_names_no_widget_and_no_action():
    sources = {"turn.composes": inspect.getsource(turn.composes), "effects.event_of": inspect.getsource(effects.event_of),
               "effects.acts_of": inspect.getsource(effects.acts_of)}
    import textwrap
    hit = {k: sorted(_strings(textwrap.dedent(v)) & _names()) for k, v in sources.items()}
    assert not any(hit.values()), hit
    assert "mensajeria" in _names(), "the sweep reads the real manifests"
