"""V2-850 · «send Raquel a message» reaches the Raquel he means or asks which — never a name he did not say.

Measured on a cloud session (2026-11-04), typed twice: «manda un mensaje a raquel, pregúntale cómo va y a qué hora
llega». His directory holds ten Raquels. The model made no call, promised «te lo enseño antes de enviarlo», and the
promise repair wrote `mensajeria:draft {contact: "Rakel Karó"}` — the name of a WhatsApp chat, a word nobody said.
The card never asked «which Raquel?», the ask-once memory (V2-849) never started, and the draft was written behind
a closed card while the reply said «ya lo tienes en la tarjeta, míralo». On the local engine the same sentence read
the contacts card, got NOTHING back for «Raquel» (ten hits read as «a common word») and said «Raquel isn't listed».

One door each:
  · a contact his words never named is asked on his behalf, never swapped for a word of his (V2-887);
  · a draft held for his review brings its card (`present.mount`), like `send_to`;
  · a question about a first name many people share answers «which one», closest first (`contactos.read_query`).
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

from nucleo.acts import message as gate

RAQUEL = "manda un mensaje a raquel, preguntale como va y a que hora llega"
WIDGETS = pathlib.Path(__file__).resolve().parents[4] / "widgets"


@pytest.fixture
def world(tmp_path, monkeypatch):
    """ISOLATED stores — never the operator's real directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets import directory
    directory._WINDOW.clear(); directory._ASKED.clear()
    from widgets.contactos import data as c
    db = c.load_db()
    names = ["Raquel Jofre", "Raquel Ares", "Raquel Salvador Esteban", "raquel.salvadoresteban", "Raquel Diaz",
             "Rowan Ferrer", "Rowan Lee"]
    for i, n in enumerate(names):
        db["contacts"].append({"id": f"c{i}", "kind": "person", "name": n, "aliases": [], "relation": "",
                               "channels": [{"platform": "whatsapp", "handle": f"3460000000{i}@s.whatsapp.net",
                                             "chatId": f"3460000000{i}@s.whatsapp.net", "volume": 1,
                                             "last_seen": time.time() - 400 * 86400}]})
    c.store.save(c.WIDGET_ID, db)
    yield c
    directory._WINDOW.clear(); directory._ASKED.clear()


# ── a name he never said is ASKED, never rewritten (V2-887) ───────────────────────────────────────────────────

def test_a_name_he_never_said_is_kept_and_asked_never_swapped_for_a_word_of_his(world):
    """Measured 2026-11-11 (local): «te dije su nombre y su apellido» turned the model's «Raquel Salvador» into
    «nombre» and three contacts named «Nombre …». The recipient is read, never rewritten: a name his words never
    named is a question on behalf («¿a Rakel Karó?»), a name they did name passes as it is."""
    from widgets import actions as wa
    assert not hasattr(gate, "his_recipient"), "the recipient rewriter is gone"
    asked = gate.asked_if_leaving(wa.FAST, None, "mensajeria", "send_to",
                                  payload={"contact": "Rakel Karó", "text": "¿Qué tal va?"}, said=RAQUEL)
    assert asked == wa.CONFIRM
    kept = gate.asked_if_leaving(wa.FAST, None, "mensajeria", "send_to",
                                 payload={"contact": "Raquel Salvador", "text": "x"},
                                 said="te dije su nombre y su apellido · mándale un mensaje a Raquel Salvador")
    assert kept == wa.FAST


def test_the_door_runs_on_every_data_op():
    """Since V2-852 M2 a send runs at the worker's exit door, so that is where his recipient goes back in — since V2-857
    phase 5 as the rule of each recipient slot a leaving card DECLARES (`exit_slots`), never as a reader by name."""
    workers = pathlib.Path(gate.__file__).parents[1] / "workers"
    assert "exit_slots.read(" in (workers / "exit_gate.py").read_text()
    assert "his_recipient" not in (workers / "exit_slots.py").read_text().split("def _his_words", 1)[1][:800]
    from nucleo.workers import exit_slots
    for act in ("send_to", "send_draft", "forward"):
        assert exit_slots.declared("mensajeria", act)["recipient"] == {"key": "contact", "from": "his_words"}, act


