"""An act whose app never confirmed it is ASKED, never done and never failed (V2-884 C10 A6).

An end state that names `report.<field>` (`nucleo/circuit/reported.py`) reads None for two different reasons, and the
circuit tells them apart:
  · PENDING — the order changed and the surface has not acked it: the act WAITS. The op's own ending leaves it to the
    pulse (`data_ops._write_ending`), and the turn's bare «done» is not said over it (`reply_receipts.end_state_unmet`);
  · `no_ack` — nothing acked within `PENDING_S` of its birth, or no surface reports the app at all: the pulse settles
    it `unverifiable` with the reason's own outcome (`verdict.REASONS["no_ack"]`), and no correction is spoken.
A contrary report is `unmet` only if still contrary at `INLINE_GRACE_S`; when the app's own late tell already said it
(`late_report.falsified_since`), the circuit's correction is not said a second time. Disarmed (each named) → red.
"""
from __future__ import annotations

import pytest

from nucleo import circuit
from nucleo.circuit import reported, spec, verdict
from voice import screens
from widgets import state, state_render, store
from widgets.youtube import data as yt

A = "desktop:aaa"
V1 = "dQw4w9WgXcQ"


@pytest.fixture
def world(monkeypatch, tmp_path):
    from server import canvas_api
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    spec.reset()
    db = yt._load()
    db.update(videoId=V1, title="uno", paused=False, muted=False, volume=70, player_error="")
    store.save("youtube", db)
    state.note_save("youtube", db)
    settled, said = [], []
    real_settle = circuit.settle
    monkeypatch.setattr(circuit, "settle", lambda e=None, **k: settled.append((k.get("verdict"), k.get("outcome")))
                        or real_settle(e, **k))
    monkeypatch.setattr(circuit, "_say_now", lambda e, missing, **k: said.append(missing) or True)
    w = type("W", (), {"settled": settled, "said": said, "canvas": canvas_api})
    yield w
    spec.reset()
    state._reset_for_tests()
    screens._reset_for_tests()


def _screen(monkeypatch, w):
    screens.attach(A)
    monkeypatch.setattr(w.canvas, "_BY_DEV", {A: {"open": ["youtube"]}})
    screens.note_playing("youtube", A)


def _report(n, **fields):
    code, got = state.report("youtube", {"dev": A, "mount": "m1", "n": n, "full": n == 1, "patch": fields,
                                         "ack": state.stamp("youtube")})
    assert code == 200, got


def _act(action, now):
    e = spec.open_for_action("youtube", action, {})
    e["born"] = now
    assert yt.apply_action(action, {}).get("ok")
    return e


def test_with_nothing_reporting_the_act_settles_no_ack_after_its_window(world):
    e = _act("pause", 1000.0)
    assert spec.attest(e) is None and e["awaiting"] == reported.NO_ACK
    circuit.tick(now=1000.0 + state_render.PENDING_S / 2)
    assert world.settled == [], "inside its ack window the act waits"
    e["checked_at"] = 0
    circuit.tick(now=1000.0 + state_render.PENDING_S)
    assert world.settled == [("unverifiable", verdict.REASONS["no_ack"])]
    assert world.said == [], "asked and never confirmed is not a failure to correct out loud"


def test_a_pending_act_waits_and_the_ack_meets_it(world, monkeypatch):
    _screen(monkeypatch, world)
    _report(1, playing=True, playing_id=V1, muted=False, volume=70)
    e = _act("pause", 1000.0)
    assert spec.attest(e) is None and e["awaiting"] == reported.PENDING
    circuit.tick(now=1000.0 + circuit.INLINE_GRACE_S)
    assert world.settled == [], "a pending act is never settled while it waits"
    _report(2, playing=False)
    e["checked_at"] = 0
    circuit.tick(now=1000.0 + circuit.INLINE_GRACE_S + 6)
    assert world.settled == [("met", None)]


