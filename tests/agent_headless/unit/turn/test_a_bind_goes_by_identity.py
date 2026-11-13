"""Binding his answer to a waiting row goes by IDENTITY — an id, never a bar and never text (CRIT-K2b R6, V2-893 L4).

With several rows waiting, the verdict's pick binds only when it is the row that asked him since his last turn (the one
asker notes the `ask_id`, his turn freezes it when its window is built — `circuit.asked_last`), a row our «which task?»
named (its `among`), or a candidate no other waiting row declares. Otherwise he is asked which — «sí» to two yes/no rows
included, whatever the bar — and asking which is ATTENDED: the turn's escalation is no new errand (V2-854 F4). A prose
question about one of several waiting sends opens no third row. Disarm: `_identified` always True; `asked` by text;
`answers_an_open_ask` back to ANSWER only; `to_waiting` back to `rows[0]` → red.
"""
from __future__ import annotations

import threading
import time

import pytest

from nucleo.circuit import asked_last
from nucleo.cli import worker_api_bind as B

A = {"ask_id": "a-1", "task_id": "t-a", "question": "¿Qué fechas quieres para el hotel?", "title": "Hotel en Roma"}
C = {"ask_id": "c-1", "task_id": "t-c", "question": "¿Busco vuelos?", "title": "Vuelos a Roma"}
YES_NO = ["Sí", "No"]
MAIL = {"ask_id": "m-1", "task_id": "t-m", "question": "¿Envío el correo a Marta?", "candidates": YES_NO}
DATE = {"ask_id": "d-1", "task_id": "t-d", "question": "¿Borro la cita del jueves?", "candidates": YES_NO}
WHICH = {"ask_id": "w-1", "task_id": "t-w", "question": "¿A cuál Raquel?", "candidates": ["Raquel Jofre", "Raquel Salvador"]}


@pytest.fixture(autouse=True)
def fresh():
    asked_last.reset()
    yield
    asked_last.reset()


def _brief(choice: str, conf: float) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "judged": "x",
            "result": {B.KEY: {"choice": choice, "confidence": conf, "probs": {choice: conf}}}}


def _we_asked(*asks):
    """Our reply put these questions to him through the one asker, then his turn began (its window was built)."""
    from nucleo.circuit import asker
    for a in asks:
        asker.ask(a["task_id"], {"ask_id": a["ask_id"], "question": a["question"]})
    from nucleo.flash import prior_line
    prior_line.snapshot(type("Brain", (), {})(), [])


def test_two_rows_waiting_and_an_answer_with_no_identity_is_asked_which():
    assert B.bind(_brief("a-1", 0.97), asks=[A, C])[0] == B.ASK_WHICH


def test_the_row_that_asked_since_his_last_turn_is_his_answer_whatever_we_said():
    _we_asked(A)                          # by id: the words we said (reworded, proactive, cut) never matter
    how, asks = B.bind(_brief("a-1", 0.97), asks=[A, C])
    assert how == B.ANSWER and asks[0]["ask_id"] == "a-1"
    _we_asked()                           # a turn of ours that asked nothing leaves no identity for the next
    assert B.bind(_brief("a-1", 0.97), asks=[A, C])[0] == B.ASK_WHICH


def test_the_answer_to_our_which_binds_the_row_it_picks():
    """Audit L4 P1-2: «which task?» names its rows (`among`); his next pick among them IS the identity — no loop."""
    assert B.bind(_brief("a-1", 0.97), asks=[A, C])[0] == B.ASK_WHICH
    B.ask_which([A, C], text="sí")
    _we_asked()
    how, asks = B.bind(_brief("a-1", 0.97), asks=[A, C])
    assert how == B.ANSWER and asks[0]["ask_id"] == "a-1"


def test_two_consents_and_a_yes_are_asked_which_however_sure_the_pick():
    """Audit L4 P1-3: every consent row declares «Sí»: a «Sí» identifies none of them — never a substring of his words."""
    assert B.bind(_brief("d-1#0", 0.9), asks=[MAIL, DATE])[0] == B.ASK_WHICH


def test_a_candidate_no_other_row_declares_identifies_its_row():
    how, asks = B.bind(_brief("w-1#0", 0.8), asks=[WHICH, MAIL])
    assert how == B.ANSWER and asks[0]["choice"] == 0


def test_one_row_waiting_keeps_its_binding():
    how, asks = B.bind(_brief("a-1", 0.7), asks=[A])
    assert how == B.ANSWER and asks[0]["ask_id"] == "a-1"


