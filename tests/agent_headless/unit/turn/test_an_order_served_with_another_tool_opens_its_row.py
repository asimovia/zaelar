"""An order the model served with another tool opens the ORDER's row (group A2, 2026-11-12; ES/EN).

Measured: «mándale un whatsapp a Raquel diciendo que llego tarde» → the model called `mensajeria:show_view` and said
«here are your messages»; «ponle el alias Raquel a Rakel Karó» → `manage_widget_alias`; «apúntame el gimnasio» →
the model asked without calling. Every time the brief had read the order and its act (`request_type = order`,
`screen_action = card:act`, `wants_words = act`), and nobody owned it: the completion runs only when NOTHING acted,
`claimed` only when no call was made. Now the close reads the sure order against what the turn's doors RAN
(`order_unserved.served`: the act, an act of that card with the same declared effect, or the model's own call): a
leaving act becomes its send task (run, or ONE slot asked on its row; a worker when his words name nobody of his), an
act of the card is completed by the empty turn's completion or asks ONE fact question on the order's row, and his
answer fills THAT row. A question, a doubted order, an order answered by words, an escalation or a turn that reached a
worker open nothing. Disarm: make `served` read «something ran» as served → the first test goes red.

The model's valid call is never overruled (node 2.73): an order that only reads is served by what the turn chose to
do, and an act that stays on the card yields to the model's own call that ran on that card.
"""
from __future__ import annotations

import ast
import asyncio
import threading
from pathlib import Path

import pytest

from memory import db as memdb, embeddings as mememb, tasks_store as ts
from nucleo import his_words, untrusted
from nucleo.circuit import asker
from nucleo.request import inline_ask, model, order_unserved as ou, send_task

ROOT = Path(__file__).resolve().parents[4]
WID, ACT = "mensajeria", "send_to"
WORDS = {
    "es": {"said": "Mándale un whatsapp a Raquel diciendo que llego tarde", "text": "que llego tarde",
           "view": "Aquí tienes tus mensajes de WhatsApp.",
           "quoted": 'Le mando a Raquel: "que llego tarde".', "ask": "¿A qué Raquel se lo mando?",
           "nobody": "Mándale un whatsapp a Pablo diciendo hola"},
    "en": {"said": "Send Raquel a WhatsApp saying that I'm running late", "text": "that I'm running late",
           "view": "Here are your WhatsApp messages.",
           "quoted": 'Sending Raquel: "that I\'m running late".', "ask": "Which Raquel should I send it to?",
           "nobody": "Send Pablo a WhatsApp saying hello"},
}
VIEW_OPS = [("mensajeria", "show_view")]
VIEW_CALLS = [{"name": "widget_data", "args": {"widget_id": "mensajeria", "action": "show_view"}}]


def _brief(target=f"{WID}:{ACT}", order=0.95, act=0.95, words=("act", 0.9)) -> dict:
    ev = threading.Event()
    ev.set()
    verdicts = {"request_type": ("order", order), "screen_action": (target, act), "wants_words": words}
    return {"event": ev, "turn_id": "t-1", "open_ids": [WID, "agenda"],
            "result": {k: {"choice": c, "confidence": p} for k, (c, p) in verdicts.items()}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from nucleo import consent
    from widgets import contract, directory, store
    from widgets.contactos import data as cd
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    cd.apply_action("add_contact", {"name": "Raquel Jofre", "phone": "680 762 886"})
    assert directory.note_inbound("whatsapp", {"chatId": "34680762886@s.whatsapp.net",
                                               "senderId": "34680762886@s.whatsapp.net", "from": "Raquel"})
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    untrusted.reset()
    his_words.reset()
    inline_ask._RECENT.clear()
    inline_ask._TAKEN.clear()
    inline_ask._RESUMING.clear()
    sent, events, workers = [], [], []

    async def _dispatch(wid, action, payload, *, row="", text="", **kw):
        sent.append({"widget": wid, "action": action, "payload": dict(payload), "row": row})
        return {"ok": True, "result": {"to": "Raquel Jofre", "channel": "whatsapp"}}
    from nucleo.flash import data_ops
    monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    from nucleo.acts import errand
    monkeypatch.setattr(errand, "escalate_to_slowbrain", lambda text, context=None, **k: workers.append((text, context)) or 7)
    import voice.observer as _obs
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        events.append({"kind": kind, "label": label, "text": text, **(extra or {})}))
    yield {"sent": sent, "events": events, "workers": workers}
    model._TURN.set(None)
    inline_ask._RESUMING.clear()
    inline_ask._TAKEN.clear()
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()
    memdb.reset_db()
    mememb.reset()


