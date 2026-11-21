"""V2-683 row 3 — the durable errand: it survives a restart, it closes itself, and it is VISIBLE.

The four kinds of «ongoing» this engine had could not hold «contacta con Iván y organiza una reunión esta
tarde»: a turn lasts seconds, a worker session lives in RAM and a restart buries it, a cron carries no
state, and a harness goal expires in five minutes. What is measured here is the missing noun — and mostly
the two properties that make it safe rather than the ones that make it work:

  · it is born only from something the operator actually authorised, and never for the engine itself;
  · it CLOSES itself, because his own rule is that a task is not left open forever — «esa persona puede no
    contestar nunca más».
"""
from __future__ import annotations

import time

import pytest


@pytest.fixture
def er(tmp_path, monkeypatch):
    """An ISOLATED database — never the operator's real one.

    `ZAELAR_DB` is the documented override, and `reset_db()` is what makes it BITE: the connection is a
    process singleton, so a test that merely sets the variable inherits whatever path an earlier test in the
    same session already opened. That is the V2-673 shape exactly — an unisolated test does not fail, it
    leaves something behind — and here what it would leave behind is errands in the operator's own ledger.
    Closed again on the way out, so the next test does not inherit ours either."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    import memory.db as _db
    _db.reset_db()
    # The operator's OWN `config/playbooks.json` must not decide what green means — it holds `shadow`,
    # and the live node (V2-684) writes `shadow: false` into it while it runs. These two cases were green
    # only because that file had never existed on this machine.
    from nucleo import workspace
    from nucleo.errands import playbooks
    monkeypatch.setattr(workspace, "root", lambda: tmp_path)
    playbooks._override_cache = (None, {})
    from nucleo import errands
    yield errands
    _db.reset_db()


def test_the_fixture_really_isolates_the_database(er, tmp_path):
    """The guard for the guard: if this ever points at the real file, every case in this file is writing
    into the operator's ledger while reporting green."""
    import memory.db as _db
    assert str(tmp_path) in str(_db.db_path())


def _one(er, **kw):
    return er.start(kw.pop("objective", "organizar una reunión con Iván esta tarde"), **kw)


# ── it exists, and it lasts ──────────────────────────────────────────────────────────────────────────────

def test_the_operator_s_own_bound_is_what_expires_it(er):
    """Measured with a window that is NOT the default, or the assertion would hold just as well for an
    errand that ignored his words entirely — which is what a disarm proved about the first version."""
    assert er.DEFAULT_WINDOW_S != 2 * 3600
    row = _one(er, objective="habla con Iván en las próximas 2 horas")
    assert 1.9 < (row["deadline"] - row["created_at"]) / 3600 <= 2.1
    slow = _one(er, objective="escríbele a Iván en los próximos 3 días")
    assert 2.9 < (slow["deadline"] - slow["created_at"]) / 86400 <= 3.1


def test_a_vague_window_falls_back_to_a_DECLARED_default_not_a_guess(er):
    """«esta tarde» is not a number. `scheduler.parse_when` refuses to guess a date for exactly this reason;
    here the fallback is a default that is written down, and the pack tells him when it expires."""
    row = _one(er, objective="habla con Iván esta tarde")
    assert (row["deadline"] - row["created_at"]) == pytest.approx(er.DEFAULT_WINDOW_S, abs=2)


def test_nothing_lives_past_the_ceiling(er):
    """A window LONGER than the ceiling is what makes the cap bite — «90 días» does not, because the grammar
    refuses it and falls back to the default, and the test then measured nothing (a green disarm said so)."""
    row = _one(er, objective="escríbele a Iván en los próximos 20 días")
    assert (row["deadline"] - row["created_at"]) > er.MAX_S, "the window itself is past the ceiling"
    assert row["expires_at"] - row["created_at"] <= er.MAX_S


# ── it is born only from what he authorised ──────────────────────────────────────────────────────────────

def test_an_empty_objective_opens_nothing(er):
    assert er.start("   ") is None


# ── a conversation belongs to ONE errand ─────────────────────────────────────────────────────────────────

def test_a_thread_can_only_belong_to_one_errand(er):
    """Structural, not a rule somebody remembers: two errands on one chat is how the same person gets two
    different answers to one message."""
    a, b = _one(er), _one(er, objective="pídele presupuesto a Iván")
    assert er.bind("telegram", "987", a["id"]) is True
    assert er.bind("telegram", "987", b["id"]) is False
    assert er.for_thread("telegram", "987")["id"] == a["id"]


def test_a_CLOSED_errand_owns_no_conversation_any_more(er):
    """A message six weeks later, about something else entirely, must not wake something that is over."""
    a = _one(er)
    er.bind("telegram", "987", a["id"])
    er.close(a["id"], "closed", "hecho")
    assert er.for_thread("telegram", "987") is None
    assert er.bind("telegram", "987", _one(er, objective="otra cosa")["id"]) is True


def test_a_finished_errand_owns_nothing_even_if_its_binding_SURVIVES(er):
    """Two guards for one property, on purpose, and this measures the second: `close()` releases the
    conversations, and the lookup ALSO refuses a finished errand — because any path that moves the state
    without going through `close()` would otherwise leave a dead errand answering in somebody's chat."""
    a = _one(er)
    er.bind("telegram", "987", a["id"])
    er.update(a["id"], state="closed")            # state moved, binding deliberately left in place
    assert er.threads(a["id"]), "the binding is still there — that is the case this covers"
    assert er.for_thread("telegram", "987") is None


# ── it closes itself ─────────────────────────────────────────────────────────────────────────────────────

def test_reading_the_live_list_sweeps_first(er):
    """Nobody should be able to read an expired errand as open — including the prompt."""
    _one(er)
    assert er.live(time.time() + er.MAX_S + 10) == []


def test_an_errand_records_WHY_it_ended(er):
    a = _one(er)
    er.close(a["id"], "blocked", "quiere hablar con el operador")
    row = er.get(a["id"])
    assert row["state"] == "blocked" and "operador" in row["outcome"]


# ── the operator can SEE it ──────────────────────────────────────────────────────────────────────────────

def test_a_closed_errand_leaves_the_live_board_and_lands_in_the_finished_one(er):
    """…and it LANDS somewhere. Before this it simply vanished from the board with no record of the ending."""
    from nucleo.circuit import ledger as _tasks
    a = _one(er)
    er.close(a["id"], why="mesa para 4 el sábado")
    assert _tasks.board("live") == []
    done = _tasks.board("done")
    assert len(done) == 1 and done[0]["id"] == _tasks.errand_uid(a["id"])
    assert done[0]["state"] == "done" and done[0]["outcome"] == "mesa para 4 el sábado"
    assert done[0]["finished_at"] and done[0]["finished_at"] > 0


def test_an_errand_never_enters_the_WORKER_projection(er):
    """`dispatch.active_sessions()` feeds the stall detector, the susurro's dedup and the worker ledger, and
    all three reason about a PROCESS. An errand has none: waiting three hours for somebody to answer is this
    thing working correctly, and a «silent worker» to every one of them. It is merged onto the board at the
    HTTP route instead — the operator's view, not the machinery's."""
    from nucleo import dispatch
    _one(er)
    assert [r for r in dispatch.active_sessions() if r.get("kind") == "encargo"] == []
    assert dispatch.has_active() is False


def test_the_new_event_kind_is_CLASSIFIED(er):
    """An unclassified kind is invisible to every filter in the viewer (the 7.6 inventory)."""
    from voice.observer import _CAT
    assert _CAT.get("errand") == "worker"
