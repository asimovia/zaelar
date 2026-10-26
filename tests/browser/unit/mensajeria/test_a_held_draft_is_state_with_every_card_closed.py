"""V2-807 T-10 — a held draft is part of the agent's state while it exists, whichever cards are open.

The class (live, 2026-10-26): the draft's body and its `open_draft` verb reached the prompt only through the mail
card's digest, i.e. only while that card was on screen. With every card closed the model had a title, «draft
waiting for his OK» and `send_draft` — no body, no way to show it — and said it did not have the draft.

Now the row itself carries its recipient, subject, a bounded excerpt and the declared actions that act on it, through
the ONE source every turn reads (`nucleo/pending_work.py`), and the card's digest no longer repeats it. Email and
WhatsApp, Spanish and English text.
"""
from __future__ import annotations

import pytest

from widgets import store as wstore
from widgets.mensajeria import data, inbox_read


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Rowan Pike", "phone": "+34600111222"})
    cd.apply_action("set_channel", {"contactId": "c1", "platform": "whatsapp", "handle": "+34600111222"})
    from nucleo import pending_work
    monkeypatch.setattr(pending_work, "_task_rows", lambda now: [])     # the task board is not this test's
    pending_work.forget_cache()
    yield
    pending_work.forget_cache()


def _lines() -> str:
    from nucleo import pending_work
    pending_work.forget_cache()
    return "\n".join(pending_work.prompt_lines())


def test_with_every_card_closed_the_prompt_carries_the_draft_and_its_doors():
    data.apply_action("draft", {"contact": "partners@booking.example", "subject": "API access",
                                "text": "Hola, queremos acceso a vuestra API de reservas. Un saludo, Zaelar"})
    block = _lines()
    assert "partners@booking.example" in block and "API access" in block, "«do you have it?» names who and what"
    assert "queremos acceso a vuestra API" in block, "the body's excerpt rides with the row"
    assert "mensajeria: open_draft / draft / send_draft / discard_draft" in block
    assert '"contact": "partners@booking.example"' in block, "the payload that names THIS draft"


def test_a_whatsapp_draft_in_english_is_state_too_and_the_excerpt_is_bounded():
    from nucleo import pending_work
    data.apply_action("draft", {"contact": "Rowan Pike", "text": "See you at four — " + "long words " * 80})
    block = _lines()
    assert "Rowan Pike" in block and "See you at four" in block
    line = next(l for l in block.splitlines() if "Rowan Pike" in l)
    excerpt = line.split("«", 1)[1].split("»", 1)[0]
    assert len(excerpt) <= pending_work.EXCERPT_MAX


def test_a_row_cannot_name_an_action_its_card_does_not_declare():
    from nucleo import pending_work
    line = pending_work._line({"id": "mensajeria:x", "widget": "mensajeria", "title": "t", "state": "s",
                               "verbs": ["open_draft", "launch_rockets"], "args": {}})
    assert "open_draft" in line and "launch_rockets" not in line


def test_the_card_digest_no_longer_repeats_the_held_draft():
    data.apply_action("draft", {"contact": "partners@booking.example", "text": "Hola, queremos acceso a la API."})
    assert "BORRADOR esperando su OK" not in inbox_read.prompt_digest(), "one source: the pending-work row"
    assert "queremos acceso" in _lines()


def test_nothing_held_adds_nothing():
    assert _lines() == ""