def _say(text: str) -> None:
    model._TURN.set(None)
    model.begin(text, trace="t-1")
    his_words.note(text)


def _rows():
    return ts.tasks_where(states=("waiting", "running", "done", "failed", "cancelled"), visible_only=False)


def _open(brief, said, reply, ops=VIEW_OPS, calls=VIEW_CALLS, **kw):
    return ou.open_the_order(brief, said=said, reply=reply, ops=ops, model_calls=calls,
                             escalate_req={"v": None}, worker_acted={"v": None}, emit=None, **kw)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_send_the_model_served_with_a_view_opens_the_send_task_and_asks_the_one_slot_it_lacks(world, lang):
    w = WORDS[lang]
    _say(w["said"])
    got = _open(_brief(), w["said"], w["view"])
    assert got["how"] == "asked" and got["widget"] == WID and got["act"] == ACT
    (row,) = _rows()
    assert row["id"] == got["row"] and row["state"] == "waiting" and row["waiting_for"] == "user_answer"
    ret = asker.artefact(row["id"])["retained"]
    assert ret["kind"] == "send" and ret["action"] == ACT and ret["slot"] == "text"
    assert send_task.artefact(row["id"])["payload"]["contact"] == "raquel", "the person is his word"
    assert world["sent"] == [] and world["workers"] == []
    assert any(e["label"].startswith("🚪 the order the brief identified") and e["how"] == "asked"
               for e in world["events"])


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_send_whose_words_the_model_quoted_runs_on_its_row_with_no_question(world, lang):
    w = WORDS[lang]
    _say(w["said"])
    got = _open(_brief(), w["said"], w["quoted"])
    assert got["how"] == "run"
    (s,) = world["sent"]
    assert (s["widget"], s["action"], s["payload"]["text"], s["row"]) == (WID, ACT, w["text"], got["row"])
    assert world["workers"] == []


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_send_to_nobody_of_his_goes_to_a_worker_on_its_row(world, lang):
    w = WORDS[lang]
    _say(w["nobody"])
    got = _open(_brief(), w["nobody"], w["view"])
    assert got["how"] == "worker" and got["worker"] == 7
    ((text, ctx),) = world["workers"]
    assert text == w["nobody"] and ctx["playbook"] == "message" and ctx["src"] == "served_elsewhere"
    assert world["sent"] == []


def test_a_served_order_a_doubted_one_a_question_or_an_errand_opens_nothing(world):
    w = WORDS["es"]
    _say(w["said"])
    assert _open(_brief(), w["said"], w["view"], ops=[(WID, ACT)]) == {}, "the act ran"
    assert _open(_brief(), w["said"], w["view"], ops=[(WID, "forward")]) == {}, "an act with the same effect ran"
    assert _open(_brief(), w["said"], w["view"], ops=[], calls=[{"name": "widget_data", "args": {
        "widget_id": WID, "action": ACT}}]) == {}, "the model called it: its door owns it"
    assert _open(_brief(), w["said"], w["ask"]) == {}, "a question is held's"
    assert _open(_brief(order=0.55), w["said"], w["view"]) == {}, "an order below the act floor"
    assert _open(_brief(act=0.55), w["said"], w["view"]) == {}, "an act below the act floor"
    assert _open(_brief(words=("tell", 0.9)), w["said"], w["view"]) == {}, "an order answered by words"
    assert ou.open_the_order(_brief(), said=w["said"], reply=w["view"], ops=VIEW_OPS, model_calls=VIEW_CALLS,
                             escalate_req={"v": "send it"}, worker_acted={"v": None}) == {}, "an errand owns it"
    assert ou.open_the_order(_brief(), said=w["said"], reply=w["view"], ops=VIEW_OPS, model_calls=VIEW_CALLS,
                             escalate_req={"v": None}, worker_acted={"v": "answer"}) == {}, "his answer to a worker"
    assert _rows() == [] and world["sent"] == [] and world["workers"] == []


