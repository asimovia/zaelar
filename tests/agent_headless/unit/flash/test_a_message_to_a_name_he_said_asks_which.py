"""V2-850 · «send Raquel a message» reaches the Raquel he means or asks which — never a name he did not say.

Measured on a cloud session (2026-11-04), typed twice: «manda un mensaje a raquel, pregúntale cómo va y a qué hora
llega». His directory holds ten Raquels. The model made no call, promised «te lo enseño antes de enviarlo», and the
promise repair wrote `mensajeria:draft {contact: "Rakel Karó"}` — the name of a WhatsApp chat, a word nobody said.
The card never asked «which Raquel?», the ask-once memory (V2-849) never started, and the draft was written behind
a closed card while the reply said «ya lo tienes en la app, míralo». On the local engine the same sentence read
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
from tests.outbound_lane import his_hand  # noqa: F401,E402 — these tests run the card's own acts, as his hand

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
    names = ["Raquel Lozoya", "Raquel Ares", "Raquel Salinas Ortega", "raquel.salinasortega", "Raquel Diaz",
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

# ── a draft that waits for him is on screen ─────────────────────────────────────────────────────────────────

# ── a shared first name is a question, not silence ──────────────────────────────────────────────────────────

def test_which_raquel_answers_which_one(world):
    from widgets.contactos import lookup
    ans = lookup.read_query("Which Raquel is in the contacts, and what channels do they have?")
    # V2-887 step 6: «raquel.salinasortega» is Raquel Salinas Ortega's own address row — four people, not five
    assert "4 personas del directorio encajan" in ans and "PREGÚNTALE cuál" in ans
    assert ans.count("·") >= 4, "every one of the four, each on its row"


# ── our own «which one?» is a question, and his answer is remembered ────────────────────────────────────────

def test_a_who_question_leaves_the_conversation_the_card_stood_on(world):
    from widgets.mensajeria import data as ms
    db = ms.load_db()
    db["active_chat"] = {"platform": "whatsapp", "chatId": "120363000000000100@g.us"}
    ms.store.save(ms.WIDGET_ID, db)
    for action in ("send_to", "draft"):
        assert ms.apply_action(action, {"contact": "Raquel", "text": "¿qué tal?"})["ok"] is False
        assert ms.load_db()["active_chat"] is None, f"{action}: «which Raquel?» is not asked over another chat"
