"""A send task's exit door reads the row's OWN words: a person he named for another order is asked (CRIT-T2j).

Measured on a live engine: «send a whatsapp saying I'm late» (no person) right after three sends to one contact — the
model filled the recipient with that contact; the row recorded `recipient: agent` at its birth, but the exit door
re-read the slot against a time window of his recent turns (`on_his_behalf.errand_words`), which still held the
previous orders' words, called it `his`, and the send left with no question. A name or a text he said for ANOTHER
order is not his word for this one.

Now a record that keeps its own words (`own_words`: the send task's row, `send_task_run._rec`) is read by them alone,
and where the act declares its recipient slot that slot's SOURCE decides the question (`agent` → asked); the leave rule
(`message.asked_if_leaving`) decides only for an act that declares no recipient slot. Through the real door
(`exit_gate.leave`), over an isolated directory, ES and EN, three leaving acts that declare a recipient slot
(`mensajeria:send_to` by WhatsApp and by email, `mensajeria:forward`):

  · his sentence names nobody, another sentence in the ring names her → `recipient: agent`, ONE question;
  · his answer naming her appended to the row's words → `recipient: his`, it passes;
  · a worker's record (no `own_words`) with the same ring → the window still counts, it passes (scoped change);
  · the row's words as a plain string are ONE sentence, never spread character by character;
  · `agenda:invite` (no recipient slot) still asks by the leave rule, and passes when his words name the guest.

Disarms (seen red, source mutated and restored in `finally`): the row read by the window again (2) → the three
recipient-slot acts pass with no question, 3 reds; the leave rule's own reading back as the only reading (3) → the
same three pass, 3 reds.
"""
from __future__ import annotations

import importlib
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from nucleo.workers import exit_gate

#: per variant: the act, the call, the row's own words, his sentence for ANOTHER order (in the ring), his answer
VARIANTS = {
    "es-whatsapp": {"lang": "es", "act": "send_to",
                    "payload": {"contact": "Odile Varga", "text": "llego tarde", "platform": "whatsapp"},
                    "heard": "manda un whatsapp diciendo que llego tarde",
                    "other": "escríbele a Odile Varga que la llamo luego", "answer": "a Odile Varga"},
    "en-email": {"lang": "en", "act": "send_to",
                 "payload": {"contact": "brin@example.com", "text": "I am late", "channel": "email"},
                 "heard": "send an email saying I am late",
                 "other": "email brin@example.com the minutes of Monday", "answer": "to brin@example.com"},
    "en-forward": {"lang": "en", "act": "forward",
                   "payload": {"contact": "Odile Varga", "text": "I am late", "channel": "whatsapp"},
                   "heard": "forward that saying I am late",
                   "other": "tell Odile Varga the dinner is at nine", "answer": "to Odile Varga"},
}
RECIPIENT_ACTS = list(VARIANTS)


@pytest.fixture
def world(tmp_path, monkeypatch):
    from nucleo import consent, his_words, untrusted
    from nucleo.workers.prompts import playbook
    from widgets import contract, store
    from widgets.contactos import data as cd
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    cd.apply_action("add_contact", {"name": "Odile Varga", "phone": "611 204 377"})
    monkeypatch.setattr(playbook, "checkpoint_one", lambda rec: "")
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    untrusted.reset()
    his_words.reset()
    seen: list[dict] = []
    import voice.observer as _obs
    real = _obs.emit
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        (seen.append({"label": label, **(extra or {})}) if str(label).startswith("🚪") else None)
                        or real(kind, label, text=text, role=role, extra=extra))

    def rec(tid, heard, own_words=True):
        base = dict(task_id=tid, playbook_chosen="message", uid=tid, started=time.time(), depth=0, trace_id="",
                    surface="", sheet="", mandate={}, reading=None, heard=heard)
        return SimpleNamespace(**base, **({"own_words": True} if own_words else {}))
    yield SimpleNamespace(rec=rec, seen=seen, his_words=his_words)
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()


def _leave(rec, act, payload, wid="mensajeria"):
    return exit_gate.leave(rec, "widget_data", {"widget_id": wid, "action": act, "payload": dict(payload)})


def _ring(world, v):
    world.his_words.note(v["other"], ts=time.time() - 60)    # his sentence for the PREVIOUS order, a minute ago


# ── the row's own words decide; the recipient slot's source decides the question ──────────────────────────────────

@pytest.mark.parametrize("name", RECIPIENT_ACTS)
def test_a_person_he_named_for_another_order_is_asked(world, name, monkeypatch):
    v = VARIANTS[name]
    monkeypatch.setenv("ZAELAR_LANGUAGE", v["lang"])
    _ring(world, v)
    ex = _leave(world.rec(f"a-{name}", [v["heard"]]), v["act"], v["payload"])
    assert ex.slots.get("recipient") == "agent", ex
    assert ex.verdict == "ask" and ex.question, ex
    assert {e["id"]: e for e in world.seen}[f"a-{name}"]["slots"]["recipient"] == "agent"