def test_an_act_of_the_card_served_with_another_tool_asks_one_fact_question_and_his_answer_fills_that_row(world):
    said = "Apúntame el gimnasio"
    _say(said)
    calls = [{"name": "manage_widget_alias", "args": {"alias": "gimnasio"}}]
    got = _open(_brief(target="agenda:add_meeting"), said, "Vale, lo apunto.",
                ops=[("contactos", "show_view")], calls=calls, present=lambda *a, **k: True,
                apply_widget_data=lambda *a, **k: None)
    assert got["how"] == "asked" and got["widget"] == "agenda" and got["act"] == "add_meeting"
    (row,) = _rows()
    art = asker.artefact(row["id"])
    assert row["state"] == "waiting" and art["consent"] == "ask_fact"
    assert art["retained"]["kind"] == ou.KIND and art["retained"]["needs"][:2] == ["title", "date"]
    assert "title" in art["question"], art["question"]
    assert world["sent"] == [] and world["workers"] == [], "never a worker for an app act"
    asyncio.run(inline_ask.rerun(row["id"], dict(art, state="pending"), "gimnasio"))
    (s,) = world["sent"]
    assert (s["widget"], s["action"], s["payload"], s["row"]) == ("agenda", "add_meeting", {"title": "gimnasio"}, row["id"])


def test_an_act_of_the_card_the_completion_can_fill_runs_and_asks_nothing(world, monkeypatch):
    from nucleo.flash import direct_action
    ran = []
    monkeypatch.setattr(direct_action, "complete", lambda brief, **kw: ran.append(kw) or "set_alias")
    _say("ponle el alias Raquel a Rakel Karó")
    got = _open(_brief(target="contactos:set_alias"), "ponle el alias Raquel a Rakel Karó", "Hecho.",
                ops=[], calls=[{"name": "manage_widget_alias", "args": {}}], present=lambda *a, **k: True,
                apply_widget_data=lambda *a, **k: None)
    assert got["how"] == "completed" and got["act"] == "set_alias"
    assert ran[0]["widget_id"] == "contactos" and ran[0]["require_order"] is False
    assert _rows() == []


def test_the_models_valid_call_is_never_overruled_by_the_order(world, monkeypatch):
    """Node 2.73 inside A2 (measured live, session 3afe34a8 T4 and the demo pass I1): the order's act never runs
    BESIDE a valid call the model made. Disarm: drop the two last rules of `served` → both go red, and the turn
    restarts the video he was leaving / searches the video card beside the pictures he asked for."""
    tab = [{"name": "widget_data", "args": {"widget_id": "youtube", "action": "show_tab", "payload": {"tab": "inicio"}}}]
    pictures = [{"name": "show_images", "args": {"query": "red ferrari f40"}}]
    assert ou.served("youtube", "search", ops=[], model_calls=pictures), "a view he ordered: the turn chose its view"
    assert ou.served("youtube", "restart", ops=[("youtube", "show_tab")], model_calls=tab), "its own call ran there"
    assert not ou.served("youtube", "search"), "an empty turn served nothing — the completion's case"
    assert not ou.served("youtube", "restart", ops=[], model_calls=tab), "a call that did not run served nothing"
    assert not ou.served("youtube", "restart", ops=[("agenda", "show_view")], model_calls=pictures), "another surface"
    assert not ou.served(WID, ACT, ops=VIEW_OPS, model_calls=VIEW_CALLS), "A2 stands: a send served with a view opens"
    from widgets import effects
    sends = {effects.DATA_WRITE, effects.EXTERNAL_SEND}          # the same two orders, declared as acts that leave
    monkeypatch.setattr(effects, "of", lambda card, act: sends if act in ("search", "restart") else {effects.DATA_READ})
    monkeypatch.setattr(effects, "leaves", lambda card, act: act in ("search", "restart"))
    assert not ou.served("youtube", "search", ops=[], model_calls=pictures), "the rule reads the declared effect"
    assert not ou.served("youtube", "restart", ops=[("youtube", "show_tab")], model_calls=tab), "an act that leaves opens"


