"""The prompt says each thing ONCE, from a pure function (node 13.11).

Snapshots in Spanish and English of the same state: every id appears once across the state and the input; OPEN holds
what is open in the ledger — the person's requests, a reserved effect — newest first under a budget, the rest counted;
what the host keeps (its tasks, what it owes) comes as its own blocks after OPEN, never copied into the ledger; our
lines in the conversation are cut to what was heard, and «heard: unknown» is said, never assumed; the prefix is
byte-identical between runs; composing twice gives the same prompt. The view is read from a real store snapshot, so
the test also proves the composer needs nothing else.
"""
from __future__ import annotations

import re

from conversation import envelopes as E
from conversation.composer import compose, view_from
from conversation.config import Config
from conversation.ports import Block
from conversation.types import Channel, Coverage, EnvelopeKind, ItemKind

PREFIX = "OPERATING RULES v1\nTOOLS: search, market_data, discover_tools, send_message"
T0 = 1_800_000_000_000


def _state(store, lang_turns):
    lease = store.acquire("acct", "test")
    with store.tx(lease) as tx:
        rows = [("r1", ItemKind.REQUEST, "open", "conversation", {"summary": "w0101 w0102"}, None, 10),
                ("r2", ItemKind.REQUEST, "answered", "conversation", {"summary": "w0111"}, None, 15),  # final
                ("x0", ItemKind.EFFECT, "claimed", "conversation", {"summary": "w0401"}, None, 30),
                ("x1", ItemKind.EFFECT, "provider_accepted", "conversation", {}, None, 40)]      # final: not shown
        for rid, kind, state, owner, data, waiting, upd in rows:
            tx.put("items", rid, {"id": rid, "kind": str(kind), "state": state, "owner": owner, "data": data,
                                  "waiting_on": waiting, "attached": [], "created_ms": upd, "updated_ms": upd})
        for i, (role, text, heard) in enumerate(lang_turns, start=1):     # the window: his entries and our lines
            if role == "user":
                env = E.make(EnvelopeKind.USER_UTTERANCE, E.UtteranceBody(f"iv{i}", text), producer="ear:d1",
                             producer_id=f"iv{i}:full", account="acct", onset_ms=i, sealed_ms=i)
                tx.put("inbox", f"e{i}", {"id": f"e{i}", "env": E.to_json(env), "kind": str(env.kind),
                                          "accepted": i, "state": "accounted", "outcome": "told"})
            else:
                tx.put("says", f"s{i}", {"say_id": f"s{i}", "text": text, "channels": ["voice"], "t_ms": i,
                                         "heard_chars": heard, "state": "ended"})
    return store.snapshot("acct")


def _batch(text_voice: str, text_typed: str):
    utt = E.make(EnvelopeKind.USER_UTTERANCE, E.UtteranceBody("iv7", text_voice), producer="ear:d1",
                 producer_id="iv7:1", account="acct", onset_ms=T0, sealed_ms=T0 + 900)
    txt = E.make(EnvelopeKind.USER_TEXT, E.TextBody("iv8", text_typed), producer="chat:d2", producer_id="c1",
                 account="acct", onset_ms=T0 + 300, sealed_ms=T0 + 300, channel=Channel.TEXT)
    inc = E.make(EnvelopeKind.USER_UTTERANCE, E.UtteranceBody("iv9", "w0601", coverage=Coverage.INCOMPLETE,
                                                               amends="iv7"),
                 producer="ear:d1", producer_id="iv9:incomplete", account="acct", onset_ms=T0 + 900, sealed_ms=T0 + 2000)
    return (utt, txt, inc)


ES_TURNS = [("user", "w0001 w0002", None), ("agent", "Te lo miro ahora mismo, dame un segundo.", 13),
            ("agent", "Hecho.", None)]
EN_TURNS = [("user", "w0001 w0002", None), ("agent", "Let me check that for you right now.", 9),
            ("agent", "Done.", None)]

EXPECTED_ES = """NOW Fri 2027-01-15 08:00 · screen: agenda · voice: d1 · lang: es

OPEN
[x0] effect · claimed · w0401
[r1] request · open · w0101 w0102

TASKS
[t5] running · w0201"""

HOST = (Block("TASKS", "[t5] running · w0201"),)          # the host's own rows, read by the host


def _compose(store, turns, lang, cfg=Config()):
    snap = _state(store, turns)
    view = view_from(snap, prefix=PREFIX, now_ms=T0, lang=lang, screen="agenda", voice_endpoint="d1", memory=HOST)
    return compose(view, _batch("w0701 w0702", "w0801"), cfg)


def test_the_spanish_snapshot(store):
    p = _compose(store, ES_TURNS, "es")
    assert p.state == EXPECTED_ES
    assert [t.text for t in p.conversation] == ["w0001 w0002", "Te lo miro ah", "Hecho. [heard: unknown]"]
    assert p.input == ("INPUT\n[iv7 · voice · closed] «w0701 w0702»\n[iv8 · text · closed] «w0801»\n"
                       "[iv9 · voice · incomplete · amends iv7] «w0601»")


def test_the_english_snapshot_has_the_same_shape(store):
    p = _compose(store, EN_TURNS, "en")
    assert p.state == EXPECTED_ES.replace("lang: es", "lang: en")
    assert [t.text for t in p.conversation] == ["w0001 w0002", "Let me ch", "Done. [heard: unknown]"]


def test_every_id_appears_once(store):
    p = _compose(store, ES_TURNS, "es")
    ids = re.findall(r"^\[([a-z0-9_]+)[\] ]", p.state + "\n" + p.input, flags=re.M)
    assert len(ids) == len(set(ids)) and {"x0", "r1", "t5", "iv7"} <= set(ids), ids


def test_the_open_budget_keeps_the_newest_and_counts_the_rest(store):
    lease = store.acquire("acct", "test")
    with store.tx(lease) as tx:
        for i in range(20):
            tx.put("items", f"r{i:02d}", {"id": f"r{i:02d}", "kind": "request", "state": "open", "owner":
                                          "conversation", "data": {}, "waiting_on": None, "updated_ms": 100 + i})
    view = view_from(store.snapshot("acct"), prefix=PREFIX, now_ms=T0)
    p = compose(view, (), Config(open_budget=8))
    open_lines = p.state.split("OPEN\n")[1].split("\n\n")[0].splitlines()
    assert len(open_lines) == 9 and open_lines[-1] == "(+12 more open)"
    assert [ln[1:4] for ln in open_lines[:8]] == ["r19", "r18", "r17", "r16", "r15", "r14", "r13", "r12"]


def test_the_prefix_is_byte_identical_between_runs_and_compose_is_pure(store):
    a = _compose(store, ES_TURNS, "es")
    view = view_from(store.snapshot("acct"), prefix=PREFIX, now_ms=T0 + 60_000, lang="es")
    b = compose(view, (), Config())
    assert a.prefix.encode() == b.prefix.encode() == PREFIX.encode()
    assert compose(view, (), Config()) == b
