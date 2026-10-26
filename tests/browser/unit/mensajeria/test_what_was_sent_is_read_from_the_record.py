"""V2-807 T-12 — a statement about what was SENT is read from the record of what left, which every turn carries.

The class (live, 2026-10-26): «check what was sent» → the reply, composed before any data came back, said the mail went
out «with the name, the phone and the web in the signature». It had none of them: the words came from the
conversation that wrote the draft, not from the message that left. The sent body was not in observability either.

Now: (1) the body as it left (head and tail — the signature is at the end) is a fact of every turn whichever cards are
open, through the one reader of pending state (`nucleo/pending_work.fact_lines`); (2) a send still leaving says it has
not left yet, so a claim about its content has nothing to stand on; (3) the timeline records the body a send of this
card left with, and nothing for what he typed in his own app. Email and Telegram; Spanish and English bodies.
"""
from __future__ import annotations

import time

import pytest

from widgets import store as wstore
from widgets.mensajeria import data, sent

SIGNED = ("Hola, equipo:\n\nQueremos solicitar acceso a la API de reservas para integrarnos directamente con vuestra "
          "plataforma y dejar de depender del navegador para cada reserva que hacen nuestros usuarios. Quedamos a la "
          "espera de vuestra respuesta y de la documentación técnica. Si os encaja, podemos agendar una llamada "
          "breve la semana que viene para revisar juntos el alcance de la integración, los límites de uso y los "
          "requisitos de seguridad que tengáis para los socios.\n\nUn saludo,\n\n-- \nAna Ruiz\nTel. 600 000 000"
          " · zaelar.example")


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    from nucleo import pending_work
    monkeypatch.setattr(pending_work, "_task_rows", lambda now: [])
    pending_work.forget_cache()
    yield


def _facts() -> str:
    from nucleo import pending_work
    pending_work.forget_cache()
    return "\n".join(pending_work.prompt_lines())


def _left(platform: str, chat: str, name: str, body: str, ago: float = 30):
    db = data.load_db()
    db.setdefault("threads", {})[f"{platform}|{chat}"] = {"name": name, "msgs": [
        {"id": "sent:1", "dir": "out", "who": "Tú", "body": body, "ts": time.time() - ago}]}
    wstore.save("mensajeria", db)


def test_the_body_that_left_is_a_fact_of_every_turn_signature_included():
    _left("email", "partners@booking.example", "partners@booking.example", SIGNED)
    block = _facts()
    assert "LO QUE SALIÓ" in block and "ENVIADO por email a partners@booking.example" in block
    assert "Queremos solicitar acceso" in block, "its head"
    assert "Tel. 600 000 000 · zaelar.example" in block, "and its tail: what is asked about is often the signature"


def test_a_short_telegram_in_english_is_quoted_whole():
    _left("telegram", "555", "Rowan", "Moved to 4:15, see you then")
    assert "«Moved to 4:15, see you then»" in _facts()


def test_a_send_still_leaving_says_it_has_not_left():
    db = data.load_db()
    db["pending_send"] = [{"platform": "email", "to": "partners@booking.example", "text": "Hola", "at": time.time()}]
    wstore.save("mensajeria", db)
    block = _facts()
    assert "SALIENDO" in block and "AÚN NO ha salido" in block and "ENVIADO" not in block


def test_an_old_send_is_not_a_fact_any_more():
    _left("email", "x@y.example", "x", SIGNED, ago=3 * 3600)
    assert "SALIÓ" not in _facts()


def test_the_timeline_records_the_body_a_send_of_ours_left_with():
    ev = {"platform": "email", "chatId": "partners@booking.example", "messageId": "sent:1730000000:partners",
          "ref": "r-1", "body": SIGNED, "chatName": "partners@booking.example"}
    rec = sent.left_event(ev)
    assert rec["text"] == SIGNED and rec["extra"]["ref"] == "r-1" and rec["extra"]["chars"] == len(SIGNED)
    # what he typed in his own app is not this card's send
    assert sent.left_event({"platform": "whatsapp", "chatId": "34600", "messageId": "ABC", "body": "hi"}) is None


def test_the_owner_emits_it_where_the_send_comes_back(monkeypatch):
    """Wired where the connector's echo of a send is folded into its thread (`_Owner._apply_outbound`)."""
    from types import SimpleNamespace
    from voice import observer
    from widgets.mensajeria import owner
    got = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **k: got.append((kind, label, k)))
    echo = {"platform": "email", "chatId": "a@b.example", "ref": "r-2", "body": SIGNED,
            "messageId": "sent:1:a@b.example", "timestamp": time.time()}
    fake = SimpleNamespace(_out_sub=object(), _drain=lambda sub: [echo])
    owner._Owner._apply_outbound(fake)
    mine = [g for g in got if g[:2] == ("widget", "sent")]
    assert len(mine) == 1 and mine[0][2]["text"] == SIGNED and mine[0][2]["extra"]["id"] == "mensajeria"
