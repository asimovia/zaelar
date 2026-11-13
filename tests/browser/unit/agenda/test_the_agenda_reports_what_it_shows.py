"""The agenda's state is what each screen SHOWS, said by the card — never the last order (V2-884 step 3, C6 test 2).

The agenda is a SHARED app: the computer can sit on the week while the phone sits on Thursday, and «show me tomorrow»
moves both. Until now the brain could only read the order (`view.sel`, the last push) and spoke it as what was on
screen. Now the card says its face (`view`: day · week · month · list · tasks) and the date it stands on
(`date_shown`) after every paint, with the revision it applied; the brain reads one clause per screen. An order that
moves the face — the day/lens push (`show_day`, `find_free`, opening an appointment) OR the tasks push
(`show_tasks`) — leaves both fields `?ordered` until the screen acks it: the field follows BOTH order keys.

Run on two screen pairs: a computer and a phone, and two computers. The rendered card (the real `widget.js`, the real
reporter) feeds the real door. Disarms (each named in the test): a field following only its first order key → the
tasks push reads as confirmed; the card that never reports → `state unreported`; an `applied` that re-sends the full
snapshot on every repaint → the repaint is a full snapshot.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from voice import screens
from widgets import state, state_decl, state_render, store
from tests.browser.unit.widgets.state_card import card_page, click, deliver, mount, posts, push  # noqa: F401

ENGINE = pathlib.Path(__file__).resolve().parents[4]
PAIRS = [("desktop:aaa", "mobile:bbb"), ("desktop:aaa", "desktop:bbb")]
_WEEK = json.loads((ENGINE / "tests/browser/unit/phone_apps/agenda_week.json").read_text())


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    """An isolated store, the real agenda manifest, two screens with the agenda open on both."""
    from server import canvas_api
    from widgets.agenda import data as ag
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    import widgets.state_api  # noqa: F401 — the move listener

    def on(a, b):
        for d in (a, b):
            screens.attach(d)
        monkeypatch.setattr(canvas_api, "_BY_DEV", {a: {"open": ["agenda"]}, b: {"open": ["agenda"]}})
    ag.load_db()
    store.save("agenda", {**ag.load_db(), "tick": 1})            # a store to read; the ledger holds its copy
    yield ag, on
    state._reset_for_tests()
    screens._reset_for_tests()


def _say(dev, n, mount="m1", full=False, ack=True, **fields):
    body = {"dev": dev, "mount": mount, "n": n, "full": full or n == 1, "patch": fields}
    if ack:
        body["ack"] = state.stamp("agenda")
    return state.report("agenda", body)[0]


def test_the_agenda_declares_its_state_and_it_is_shared():
    man = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text())
    assert man["screens"] == "shared" and state_decl.problem(man) is None
    assert state_decl.follows_all(man["state"]["report"]["view"]) == ["view", "tasks"]
    assert "adopt" not in json.dumps(man["state"]), "a shared app never adopts (C10 A3)"
    bad = {"state": {"order": {"v": "v"}, "report": {"x": {"type": "bool", "follows": ["v", "nope"]}}}}
    assert "nope" in state_decl.problem(bad), "a list hid an order key that does not exist"
    assert "follows" in state_decl.problem({"state": {"order": {"v": "v"}, "report": {"x": {"type": "bool", "follows": []}}}})


@pytest.mark.parametrize("a,b", PAIRS)
def test_two_screens_two_views_each_its_own_clause_and_a_worker_reads_both(agenda, a, b):
    _ag, on = agenda
    on(a, b)
    assert state_render.clause("agenda") == "agenda: state unreported"
    assert _say(a, 1, view="week", date_shown="2026-11-09") == 200
    assert _say(b, 1, view="day", date_shown="2026-11-12") == 200
    assert state_render.clause("agenda", dev=a).endswith(": view=week, date_shown=\"2026-11-09\"")
    assert state_render.clause("agenda", dev=b).endswith(": view=day, date_shown=\"2026-11-12\"")
    got = {s["dev"]: s["fields"] for s in state_render.read("agenda")["surfaces"]}
    assert got == {a: {"view": "week", "date_shown": "2026-11-09"}, b: {"view": "day", "date_shown": "2026-11-12"}}
    from nucleo.flash import widget_read
    both = widget_read.read("agenda")
    assert "view=week" in both and "view=day" in both, "a worker read only one screen"
    assert _say(b, 2, view="list", date_shown="") == 200
    assert state_render.clause("agenda", dev=b).endswith(": view=list"), "an empty date is at rest, never «?»"


@pytest.mark.parametrize("order", ["show_day", "show_tasks"])
def test_an_order_that_moves_the_face_is_pending_on_every_screen_until_each_acks_it(agenda, order):
    ag, on = agenda
    a, b = PAIRS[0]
    on(a, b)
    _say(a, 1, view="week", date_shown="2026-11-09")
    _say(b, 1, view="week", date_shown="2026-11-09")
    payload = {"day": "mañana"} if order == "show_day" else {"list": "1"}
    assert ag.apply_action(order, payload).get("ok") is not False
    for d in (a, b):
        assert state_render.read("agenda", dev=d)["surfaces"][0]["pending"] == ["view", "date_shown"], (
            f"{order} read as confirmed on {d} — the field follows only its first order key")
        assert "view=?ordered" in state_render.clause("agenda", dev=d)
    shown = ("day", "2026-11-14") if order == "show_day" else ("tasks", "")
    assert _say(a, 2, full=True, view=shown[0], date_shown=shown[1]) == 200            # A applied it
    assert state_render.read("agenda", dev=a)["surfaces"][0]["pending"] == []
    assert state_render.read("agenda", dev=b)["surfaces"][0]["pending"] == ["view", "date_shown"], \
        "one screen's ack confirmed the other"


def test_the_rendered_card_says_its_face_through_the_door(agenda, card_page):
    ag, on = agenda
    a, b = PAIRS[0]
    on(a, b)
    data = {**_WEEK, "_rev": state.stamp("agenda")}
    mount(card_page, "agenda", data, a)
    sent = posts(card_page)
    assert len(sent) == 1 and sent[0]["full"] and sent[0]["ack"] == data["_rev"], sent
    assert sent[0]["patch"] == {"view": "week", "date_shown": "2026-11-09"}, sent
    assert deliver("agenda", sent) == [200]
    assert state_render.clause("agenda", dev=a).endswith(': view=week, date_shown="2026-11-09"')

    click(card_page, ".agtab[data-view='day']")                                      # his click, no order
    sent = posts(card_page)
    assert len(sent) == 1 and not sent[0]["full"] and sent[0]["patch"] == {"view": "day", "date_shown": "2026-11-10"}, \
        "a repaint over the revision already acked re-sent the full snapshot"
    deliver("agenda", sent)

    ag.apply_action("show_day", {"day": "month"})                                    # the voice: the month
    assert "view=?ordered" in state_render.clause("agenda", dev=a)
    pushed = {**_WEEK, "view": ag.view_data()["view"], "_rev": state.stamp("agenda")}
    push(card_page, pushed)
    sent = posts(card_page)
    assert sent and sent[-1]["full"] and sent[-1]["ack"] == pushed["_rev"], sent
    assert sent[-1]["patch"] == {"view": "month", "date_shown": "2026-11"}, sent
    deliver("agenda", sent)
    assert state_render.clause("agenda", dev=a).endswith(': view=month, date_shown="2026-11"'), \
        state_render.clause("agenda", dev=a)

    click(card_page, ".agsecb[data-sec='tasks']")
    deliver("agenda", posts(card_page))
    assert state_render.clause("agenda", dev=a).endswith(": view=tasks"), state_render.clause("agenda", dev=a)