def test_asking_which_is_attended_the_escalation_is_no_new_errand(monkeypatch):
    """Audit L4 P1-5: two rows, «sí, mándaselo» and the model escalates — asking which still clears the escalation
    (V2-854 F4), or a second send opens beside the waiting one."""
    from nucleo.cli import worker_api
    from nucleo.flash import post_stream_settle as pss
    monkeypatch.setattr(worker_api, "open_asks", lambda: [MAIL, DATE])
    req = {"v": "sí, mándaselo", "more": []}
    assert pss.no_new_errand_for_a_bound_answer(req, _brief("m-1#0", 0.9), worker_acted={}, emit=lambda *a, **k: None)
    assert req["v"] is None
    req = {"v": "pon música clásica", "more": []}
    assert not pss.no_new_errand_for_a_bound_answer(req, _brief(B.NONE, 0.9), worker_acted={},
                                                    emit=lambda *a, **k: None), "a new request was taken for an answer"


def test_a_prose_question_about_one_of_several_sends_opens_no_third_row(monkeypatch):
    """Audit L4 P2-1: several sends of the card wait and nothing names one — no row is guessed, none is opened."""
    from nucleo.request import one_row, send_task, send_task_anchor as SA, send_task_words
    rows = [("t-new", {"ask_id": "n-1", "retained": {}, "created": 2}), ("t-old", {"ask_id": "o-1", "retained": {},
                                                                                     "created": 1})]
    monkeypatch.setattr(SA, "_waiting_sends", lambda wid: rows)
    monkeypatch.setattr(one_row, "people", lambda uid: set())
    monkeypatch.setattr(send_task_words, "his_word_for_people", lambda said: ("", []))
    monkeypatch.setattr(send_task, "artefact", lambda uid: {})
    monkeypatch.setattr(send_task, "missing", lambda art: ("text", "text"))
    monkeypatch.setattr(send_task, "_question", lambda uid, *a, **k: f"ask-{uid}")
    monkeypatch.setattr(send_task, "_emit", lambda *a, **k: None)
    assert SA.to_waiting("mensajeria", "dile que llego tarde", "¿Qué le digo?") == SA.SEVERAL
    asked_last.note("o-1")
    asked_last.turn_began()
    assert SA.to_waiting("mensajeria", "dile que llego tarde", "¿Qué le digo?") == "ask-t-old"


def test_a_new_send_is_told_by_the_people_of_the_waiting_row_never_its_text(monkeypatch):
    """Audit L4 #19: «mándale a Pablo que llego tarde» shares «llego tarde» with the send to Raquel that waits — it is
    a new send all the same: the waiting row is about Raquel."""
    from nucleo.circuit import asker
    from nucleo.request import one_row, send_task, send_task_words as W
    monkeypatch.setattr(W, "identified", lambda brief, floor=None: ("mensajeria", "send_to"))
    monkeypatch.setattr(W, "his_word_for_people", lambda said: ("pablo", [{"name": "Pablo"}]))
    monkeypatch.setattr(asker, "artefact", lambda uid: {"retained": {"kind": send_task.KIND}})
    monkeypatch.setattr(one_row, "people", lambda uid: {"raquel"})
    assert W.new_send({}, "mándale a Pablo que llego tarde", [{"task_id": "t-r"}]) is True
    monkeypatch.setattr(one_row, "people", lambda uid: {"pablo"})
    assert W.new_send({}, "mándale a Pablo que llego tarde", [{"task_id": "t-p"}]) is False


OPEN = {"ask_id": "o-1", "task_id": "t-o", "question": "¿Busco vuelos?"}          # a worker's open question
MAIL_EN = {"ask_id": "e-1", "task_id": "t-e", "question": "Send the mail to Marta?", "candidates": ["Yes", "No"]}


def test_a_consent_yes_beside_an_open_question_is_asked_never_bound_by_the_bar():
    """Audit L4b P1-A: a consent and a worker's open question, «sí» picked as the consent's yes at 0.6 — the open
    question takes any answer, so «Sí» identifies nothing; and against the row that asked, a pick of another is asked."""
    assert B.bind(_brief("m-1#0", 0.6), asks=[MAIL, OPEN])[0] == B.ASK_WHICH
    _we_asked(OPEN)
    assert B.bind(_brief("m-1#0", 0.6), asks=[MAIL, OPEN])[0] == B.ASK_WHICH, "a pick beat the row that asked"
    how, asks = B.bind(_brief(B.SEVERAL, 0.8), asks=[MAIL, OPEN])
    assert how == B.ANSWER and asks[0]["ask_id"] == "o-1", "the row that asked is identity before any pick"
    assert B.bind(_brief("e-1#0", 0.9), asks=[MAIL_EN, DATE])[0] == B.ASK_WHICH, "a yes in another language identified"