def test_a_contrary_report_is_unmet_at_the_grace_and_said_once(world, monkeypatch):
    from widgets import late_report
    _screen(monkeypatch, world)
    _report(1, playing=True, playing_id=V1, muted=True, volume=70)
    e = _act("unmute", 1000.0)
    _report(2, muted=True)                                  # acked, still silent (a browser that blocks the sound)
    circuit.tick(now=1001.0)
    assert world.settled == [], "a muted start that sounds a second later is not a failure"
    monkeypatch.setattr(late_report, "_falsified", {"youtube": 1002.0})   # the app's own tell said it
    e["checked_at"] = 0
    circuit.tick(now=1000.0 + circuit.INLINE_GRACE_S)
    assert [v for v, _ in world.settled] == ["unmet"] and world.said == [], "the app said it: not said twice"


def test_a_contrary_report_no_tell_spoke_for_is_corrected(world, monkeypatch):
    _screen(monkeypatch, world)
    _report(1, playing=True, playing_id=V1, muted=True, volume=70)
    e = _act("unmute", 1000.0)
    _report(2, muted=True)
    e["checked_at"] = 0
    circuit.tick(now=1000.0 + circuit.INLINE_GRACE_S)
    assert [v for v, _ in world.settled] == ["unmet"] and len(world.said) == 1


def test_the_ops_own_ending_leaves_a_pending_act_to_the_pulse(world, monkeypatch):
    from nucleo.flash import data_ops
    _screen(monkeypatch, world)
    _report(1, playing=True, playing_id=V1, muted=False, volume=70)
    e = _act("pause", 1000.0)
    out = spec.attest(e)
    data_ops._write_ending("", "youtube", "pause", {"ok": True}, e, out, False)
    assert world.settled == [], "settled «unverifiable» at the op: the ack the act waits for would never count"


def test_a_bare_done_is_not_said_over_an_act_the_app_has_not_confirmed(world, monkeypatch):
    from nucleo.turn import reply_receipts
    _screen(monkeypatch, world)
    _report(1, playing=True, playing_id=V1, muted=False, volume=70)
    import time
    e = _act("pause", time.time())                          # read now, as the turn's mouth does
    assert reply_receipts.end_state_unmet({"youtube"}) is e
    _report(2, playing=False)
    assert reply_receipts.end_state_unmet({"youtube"}) is None


# ── disarms ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_disarm_without_the_wait_a_pending_act_is_settled_at_its_birth(world, monkeypatch):
    """Disarm: `reported.awaiting` blind → the op's ending settles the act «unverifiable» before the app could ack."""
    from nucleo.flash import data_ops
    _screen(monkeypatch, world)
    _report(1, playing=True, playing_id=V1, muted=False, volume=70)
    monkeypatch.setattr(reported, "awaiting", lambda dw: "")
    e = _act("pause", 1000.0)
    data_ops._write_ending("", "youtube", "pause", {"ok": True}, e, spec.attest(e), False)
    assert world.settled == [("unverifiable", None)]


def test_disarm_without_the_told_check_the_same_fact_is_said_twice(world, monkeypatch):
    """Disarm: `_told_by_the_app` blind → the circuit corrects what the app's tell already said."""
    from widgets import late_report
    _screen(monkeypatch, world)
    _report(1, playing=True, playing_id=V1, muted=True, volume=70)
    e = _act("unmute", 1000.0)
    _report(2, muted=True)
    monkeypatch.setattr(late_report, "_falsified", {"youtube": 1002.0})
    monkeypatch.setattr(circuit, "_told_by_the_app", lambda e: False)
    e["checked_at"] = 0
    circuit.tick(now=1000.0 + circuit.INLINE_GRACE_S)
    assert len(world.said) == 1


# ── the mouth (players audit P2-1) ─────────────────────────────────────────────────────────────────────────────

