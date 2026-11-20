"""Every event of the manager names its piece of the architecture map (node 13.117, V2-941, plan v3.2 C17).

The operator's session c2cb9f47: every `conv_inbox` event said `piece: unmapped` (`piece_src: conversation/guard.py`)
— the inbox's events are held by its transaction and said when the timed store closes it, from `conversation/guard.py`,
which the map neither draws nor lists as a relay. It is a relay now, so the walk reaches the module that opened the
transaction. Every event the real manager says through the host's telemetry, over a spoken turn and a typed one,
carries a piece the map draws and the family `conversation`.

Disarm seen red: `conversation/guard.py` off the relays → the inbox's events are `unmapped` again.
"""
from __future__ import annotations

from conversation.ports import Done
from conversation.testing.scripted_model import reply
from nucleo.conversation_host.telemetry import ObserverTelemetry
from tests.conversation.unit.convkit import Harness


def test_every_event_says_its_piece_and_family(store, monkeypatch):
    import bus
    from observability import pieces
    got = []
    real = bus.emit_sync
    monkeypatch.setattr(bus, "emit_sync", lambda topic, ev, *a, **k: got.append(dict(ev)) if topic == "observer"
                        else real(topic, ev, *a, **k))
    pieces._code_cache.clear()
    h = Harness(store)
    h.tel.emit = ObserverTelemetry().emit                  # the host's port: what the engine's stream receives
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.utter([(["w1", "w2"], 0)])
    h.settle(9000)
    h.typed("w3", h.clock.mono + 100)
    h.settle(9000)
    conv = [e for e in got if str(e.get("kind", "")).startswith("conv_")]
    assert {e["kind"] for e in conv} >= {"conv_ear", "conv_inbox", "conv_run", "conv_ledger", "conv_close"}
    import json
    with open(pieces.MAP_PATH, encoding="utf-8") as f:
        drawn = {p["id"] for p in json.load(f)["pieces"]}
    bad = sorted({(e["kind"], e.get("piece"), e.get("piece_src")) for e in conv if e.get("piece") not in drawn})
    assert not bad, bad
    assert {e["kind"]: e["piece"] for e in conv if e["kind"] == "conv_inbox"} == {"conv_inbox": "c_inbox"}
    assert {e.get("cat") for e in conv} == {"conversation"}
