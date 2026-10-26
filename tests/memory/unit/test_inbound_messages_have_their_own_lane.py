"""Inbound messages have their own lane (V2-802 T-03).

The class: a memory of hundreds of rows, mostly inbound messages (`kind='msg'`: «[email] Brokerly: …», «[whatsapp] X
(group): …»). Asked «what's my phone / were we booking a restaurant yesterday», the turn recall and a worker's recall
came back with inbox rows instead of the stored booking rows. Four doors let the inbox in: one ranked pool in the
retriever, promotion by age (short→mid→long), the «what we were talking about» block (`recent_short`) and the
salient block (`salient_long`). This file pins each door shut — without deleting a message: «the carpenters'
numbers Lorena sent us» must still be found, through the messages lane.

Two languages and two domains on purpose (a booking in Spanish, a dentist appointment in English): the lane is a
property of the ROW's kind, never of the words in the question.
"""
import time

import pytest

from memory import api as memapi
from memory import consolidator as memcons
from memory import db as memdb
from memory import embeddings as mememb
from memory import retriever as memret
from memory import writer as memwriter


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _inbox(n: int, words: str) -> list[int]:
    """`n` inbound messages, each repeating the query's words so they win any lexical match by sheer weight."""
    ids = []
    for i in range(n):
        src = ("email", "whatsapp")[i % 2]
        ids.append(memwriter.insert_memory(
            f"[{src}] Promo{i}: {words} {words} oferta {i}", kind="msg", level="short", importance=0.6,
            meta={"source": src, "entity": f"Promo{i}", "trust": "external"}))
    return ids


CASES = [
    # (own row the operator's errand left, words the inbox repeats, the question)
    ("Reserva de mesa para dos en el restaurante Casa Lumbre, sábado 21:30", "reserva restaurante mesa",
     "¿qué restaurante estábamos reservando ayer?"),
    ("Dentist appointment booked with Dr Lowe on Tuesday at 10:00", "dentist appointment booked",
     "what dentist appointment did we book?"),
]


@pytest.mark.parametrize("own_text,inbox_words,question", CASES)
def test_operator_recall_returns_his_rows_and_no_inbox(fresh_db, own_text, inbox_words, question):
    own = memwriter.insert_memory(own_text, kind="result", level="long", importance=0.5)
    inbox = set(_inbox(220, inbox_words))
    res = memapi.query(question, limit=12, reinforce_used=False)
    ids = [m["id"] for m in res["memories"]]
    assert own in ids, f"the operator's own row must be recalled; got {[m['text'][:40] for m in res['memories']]}"
    assert not (set(ids) & inbox), "an inbound message reached the operator-fact recall"


def test_the_lane_is_inside_the_pool_not_a_filter_after_it(fresh_db):
    """With a pool of 10 and 220 inbox rows outranking it lexically, a filter applied AFTER the top-K would find
    nothing left; the lane applied inside each channel still finds the own row."""
    own = memwriter.insert_memory("Reserva de mesa en Casa Lumbre", kind="result", level="long")
    _inbox(220, "reserva mesa casa lumbre")
    res = memret.search("reserva mesa casa lumbre", k=10, limit=5, expand=False, rerank=False, lane="own")
    assert [r["id"] for r in res][:1] == [own]


def test_messages_stay_searchable_in_their_own_lane(fresh_db):
    memwriter.insert_memory("Reserva de mesa en Casa Lumbre", kind="result", level="long")
    _inbox(50, "promo reserva")
    lorena = memwriter.insert_memory(
        "[whatsapp] Lorena: los teléfonos de los carpinteros son 600111222 y 600333444", kind="msg",
        meta={"source": "whatsapp", "entity": "Lorena", "trust": "external"})
    res = memapi.query("teléfonos de los carpinteros que mandó Lorena", lane="messages", reinforce_used=False)
    assert lorena in [m["id"] for m in res["memories"]]
    assert all(m["kind"] == "msg" for m in res["memories"])


def test_all_puts_every_own_row_before_any_message(fresh_db):
    own = memwriter.insert_memory("presupuesto de la reforma del baño", kind="fact", level="long", importance=0.3)
    _inbox(30, "presupuesto reforma baño")
    res = memret.search("presupuesto reforma baño", limit=8, expand=False, rerank=False, lane="all")
    kinds = [r["kind"] for r in res]
    assert res[0]["id"] == own
    assert "msg" in kinds, "the message lane still answers in `all`"
    assert kinds.index("msg") > max(i for i, k in enumerate(kinds) if k != "msg")


def test_age_does_not_promote_an_inbound_message(fresh_db):
    now = int(time.time())
    msg = memwriter.insert_memory("[email] Brokerly: abre tu cuenta", kind="msg", level="short")
    fact = memwriter.insert_memory("vive en Madrid", kind="fact", level="short")
    old_mid_msg = memwriter.insert_memory("[whatsapp] Grupo: hola", kind="msg", level="mid")
    db = memdb.get_db()
    db.execute("UPDATE memories SET created=? WHERE id IN (?,?,?)", (now - 40 * 86400, msg, fact, old_mid_msg))
    memcons.promote(now=now)
    level = lambda i: db.query_one("SELECT level FROM memories WHERE id=?", (i,))["level"]  # noqa: E731
    assert level(fact) in ("mid", "long"), "an own row still ages into durable"
    assert level(msg) == "short"
    assert level(old_mid_msg) == "mid"
    assert db.query_one("SELECT valid FROM memories WHERE id=?", (msg,))["valid"] == 1, "never deleted"


def test_the_passive_blocks_read_no_inbox(fresh_db):
    """`recent_short` is «what WE were talking about»; `salient_long` is «what zaelar knows of HIM». An inbound
    message is neither — including one promoted to long before promotion stopped taking them."""
    conv = memwriter.insert_memory("Operador: reserva para dos · zaelar: hecho", kind="conv", level="short",
                                   meta={"source": "conv", "u": "reserva para dos", "a": "hecho"})
    _inbox(40, "newsletter")
    legacy = memwriter.insert_memory("[email] Brokerly: invierte ya", kind="msg", level="long", importance=0.99,
                                     weight=1.0)
    short_ids = [r["id"] for r in memapi.recent_short(limit=5)]
    assert short_ids == [conv]
    assert legacy not in [r["id"] for r in memapi.salient_long(limit=8)]