def test_a_dropped_fragment_never_spends_the_identity():
    """Audit L4b P1-B: «del 3…» is dropped («the sentence went on») after its window was built — the resumed sentence
    reads the same identity; only a NEW reply of ours advances it."""
    from nucleo.circuit import asker
    from nucleo.flash import prior_line
    brain, reply = type("Brain", (), {})(), {"role": "assistant", "content": "¿Qué fechas quieres para el hotel?"}
    asker.ask(A["task_id"], {"ask_id": A["ask_id"], "question": A["question"]})
    prior_line.snapshot(brain, [reply])                       # «del 3…» — dropped before the bind
    prior_line.snapshot(brain, [reply])                       # «del 3 al 5» — the same window, no reply of ours since
    how, asks = B.bind(_brief("a-1", 0.97), asks=[A, C])
    assert how == B.ANSWER and asks[0]["ask_id"] == "a-1", "the dropped fragment spent the identity"
    prior_line.snapshot(brain, [reply, {"role": "assistant", "content": "Hecho."}])   # a reply that asked nothing
    assert B.bind(_brief("a-1", 0.97), asks=[A, C])[0] == B.ASK_WHICH


def test_after_which_a_candidate_row_is_asked_its_own_question_never_guessed():
    """Audit L4b P1-C: «which?» names the ROWS; two yes/no rows and a second «sí» — the picked row is asked its own
    question again (REASK), which makes it the row that asked; its answer then binds by identity, no loop."""
    from nucleo.cli import worker_api
    B.ask_which([MAIL, DATE], text="sí")
    _we_asked()
    how, asks = B.bind(_brief("d-1#0", 0.7), asks=[MAIL, DATE])
    assert how == B.REASK and asks[0]["ask_id"] == "d-1", (how, asks)
    said = []
    orig = worker_api.emit_ask
    worker_api.emit_ask = lambda **k: said.append(k)
    try:
        assert B.reask(asks[0]) == DATE["question"] and said[0]["ask_id"] == "d-1"
    finally:
        worker_api.emit_ask = orig
    _we_asked()
    how, asks = B.bind(_brief("d-1#0", 0.7), asks=[MAIL, DATE])
    assert how == B.ANSWER and asks[0]["choice"] == 0


def test_alone_counts_only_the_rows_still_waiting():
    """Audit L4b P2-3: our own confirm withdrawn and the task's question asked — the withdrawn one waits no more."""
    from nucleo.circuit import asker
    asker.ask("t-x", {"ask_id": "x-9", "question": "¿Lo envío?"})
    _we_asked(A)
    how, asks = B.bind(_brief("a-1", 0.97), asks=[A, C])
    assert how == B.ANSWER and asks[0]["ask_id"] == "a-1"


def test_an_escalation_dropped_for_an_answer_is_always_asked(monkeypatch):
    """Audit L4b P2-1: the turn also acted on a card — the escalation was dropped for his answer, so the «which?» is
    asked anyway: never an answer and a request both lost in silence."""
    from nucleo.cli import worker_api
    from nucleo.flash import post_stream_settle as pss
    monkeypatch.setattr(worker_api, "open_asks", lambda: [MAIL, DATE])
    said, acted, req = [], {"v": None}, {"v": "sí, mándaselo", "more": []}
    assert pss.no_new_errand_for_a_bound_answer(req, _brief("m-1#0", 0.9), worker_acted=acted, emit=lambda *a, **k: None)
    monkeypatch.setattr(B, "ask_which", lambda asks, text="": "¿Para cuál?")
    out = pss.bind_the_answer(_brief("m-1#0", 0.9), "sí, mándaselo", model_answer="", worker_acted=acted,
                              escalate_req=req, others_acted=True, spoken_text="", send=said.append,
                              speech=type("S", (), {"sanitize": staticmethod(lambda t, **k: t)})(), emit=lambda *a, **k: None)
    assert out == "¿Para cuál?" and said == ["¿Para cuál?"]