def test_disarmed_served_reads_anything_that_ran_as_served_and_the_order_is_lost(world, monkeypatch):
    monkeypatch.setattr(ou, "served", lambda wid, act, ops=(), model_calls=(): bool(ops))
    w = WORDS["es"]
    _say(w["said"])
    assert _open(_brief(), w["said"], w["view"]) == {}
    assert _rows() == []


def test_the_close_reads_the_order_when_the_turn_acted_and_hands_it_what_ran():
    from tests.voice_turn_source import read as _vts_read
    src = _vts_read(ROOT / "nucleo/turn/pipeline_errands.py")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "open_the_order"]
    assert calls, "the close opens the order's row"
    kw = {k.arg: ast.unparse(k.value) for k in calls[0].keywords}
    assert kw["ops"] == "ops" and "_turn_calls" in kw["model_calls"] and kw["apply_widget_data"] == "_apply_widget_data"
    outer = next(n for n in ast.walk(tree) if isinstance(n, ast.If) and "_acted_elsewhere" in ast.unparse(n.test)
                 and n.orelse and "open_the_order" in ast.unparse(n.orelse))
    assert "only_held" in ast.unparse(outer.test), "it runs exactly where the turn ACTED (the else of the acted check)"
    close = _vts_read(ROOT / "nucleo/turn/pipeline_close.py")
    assert 'ops=data_done.get("ops")' in close and "_apply_widget_data=_apply_widget_data" in close


# ── audit 2026-11-12, A1 — an order served through the card's OWN tool ───────────────────────────────────────────────
# «add … to the queue» with the music card open: the model called `play_music {action: queue}` (the music card's door:
# its lane runs the act, no data-op records it), the brief read `musica:queue`, and the close ran the completion BESIDE
# it — the queue played, and `musica:queue` ran again with his whole sentence as its query.

def _order(target: str, *open_ids: str) -> dict:
    """A brief that surely orders `target` with these cards on screen (the completion reads the open set)."""
    b = _brief(target=target)
    b["open_ids"] = list(open_ids)
    return b


_OWN_TOOL = [
    ("musica:queue", "add the wrenfield tapes to the queue",
     {"name": "play_music", "args": {"action": "queue", "query": "the wrenfield tapes"}}),
    ("musica:play", "ponme algo de Los Brezales", {"name": "play_music", "args": {"query": "Los Brezales"}}),
    ("youtube:restart", "empieza el vídeo otra vez", {"name": "play_video", "args": {"action": "restart"}}),
]


@pytest.mark.parametrize("target, said, call", _OWN_TOOL)
def test_an_order_the_model_served_through_the_cards_own_tool_runs_no_second_act(world, target, said, call):
    card, act = target.split(":")
    ran = []
    doors = dict(present=lambda *a, **k: True, apply_widget_data=lambda w, a, p: ran.append((w, a, p)))
    _say(said)
    assert ou.served(card, act, ops=[], model_calls=[call]), "the card's own tool is its door: the model called it"
    assert _open(_order(target, card), said, "Hecho.", ops=[], calls=[call], **doors) == {}
    assert ran == [] and _rows() == [] and world["workers"] == [], "no second act beside the model's call"
    # the control: a tool that drives ANOTHER surface serves nothing of this card — the order still opens (it
    # completes, or asks the fact it lacks)
    other = [{"name": "show_images", "args": {"query": said}}]
    assert not ou.served(card, act, ops=[], model_calls=other)
    got = _open(_order(target, card), said, "Hecho.", ops=[], calls=other, **doors)
    assert (got["widget"], got["act"]) == (card, act) and got["how"] in ("completed", "asked"), got
    assert [(w, a) for w, a, _p in ran] == ([(card, act)] if got["how"] == "completed" else []), ran


