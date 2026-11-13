"""The messages card says WHICH conversation each screen has open — never the last order (V2-884 step 3, mensajeria).

A shared app: the computer can be inside one chat while the phone sits on the inbox. The brain could read only the
order (`active_chat`, the mailbox's open letter) and speak it as the screen. Now the card says `thread_open` — the
conversation or letter open, as its header reads it, with its channel ("" = none) — after every paint, with the
revision it applied; opening or closing a chat or a letter (a lens push closes them too) leaves it `?ordered` on every
screen until each acks it. The rendered card (real `widget.js`, real reporter) feeds the real door. Invented people.
Disarms (named in the test): the card that never reports → `state unreported`; a field that follows only the mailbox
→ opening a chat reads as confirmed; a header the report does not read → the open thread is never said.
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

from voice import screens
from widgets import state, state_decl, state_render, store
from tests.browser.unit.widgets.state_card import card_page, deliver, mount, posts, push  # noqa: F401

ENGINE = pathlib.Path(__file__).resolve().parents[4]
PAIRS = [("desktop:aaa", "mobile:bbb"), ("desktop:aaa", "desktop:bbb")]
IRENE = "Irene Sastre"
OPEN = f"{IRENE} (whatsapp)"


@pytest.fixture
def msg(tmp_path, monkeypatch):
    from server import canvas_api
    from widgets.mensajeria import data
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    import widgets.state_api  # noqa: F401 — the move listener
    now = time.time()
    db = data.load_db()
    db["platforms"] = {"whatsapp": {"status": "connected"}}
    db["threads"] = {"whatsapp|irene": {"name": IRENE, "isGroup": False, "complete": True, "touched": now, "msgs": [
        {"id": "m1", "dir": "in", "who": IRENE, "body": "¿quedamos el jueves?", "ts": now - 120, "read": False}]}}
    db["items"] = [{"messageId": "m1", "chatId": "irene", "platform": "whatsapp", "from": IRENE, "group": IRENE,
                    "body": "¿quedamos el jueves?", "ts": now - 120, "urgencia": "media"}]
    db["active_chat"] = None
    store.save("mensajeria", db)

    def on(a, b):
        for d in (a, b):
            screens.attach(d)
        monkeypatch.setattr(canvas_api, "_BY_DEV", {a: {"open": ["mensajeria"]}, b: {"open": ["mensajeria"]}})
    yield data, on
    state._reset_for_tests()
    screens._reset_for_tests()


def _say(dev, n, full=False, **fields):
    return state.report("mensajeria", {"dev": dev, "mount": "m1", "n": n, "full": full or n == 1, "patch": fields,
                                       "ack": state.stamp("mensajeria")})[0]


def test_mensajeria_declares_its_state_and_it_is_shared():
    man = json.loads((ENGINE / "widgets/mensajeria/manifest.json").read_text())
    assert man["screens"] == "shared" and state_decl.problem(man) is None
    assert "adopt" not in json.dumps(man["state"]), "a shared app never adopts (C10 A3)"


@pytest.mark.parametrize("a,b", PAIRS)
def test_two_screens_each_says_which_thread_is_open(msg, a, b):
    data, on = msg
    on(a, b)
    assert state_render.clause("mensajeria") == "mensajeria: state unreported"
    assert _say(a, 1, thread_open=OPEN) == 200 and _say(b, 1, thread_open="") == 200
    assert state_render.clause("mensajeria", dev=a).endswith(f': thread_open="{OPEN}"')
    assert state_render.clause("mensajeria", dev=b).endswith(": at rest")
    from nucleo.flash import widget_read
    assert f'thread_open="{OPEN}"' in widget_read.read("mensajeria")
    data.apply_action("open", {"platform": "whatsapp", "chatId": "irene"})
    for d in (a, b):
        assert "thread_open=?ordered" in state_render.clause("mensajeria", dev=d), f"open read as confirmed on {d}"
    assert _say(b, 2, full=True, thread_open=OPEN) == 200
    assert state_render.clause("mensajeria", dev=b).endswith(f': thread_open="{OPEN}"')
    assert "thread_open=?ordered" in state_render.clause("mensajeria", dev=a), "one screen's ack confirmed the other"
    _say(a, 2, full=True, thread_open=OPEN)
    data.apply_action("show_view", {"platform": "telegram"})                          # a lens push closes it
    assert "thread_open=?ordered" in state_render.clause("mensajeria", dev=a), "a lens push read as confirmed"


def test_the_rendered_card_says_which_thread_is_open_through_the_door(msg, card_page):
    data, on = msg
    a, b = PAIRS[0]
    on(a, b)
    first = {**data.view_data(), "_rev": state.stamp("mensajeria")}
    mount(card_page, "mensajeria", first, a)
    sent = posts(card_page)
    assert len(sent) == 1 and sent[0]["full"] and sent[0]["ack"] == first["_rev"] and sent[0]["patch"] == {"thread_open": ""}
    deliver("mensajeria", sent)
    assert state_render.clause("mensajeria", dev=a).endswith(": at rest")

    data.apply_action("open", {"platform": "whatsapp", "chatId": "irene"})            # the voice: open her chat
    pushed = {**data.view_data(), "_rev": state.stamp("mensajeria")}
    push(card_page, pushed)
    sent = posts(card_page)
    assert sent and sent[-1]["full"] and sent[-1]["ack"] == pushed["_rev"] and sent[-1]["patch"] == {"thread_open": OPEN}, sent
    deliver("mensajeria", sent)
    assert state_render.clause("mensajeria", dev=a).endswith(f': thread_open="{OPEN}"')

    data.apply_action("close", {})
    push(card_page, {**data.view_data(), "_rev": state.stamp("mensajeria")})
    deliver("mensajeria", posts(card_page))
    assert state_render.clause("mensajeria", dev=a).endswith(": at rest"), state_render.clause("mensajeria", dev=a)


def test_opening_a_letter_is_pending_on_its_second_key(msg):
    """Step-3 audit P3: `thread_open` follows the chat AND the mailbox's open letter; a first-key disarm left this
    green. Opening a letter (`mail_open`) moves only the mailbox, and the field is `?ordered` until the screen acks."""
    data, on = msg
    a, b = PAIRS[0]
    on(a, b)
    assert _say(a, 1, thread_open="") == 200
    db = data.load_db()
    db["platforms"]["email"] = {"status": "connected"}
    store.save("mensajeria", db)
    _say(a, 2, full=True, thread_open="")
    data.apply_action("mail_open", {"uid": "77", "folder": "INBOX"})
    assert "thread_open=?ordered" in state_render.clause("mensajeria", dev=a), state_render.clause("mensajeria", dev=a)


def test_a_letter_with_no_subject_is_named_by_its_sender(msg, card_page):
    """Step-3 audit P3: a letter with no subject renders no subject line, and the report read «at rest» over an open
    letter. It reads the sender the envelope shows."""
    data, on = msg
    a, b = PAIRS[0]
    on(a, b)
    db = data.load_db()
    db["platforms"]["email"] = {"status": "connected"}
    db["items"].append({"messageId": "u1", "chatId": "irene@example.test", "platform": "email", "from": IRENE,
                        "subject": "", "body": "", "ts": time.time() - 60, "urgencia": "media"})
    db["mailbox"] = {"folder": "INBOX", "open": {"folder": "INBOX", "uid": "u1", "asked_at": time.time()}}
    db["view"] = {"platform": "email", "n": 1, "at": time.time()}
    store.save("mensajeria", db)
    mount(card_page, "mensajeria", {**data.view_data(), "_rev": state.stamp("mensajeria")}, a)
    sent = posts(card_page)
    assert sent and IRENE in sent[-1]["patch"].get("thread_open", ""), f"an open letter read as nothing open: {sent}"