def test_a_yes_in_another_language_and_a_name_beside_an_open_question_identify_nothing(monkeypatch):
    """Audit L4b P1-A, its two edges: the interface in Spanish and a consent asked in English («Yes») — a yes or no of
    ANY language identifies no row; and a named candidate beside an open question — the open one takes any answer."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    assert B.bind(_brief("e-1#0", 0.9), asks=[MAIL_EN, DATE])[0] == B.ASK_WHICH
    assert B.bind(_brief("w-1#0", 0.9), asks=[WHICH, OPEN])[0] == B.ASK_WHICH


def _real_turn(*asks, cut: bool = False):
    """Our reply asked these through the one asker, then his turn's window is built over a REAL reply line."""
    from nucleo.circuit import asker
    from nucleo.flash import prior_line
    for a in asks:
        asker.ask(a["task_id"], {"ask_id": a["ask_id"], "question": a["question"]})
    line = {"role": "assistant", "content": "x", **({"cut": True} if cut else {})}
    prior_line.snapshot(type("Brain", (), {})(), [line])
    return line


def test_a_turn_that_also_acted_with_no_escalation_still_asks_which(monkeypatch):
    """Audit L4c F1: two rows, a sure pick with no identity, the model also opened a card and no escalation — the
    «which?» is asked all the same, never silence."""
    from nucleo.cli import worker_api
    from nucleo.flash import post_stream_settle as pss
    monkeypatch.setattr(worker_api, "open_asks", lambda: [MAIL, DATE])
    monkeypatch.setattr(B, "ask_which", lambda asks, text="": "¿Para cuál?")
    said = []
    out = pss.bind_the_answer(_brief("m-1#0", 0.9), "sí", model_answer="", worker_acted={"v": None},
                              escalate_req={"v": None, "more": []}, others_acted=True, spoken_text="", send=said.append,
                              speech=type("S", (), {"sanitize": staticmethod(lambda t, **k: t)})(), emit=lambda *a, **k: None)
    assert out == "¿Para cuál?" and said == ["¿Para cuál?"]


def test_our_which_rules_over_a_question_noted_before_it():
    """Audit L4c F2: a consent noted, then our «which?» over both — his «sí» with `several` is no answer to the consent."""
    from nucleo.circuit import asker
    asker.ask(MAIL["task_id"], {"ask_id": MAIL["ask_id"], "question": MAIL["question"]})
    B.ask_which([MAIL, DATE], text="sí")
    _real_turn()
    assert B.bind(_brief(B.SEVERAL, 0.8), asks=[MAIL, DATE])[0] != B.ANSWER, "the consent asked before «which?» bound"
    assert asked_last.named_by_which(DATE) and not asked_last.asked(MAIL, [MAIL, DATE])


def test_after_reask_a_yes_no_row_takes_only_a_declared_answer(monkeypatch):
    """Audit L4c F3: after REASK the doubt's words are gone, and a candidate row identified with `several` binds only a
    declared answer («sí»/«no») — «sí, envíalo» is asked again, never «taken» with nothing run."""
    from nucleo.cli import worker_api
    monkeypatch.setattr(worker_api, "emit_ask", lambda **k: None)
    B._DOUBT.update(text="sí", at=time.time())
    B.reask(MAIL)
    assert B._DOUBT["text"] == "", "the doubt's words rode the reasked question"
    _real_turn()
    b = _brief(B.SEVERAL, 0.8)
    b["judged"] = "no"
    how, asks = B.bind(b, asks=[MAIL, DATE])
    assert how == B.ANSWER and asks[0]["ask_id"] == "m-1" and asks[0]["choice"] == 1
    B.reask(MAIL)
    _real_turn()
    b["judged"] = "sí, envíalo ya"
    assert B.bind(b, asks=[MAIL, DATE])[0] == B.REASK


def test_a_cut_reply_that_asked_nothing_never_spends_the_identity():
    """Audit L4c F5: «del 3…», we begin «Vale, del…» and he goes on — the cut line asked nothing: the identity stands."""
    _real_turn(A)
    _real_turn(cut=True)
    how, asks = B.bind(_brief("a-1", 0.97), asks=[A, C])
    assert how == B.ANSWER and asks[0]["ask_id"] == "a-1"


def test_a_reasked_consent_keeps_its_buttons_and_its_kind(monkeypatch):
    """Audit L4c P3: the reasked question carries its declared options and kind — a consent is drawn as a consent."""
    from nucleo.circuit import asker
    from nucleo.cli import worker_api
    asker.ask(MAIL["task_id"], {"ask_id": MAIL["ask_id"], "question": MAIL["question"], "options": YES_NO,
                                "consent": "ask_consent"})
    seen = []
    monkeypatch.setattr(worker_api, "emit_ask", lambda **k: seen.append(k))
    B.reask(MAIL)
    assert seen[0]["options"] == YES_NO and seen[0]["kind"] == asker.KIND_CONSENT