def test_disarmed_a_tool_that_drives_no_card_lets_the_order_act_beside_the_models_call(world, monkeypatch):
    from nucleo.acts import media
    monkeypatch.setattr(media, "CARD_OF_TOOL", {})
    target, said, call = _OWN_TOOL[0]
    ran = []
    _say(said)
    got = _open(_order(target, "musica"), said, "Queued.", ops=[], calls=[call], present=lambda *a, **k: True,
                apply_widget_data=lambda w, a, p: ran.append((w, a, p)))
    assert got["how"] == "completed" and ran == [("musica", "queue", {"query": said})], "the double act, as audited"


# ── audit 2026-11-12, A3 — the order's row is its OWN when the model's other act already ended the turn's ────────────
# The model's other act (a view of another card) opened the turn's row and its echo ended it `done`; the order's
# question was then asked on THAT row — an ended row is never re-opened, so the question was spoken and nothing waited.

def _the_other_act_ended_the_turns_row(card: str, action: str) -> str:
    from nucleo import circuit
    row = model.opened(card, action)
    circuit.settle(row=row, state="done", outcome=f"{card}:{action}")
    assert ts.task_get(row)["state"] == "done"
    return row


@pytest.mark.parametrize("said, target, needs", [
    ("Apúntame el dentista", "agenda:add_meeting", "title"),
    ("Save Thaddeus Wrenfield as a favourite", "contactos:set_favorite", "contactId"),
])
def test_a_question_of_the_order_waits_on_a_row_of_its_own_when_the_turns_row_has_ended(world, said, target, needs):
    card, act = target.split(":")
    _say(said)
    ended = _the_other_act_ended_the_turns_row("musica", "open_view")
    got = _open(_brief(target=target), said, "Vale.", ops=[("musica", "open_view")], calls=[],
                present=lambda *a, **k: True, apply_widget_data=lambda *a, **k: None)
    assert got["how"] == "asked" and got["row"] != ended, "an ended row is never re-opened: the order has its own"
    row = ts.task_get(got["row"])
    assert row["state"] == "waiting" and row["waiting_for"] == "user_answer" and row["ask_id"] == got["ask_id"]
    assert asker.artefact(row["id"])["retained"]["needs"][0] == needs
    assert ts.task_get(ended)["state"] == "done", "the other act's row keeps its end"
    from nucleo.cli import worker_api
    assert [a["task_id"] for a in worker_api.open_asks()] == [row["id"]], "his answer has a row to bind to"


def test_a_send_task_of_the_order_is_born_on_a_row_of_its_own_when_the_turns_row_has_ended(world, monkeypatch):
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Odalys Brezmes", "phone": "600 555 0142"})
    said = "Mándale un whatsapp a Odalys"
    _say(said)
    ended = _the_other_act_ended_the_turns_row("contactos", "show_contact")
    got = _open(_brief(), said, "Aquí la tienes.", ops=[("contactos", "show_contact")], calls=[])
    assert got["how"] == "asked" and got["row"] != ended
    assert ts.task_get(got["row"])["state"] == "waiting", "the slot it lacks waits for his answer"


def test_a_turns_row_still_open_is_the_orders_row(world):
    said = "Apúntame el dentista"
    _say(said)
    live = model.opened("musica", "open_view")
    got = _open(_brief(target="agenda:add_meeting"), said, "Vale.", ops=[("musica", "open_view")], calls=[],
                present=lambda *a, **k: True, apply_widget_data=lambda *a, **k: None)
    assert got["row"] == live, "one request, one row — while it is open"