@pytest.mark.parametrize("name", RECIPIENT_ACTS)
def test_his_answer_naming_her_on_the_row_makes_it_his(world, name, monkeypatch):
    v = VARIANTS[name]
    monkeypatch.setenv("ZAELAR_LANGUAGE", v["lang"])
    _ring(world, v)
    ex = _leave(world.rec(f"b-{name}", [v["heard"], v["answer"]]), v["act"], v["payload"])
    assert ex.slots.get("recipient") == "his" and ex.verdict == "pass", ex


@pytest.mark.parametrize("name", RECIPIENT_ACTS)
def test_a_workers_record_still_reads_the_window(world, name, monkeypatch):
    v = VARIANTS[name]
    monkeypatch.setenv("ZAELAR_LANGUAGE", v["lang"])
    _ring(world, v)
    ex = _leave(world.rec(f"c-{name}", [v["heard"]], own_words=False), v["act"], v["payload"])
    assert ex.slots.get("recipient") == "his" and ex.verdict == "pass", ex


def test_the_rows_words_as_a_string_are_one_sentence(world, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    ex = _leave(world.rec("d", "send a message to Odile Varga saying I am late"), "send_to",
                {"contact": "Odile Varga", "text": "I am late", "platform": "whatsapp"})
    assert ex.slots.get("recipient") == "his" and ex.verdict == "pass", ex


@pytest.mark.parametrize("lang,heard,named", [
    ("es", ["invita a la cena del viernes"], ["invita a Odile Varga a la cena del viernes"]),
    ("en", ["invite them to Friday's dinner"], ["invite Odile Varga to Friday's dinner"])])
def test_an_act_with_no_recipient_slot_asks_by_the_leave_rule(world, lang, heard, named, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    call = {"who": "Odile Varga", "meeting": "Cena", "date": "2026-11-20"}
    ex = _leave(world.rec(f"e-{lang}", heard), "invite", call, wid="agenda")
    assert "recipient" not in ex.slots and ex.verdict == "ask", ex
    ok = _leave(world.rec(f"e2-{lang}", named), "invite", call, wid="agenda")
    assert ok.verdict == "pass", ok


def test_the_send_tasks_record_keeps_its_own_words(monkeypatch):
    from nucleo.circuit import ledger, spec
    from nucleo.request import send_task_run
    monkeypatch.setattr(ledger, "get", lambda uid: {"created_at": 1.0})
    monkeypatch.setattr(spec, "of_task", lambda uid: {})
    r = send_task_run._rec("u1", {"heard": ["send a message saying I am late"]})
    assert r.own_words is True and r.heard == ["send a message saying I am late"]


# ── the disarms: each half goes red without its line ─────────────────────────────────────────────────────────────

SRC = Path(exit_gate.__file__)
DISARMS = {
    "window": ('said = " ".join(heard if (heard and getattr(rec, "own_words", False)) else '
               '[*_ob.errand_words(rec), *heard])',
               'said = " ".join([*_ob.errand_words(rec), *heard])'),
    "leave_rule": ('unnamed = got.sources["recipient"] == "agent" if "recipient" in got.sources else '
                   'mode == _wa.CONFIRM',
                   'unnamed = mode == _wa.CONFIRM'),
}


def _disarmed(old: str, new: str) -> str:
    orig = SRC.read_text(encoding="utf-8")
    assert old in orig, "the disarm no longer matches exit_gate.py"
    SRC.write_text(orig.replace(old, new), encoding="utf-8")
    shutil.rmtree(SRC.parent / "__pycache__", ignore_errors=True)
    importlib.reload(exit_gate)
    assert new in Path(exit_gate.__file__).read_text(encoding="utf-8")
    return orig


def _restore(orig: str) -> None:
    SRC.write_text(orig, encoding="utf-8")
    shutil.rmtree(SRC.parent / "__pycache__", ignore_errors=True)
    importlib.reload(exit_gate)


@pytest.mark.parametrize("half", list(DISARMS))
@pytest.mark.parametrize("name", RECIPIENT_ACTS)
def test_disarmed_a_person_named_for_another_order_leaves_unasked(world, name, half, monkeypatch):
    v = VARIANTS[name]
    monkeypatch.setenv("ZAELAR_LANGUAGE", v["lang"])
    _ring(world, v)
    orig = _disarmed(*DISARMS[half])
    try:
        ex = _leave(world.rec(f"x-{half}-{name}", [v["heard"]]), v["act"], v["payload"])
        assert ex.verdict == "pass", f"disarmed ({half}), the send no longer leaves unasked: {ex}"
    finally:
        _restore(orig)