def _met_on_youtube(action):
    from nucleo.turn import reply
    return reply.Outcome(verdict.MET.name, "youtube", action, object="«uno»")


@pytest.mark.parametrize("action", ["mute", "set_volume", "pause"])
def test_the_mouth_never_says_done_over_an_act_the_app_has_not_confirmed(world, monkeypatch, action):
    """«Hecho: «uno».» was said over `mute`/`volume` with the row pending: the mouth read the op's `ok` and the store's
    title, the row read the report. Both read the report now: unconfirmed → `started`, which says nothing of its own."""
    import time
    from nucleo.turn import reply, reply_receipts
    _screen(monkeypatch, world)
    _report(1, playing=True, playing_id=V1, muted=False, volume=70)
    payload = {"level": 30} if action == "set_volume" else {}
    e = spec.open_for_action("youtube", action, payload)
    e["born"] = time.time()
    assert yt.apply_action(action, payload).get("ok")
    got = reply_receipts.unconfirmed([_met_on_youtube(action)])
    assert reply._value(got[0].verdict) == verdict.STARTED.name, got
    assert [t for _o, t in reply.owed(got, "")] == [reply_receipts._lang().reply_started.format(object="«uno»")]
    assert reply_receipts.bare_ack("Hecho.", {"youtube"}) == reply_receipts._lang().done_asked, "asked, never «done»"


def test_once_confirmed_done_is_said_and_a_contrary_one_is_not_on_the_card(world, monkeypatch):
    import time
    from nucleo.turn import reply, reply_receipts
    _screen(monkeypatch, world)
    _report(1, playing=True, playing_id=V1, muted=False, volume=70)
    e = spec.open_for_action("youtube", "mute", {})
    e["born"] = time.time()
    assert yt.apply_action("mute", {}).get("ok")
    _report(2, muted=False)                                  # acked, and the player did not obey
    assert reply_receipts.bare_ack("Hecho.", {"youtube"}) == reply_receipts._lang().done_not_on_card
    _report(3, muted=True)
    assert reply._value(reply_receipts.unconfirmed([_met_on_youtube("mute")])[0].verdict) == verdict.MET.name
    assert reply_receipts.bare_ack("Hecho.", {"youtube"}) == "Hecho."


def test_disarm_without_the_wait_the_mouth_says_done(world, monkeypatch):
    """Disarm: the wait not read → «Done: «uno».» over an act the app has not confirmed."""
    import time
    from nucleo.turn import reply, reply_receipts
    _screen(monkeypatch, world)
    _report(1, playing=True, playing_id=V1, muted=False, volume=70)
    e = spec.open_for_action("youtube", "mute", {})
    e["born"] = time.time()
    assert yt.apply_action("mute", {}).get("ok")
    monkeypatch.setattr(reported, "awaiting", lambda dw: "")
    assert [t for _o, t in reply.owed(reply_receipts.unconfirmed([_met_on_youtube("mute")]), "")] == \
        [reply_receipts._lang().reply_met.format(object="«uno»")], "the disarm did not land"


def test_the_turns_closing_lines_go_through_the_wait(world, monkeypatch):
    """The wiring: `reply.after_acts` — where every closing line of a turn is gathered — reads the wait."""
    import asyncio
    import time
    from nucleo.turn import reply
    _screen(monkeypatch, world)
    _report(1, playing=True, playing_id=V1, muted=False, volume=70)
    e = spec.open_for_action("youtube", "mute", {})
    e["born"] = time.time()
    assert yt.apply_action("mute", {}).get("ok")
    monkeypatch.setattr(reply, "taken", lambda: [_met_on_youtube("mute")])
    sent: list = []
    speech = type("S", (), {"sanitize": staticmethod(lambda t, **k: t)})
    asyncio.run(reply.after_acts([], "", sent.append, speech))
    assert sent == [reply._lang().reply_started.format(object="«uno»")], f"said as done: {sent}"