# ── audit 2026-11-12, A6 — a LOOK at the order's card is no serving call when the turn asks to ACT there ─────────────
# «Give Odalys the alias Oda» → the model called `contactos:show_contact` (a lens), the brief read `set_alias`, and
# the lens counted as «the model's own call that ran on that card»: zero acts and no question. T4 (node 2.73) has the
# same shape with the opposite right answer — there the verdict was the wrong one. What tells them apart is a verdict
# the turn already paid for, read as the call's own door reads it (`data_ops.a_view_where_the_verdict_acts`): a lens,
# an order that is no lens, and a sure `wants_words = act`.

def _looked(card: str, lens: str, payload: dict | None = None):
    return [(card, lens)], [{"name": "widget_data", "args": {"widget_id": card, "action": lens, "payload": payload or {}}}]


@pytest.mark.parametrize("said, target, lens", [
    ("Ponle el alias Oda a Odalys Brezmes", "contactos:set_alias", "show_contact"),
    ("Add buying stamps to my tasks for Friday at ten", "agenda:add_task", "show_tasks"),
])
def test_a_look_at_the_orders_card_leaves_the_order_owed_and_it_asks_on_its_row(world, said, target, lens):
    card, act = target.split(":")
    ops, calls = _looked(card, lens)
    _say(said)
    assert ou.served(card, act, ops=ops, model_calls=calls), "with no reading of the turn the model's call stands (2.73)"
    got = _open(_brief(target=target), said, "Aquí lo tienes.", ops=ops, calls=calls, present=lambda *a, **k: True,
                apply_widget_data=lambda *a, **k: None)
    assert got["how"] == "asked" and (got["widget"], got["act"]) == (card, act), got
    (row,) = [r for r in _rows() if r["state"] == "waiting"]
    assert row["id"] == got["row"] and asker.artefact(row["id"])["retained"]["action"] == act
    assert world["sent"] == [] and world["workers"] == []


def test_a_look_still_serves_when_the_turn_does_not_surely_ask_for_an_act(world):
    """T4's side: `youtube:show_tab` against a 0.99 `restart` with no `wants_words = act` — the model's valid call is
    never overruled; and a call that did more than look serves whatever the turn wants."""
    ran = []
    doors = dict(present=lambda *a, **k: True, apply_widget_data=lambda w, a, p: ran.append((w, a, p)))
    ops, calls = _looked("youtube", "show_tab", {"tab": "inicio"})
    for words in (None, ("tell", 0.4), ("act", 0.3)):
        brief = _order("youtube:restart", "youtube")
        brief["result"].pop("wants_words")
        if words:
            brief["result"]["wants_words"] = {"choice": words[0], "confidence": words[1]}
        _say("Venga, vuelve al inicio")
        assert _open(brief, "Venga, vuelve al inicio", "Hecho.", ops=ops, calls=calls, **doors) == {}, words
    wrote = _looked("contactos", "set_favorite")
    _say("Ponle el alias Oda a Odalys Brezmes")
    assert _open(_brief(target="contactos:set_alias"), "Ponle el alias Oda a Odalys Brezmes", "Hecho.",
                 ops=wrote[0], calls=wrote[1], **doors) == {}, "its own WRITE on that card: the model's choice"
    assert ran == [] and _rows() == []


def test_disarmed_a_look_counts_as_serving_and_the_order_is_dropped_in_silence(world, monkeypatch):
    monkeypatch.setattr(ou, "_beyond_looks", lambda brief, wid, act, model_calls: model_calls)
    ops, calls = _looked("contactos", "show_contact")
    _say("Ponle el alias Oda a Odalys Brezmes")
    assert _open(_brief(target="contactos:set_alias"), "Ponle el alias Oda a Odalys Brezmes", "Aquí la tienes.",
                 ops=ops, calls=calls, present=lambda *a, **k: True, apply_widget_data=lambda *a, **k: None) == {}
    assert _rows() == [], "the defect: zero acts and no question"
