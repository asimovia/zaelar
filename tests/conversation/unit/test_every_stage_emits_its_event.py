"""The observability contract (node 13.24, §8): every stage emits its event, with time, cause, owner and refs.

One request end to end — the sentence arrives, the turn closes, the inbox takes it, the run starts, the request is
opened and the sentence attached by id, the model reads and writes through the gateway, the mouth speaks and is
acknowledged, the request closes — and each stage's kind and label are seen, each carrying `t_ms`, `mono_ms`,
`cause`, `owner` and its `refs` chain. Statically: every kind and label written at a call site of the package is in
`conversation/telemetry.py`, and every kind of the contract is emitted by a piece of the architecture map.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from conversation.ports import Done, ToolCall
from conversation.telemetry import KINDS
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness

ENGINE = Path(__file__).resolve().parents[3]
STAGES = ["conv_ear/opened", "conv_ear/closed", "conv_inbox/accepted", "conv_inbox/dequeued", "conv_run/started",
          "conv_ledger/opened", "conv_ledger/attached", "conv_run/prompt", "conv_run/model_first_token",
          "conv_effect/read", "conv_effect/sealed", "conv_effect/claimed", "conv_effect/submitted",
          "conv_effect/receipt", "conv_run/command", "conv_mouth/say", "conv_mouth/started", "conv_mouth/ack",
          "conv_mouth/ended", "conv_close/answered", "conv_inbox/accounted", "conv_run/ended"]


def test_one_request_end_to_end_says_every_stage_with_its_fields(store):
    h = Harness(store, script={"iv_000001": [
        [ToolCall("c1", "search", {"q": "w1"}), ToolCall("c2", "agenda_add", {"what": "w2"}), Done()],
        [reply("w9"), Done()]]})
    h.utter([(["w1", "w2"], 0)])
    h.pump()
    seen = h.tel.labels()
    missing = [s for s in STAGES if s not in seen]
    assert not missing, missing
    for kind, label, p in h.tel.events:
        assert isinstance(p["t_ms"], int) and isinstance(p["mono_ms"], int), (kind, label)
        assert isinstance(p["cause"], dict) and p["owner"] and isinstance(p["refs"], dict), (kind, label)
        assert label in KINDS[kind]
    by = {f"{k}/{lab}": p for k, lab, p in h.tel.events}
    assert by["conv_close/answered"]["refs"]["req"] == "r_iv_000001"
    assert by["conv_run/started"]["refs"]["run"] and by["conv_run/started"]["refs"]["req"] == "r_iv_000001"
    assert by["conv_ear/closed"]["refs"]["iv"] == "iv_000001" and by["conv_ear/closed"]["trace"] == "iv_000001"
    assert by["conv_effect/claimed"]["refs"]["effect"].startswith("x_")
    assert by["conv_mouth/say"]["refs"]["say"]


def _call_sites() -> list[tuple[str, str, str | None]]:
    out = []
    for p in sorted((ENGINE / "conversation").rglob("*.py")):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "emit" and n.args
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                label = n.args[1].value if len(n.args) > 1 and isinstance(n.args[1], ast.Constant) else None
                out.append((p.relative_to(ENGINE).as_posix(), n.args[0].value, label))
    return out


def test_every_kind_and_label_written_in_the_package_is_in_the_contract_and_on_the_map():
    sites = _call_sites()
    assert len(sites) >= 20
    bad = [s for s in sites if s[1] not in KINDS or (s[2] is not None and s[2] not in KINDS[s[1]])]
    assert not bad, bad
    m = json.loads((ENGINE / ".meshkore/docs/architecture/zaelar-architecture-map.json").read_text())
    drawn = {k for p in m["pieces"] if p["id"].startswith("c_") for k in p.get("emits", [])}
    assert set(KINDS) <= drawn, sorted(set(KINDS) - drawn)
    assert {s[1] for s in sites} == set(KINDS)


def test_a_port_call_over_its_budget_is_an_event(store):
    h = Harness(store, script={"iv_000001": [[ToolCall("c1", "search", {"q": "w1"}), Done()], [reply("w2"), Done()]]})
    h.tools.before = lambda name: h.clock.advance(h.conv.cfg.port_budget_ms + 100)
    h.utter([(["w1"], 0)])
    slow = [p for k, lab, p in h.tel.events if lab == "port_slow"]
    assert slow and slow[0]["port"] == "tools" and slow[0]["ms"] > h.conv.cfg.port_budget_ms