# ── a draft that waits for him is on screen ─────────────────────────────────────────────────────────────────

def test_a_draft_brings_its_card():
    m = json.loads((WIDGETS / "mensajeria" / "manifest.json").read_text(encoding="utf-8"))
    assert "present.mount" in (m["actions"]["draft"].get("effects") or [])
    from nucleo.flash import canvas_visibility as cv
    shown = []
    import nucleo.flash.canvas_visibility as mod
    orig = mod.present
    try:
        mod.present = lambda target, **k: shown.append((target, k.get("reason"))) or True
        assert cv.present_for_call("mensajeria", "draft") is True
    finally:
        mod.present = orig
    assert shown == [("mensajeria", "producer-mount")]


# ── a shared first name is a question, not silence ──────────────────────────────────────────────────────────

def test_which_raquel_answers_which_one(world):
    from widgets.contactos import lookup
    ans = lookup.read_query("Which Raquel is in the contacts, and what channels do they have?")
    # V2-887 step 6: «raquel.salvadoresteban» is Raquel Salvador Esteban's own address row — four people, not five
    assert "4 personas del directorio encajan" in ans and "PREGÚNTALE cuál" in ans
    assert ans.count("·") >= 4, "every one of the four, each on its row"


# ── our own «which one?» is a question, and his answer is remembered ────────────────────────────────────────

def test_our_which_question_is_kept_and_his_answer_learned(world):
    from widgets import directory
    assert gate.asked_which("¿Cuál Raquel: Salvador, Jofre o Ares?", RAQUEL) is True
    assert directory._ASKED["spoken"] == "raquel"
    from widgets.mensajeria import data as ms
    sent = ms.apply_action("send_to", {"contact": "Raquel Salvador Esteban", "text": "¿qué tal va?"})
    assert sent["ok"] is True and sent["result"]["learned"]["alias"] == "raquel"
    assert ms.apply_action("send_to", {"contact": "Raquel", "text": "x"})["result"]["to"] == "Raquel Salvador Esteban", \
        "asked once: «Raquel» is her from now on"


def test_the_same_in_english_and_what_is_not_a_which_question(world):
    assert gate.asked_which("Which Rowan — Ferrer or Lee?", "text rowan that I'm late") is True
    assert gate.asked_which("Sent it to Rowan Lee.", "text rowan that I'm late") is False, "one person named: no question"
    assert gate.asked_which("Which one?", "what's the weather") is False


@pytest.mark.parametrize("reply", ["Tienes a Raquel Salvador y a Raquel Ares.", "You have Rowan Ferrer and Rowan Lee."])
def test_a_which_question_said_as_a_statement_names_the_last_one_before_its_full_stop(world, reply):
    """Battery C3 es (2026-11-05): «…tienes a Pablo Ruiz y a Pablo Vidal.» was not read as our which-question — the
    address-aware token kept the full stop («vidal.»), so the last person named never matched a name. A sentence's
    closing mark is not part of a name."""
    said = RAQUEL if reply.startswith("Tienes") else "text rowan that I'm late"
    assert gate.asked_which(reply, said) is True


def test_the_voice_turn_end_keeps_our_which_question():
    """The turn that acted on nothing asks `message.asked_which` over its reply, so his answer is remembered (V2-850);
    no «not done» rides on it any more (V2-851 F1)."""
    from pathlib import Path
    from tests import voice_turn_source as _vts
    src = _vts.read(Path(__file__).resolve().parents[4] / "nucleo/turn/pipeline_close.py")
    j = src.index("    if not (_acted_elsewhere or (acted[\"widget\"] and not _ending.only_held())):")
    assert "_message.asked_which(spoken_text" in src[j:j + 400]


def test_a_who_question_leaves_the_conversation_the_card_stood_on(world):
    from widgets.mensajeria import data as ms
    db = ms.load_db()
    db["active_chat"] = {"platform": "whatsapp", "chatId": "120363349887504300@g.us"}
    ms.store.save(ms.WIDGET_ID, db)
    for action in ("send_to", "draft"):
        assert ms.apply_action(action, {"contact": "Raquel", "text": "¿qué tal?"})["ok"] is False
        assert ms.load_db()["active_chat"] is None, f"{action}: «which Raquel?» is not asked over another chat"
