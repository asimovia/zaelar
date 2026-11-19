"""The outbound switch holds an errand's reply at its own door (contention M1, node 5.77).

`ZAELAR_HOLD_OUTBOUND` is read by the one exit door (`connectors/exit`). An errand's (or a stream's) reply asks it
EARLY, before anything is promised (`nucleo/errands/mandate.deliver`, lane `errand`): held → kept as a draft row he
can send later, one line to him, nothing sent. Without the variable it behaves as before.
Nothing here reaches a connector: the send is a double.
"""
from __future__ import annotations

import pytest

from connectors import exit as door


@pytest.fixture
def world(tmp_path, monkeypatch):
    from nucleo import consent
    from widgets import store
    from widgets.contactos import data as cd
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    monkeypatch.delenv(door.ENV, raising=False)
    consent._reset_for_tests()
    cd.apply_action("add_contact", {"name": "Odile Varga", "phone": "611 204 377"})
    door._reset_counters()
    yield
    consent._reset_for_tests()


# ── an errand's reply ─────────────────────────────────────────────────────────────────────────────────────

def _deliver():
    from nucleo.errands import mandate
    errand = {"id": "e1", "objective": "organise a call with Odile",
              "mandate": {"parties": ["c1"], "channels": ["telegram"], "may": ["message"]}}
    sent, told = [], []
    ok = mandate.deliver(errand, "telegram", "987", "Six works for me.", "Odile Varga",
                         lambda *a: sent.append(a) or True, told.append)
    return ok, sent, told


def test_without_the_switch_an_errands_covered_reply_leaves(world):
    ok, sent, told = _deliver()
    assert ok and len(sent) == 1 and not told


@pytest.mark.parametrize("value", ["all", "errand"])
def test_with_the_switch_on_an_errands_reply_is_kept_as_a_draft_and_he_is_told_once(world, monkeypatch, value):
    from widgets.mensajeria import data, held
    monkeypatch.setenv(door.ENV, value)
    ok, sent, told = _deliver()
    assert not ok and not sent, "held: nothing reaches the send door"
    assert len(told) == 1 and "Odile Varga" in told[0], told
    rows = held.held(data.load_db())
    assert [(r["platform"], r["text"]) for r in rows] == [("telegram", "Six works for me.")]
    assert door.counters().get("send/errand/held") == 1, door.counters()


def test_holding_another_lane_leaves_an_errands_reply_alone(world, monkeypatch):
    monkeypatch.setenv(door.ENV, "mandate,invite")
    ok, sent, _ = _deliver()
    assert ok and len(sent) == 1
