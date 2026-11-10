"""A mail an earlier process already dealt with never reaches the model again (V2-872 F2, node 2.842).

Every start of an engine classified the same unread mails again with a model, for nothing. The connector's memory of
what it had handed over lived in the process, so each start re-seeded from the server's flags alone and handed over
the newest unread again; the messaging widget dropped them as duplicates — AFTER the classifier had run. An engine
that sleeps between uses starts often, and waking it every few minutes to catch its mailbox up would have multiplied
exactly that model call.

Three doors, each tested here through the product:
  · the connector keeps a durable cursor per mailbox (`UIDVALIDITY` + highest UID dealt with): a start hands over only
    what arrived since — including what arrived while it slept — and a renumbered folder voids it;
  · the widget asks its durable ledger BEFORE the model: an item already taken in is never classified again;
  · the event router routes an arriving message once: a re-delivery resumes no row a second time.
"""
from __future__ import annotations

import asyncio

import pytest

import bus
from connectors.email import cursor, service
from connectors.email.service import inbound
from connectors.messaging import ingest
from connectors.messaging import store as msgstore
from widgets import store as wstore
from widgets.mensajeria import owner as owner_mod, triage_agent

ADDR = "me@example.test"


class _Box:
    """An IMAP INBOX the way the connector sees it: numbered UIDs, read and unread, one `UIDVALIDITY`."""

    def __init__(self, validity, read, unread):
        self.address, self.validity, self.read, self.unread = ADDR, validity, set(read), list(unread)

    def inbox_validity(self):
        return self.validity

    def inbox_split(self):
        return {str(u) for u in self.read}, [str(u) for u in self.unread]

    def all_uids(self):
        return {str(u) for u in self.read} | {str(u) for u in self.unread}

    def fetch_new(self, seen, media_dir=None):
        return [{"messageId": u, "chatId": "sender@example.com", "senderId": "sender@example.com", "senderName": "A", "isGroup": False,
                 "body": f"mail {u}", "subject": "s"} for u in sorted(self.all_uids(), key=int) if u not in seen]


@pytest.fixture
def published(monkeypatch):
    out: list[str] = []
    monkeypatch.setattr(ingest, "v2_enabled", lambda: True)
    monkeypatch.setattr(ingest, "publish_msg", lambda platform, m: out.append(m["messageId"]))
    asyncio.run(service.stop())
    yield out
    asyncio.run(service.stop())


def _process(box, polls=3) -> None:
    """One engine process: connect (seed), then a few polls — and the stop that ends it."""
    service.seed_from_mailbox(box)
    for _ in range(polls):
        asyncio.run(inbound._ingest_new(box))
    asyncio.run(service.stop())


def test_a_second_process_hands_over_only_what_arrived_since(published):
    _process(_Box(77, read=[1, 2], unread=[3, 4]))
    assert published == ["3", "4"], "the first connect hands over the unread backlog"
    assert cursor.load(ADDR) == {"validity": 77, "uid": 4}
    published.clear()
    # while it slept: 5 arrived, and he read 3 on his phone — still unread on the server: 4 and 5
    _process(_Box(77, read=[1, 2, 3], unread=[4, 5]))
    assert published == ["5"], f"a mail an earlier process handed over came back: {published}"


def test_mail_that_arrived_while_asleep_is_handed_over_even_if_he_already_read_it(published):
    """The cursor is what THIS engine dealt with; his flags are what HE read. A rule over arriving mail sees each once."""
    _process(_Box(77, read=[1], unread=[2]))
    published.clear()
    _process(_Box(77, read=[1, 3], unread=[2]))
    assert published == ["3"]


def test_a_renumbered_folder_voids_the_cursor(published):
    _process(_Box(77, read=[1, 2], unread=[3, 4]))
    published.clear()
    _process(_Box(78, read=[1, 2], unread=[3, 4]))
    assert published == ["3", "4"], "UIDVALIDITY changed: the first-connect seeding applies again"
    assert cursor.load(ADDR)["validity"] == 78


def test_the_cursor_never_moves_back_within_one_validity():
    assert cursor.save(ADDR, 5, 40) == {"validity": 5, "uid": 40}
    assert cursor.save(ADDR, 5, 12) == {"validity": 5, "uid": 40}
    assert cursor.save(ADDR, 6, 3) == {"validity": 6, "uid": 3}


def test_inbox_validity_reads_the_status_answer(monkeypatch):
    from connectors.email import mailbox as mbmod

    class _IM:
        def status(self, folder, what):
            return "OK", [b'"INBOX" (UIDVALIDITY 1699999999)']

        def logout(self):
            pass

    mb = mbmod.Mailbox.__new__(mbmod.Mailbox)
    monkeypatch.setattr(mb, "_imap", lambda: _IM(), raising=False)
    assert mb.inbox_validity() == 1699999999


# ── the widget asks its ledger before the model ────────────────────────────────────────────────────────────────
@pytest.fixture
def owner(monkeypatch, tmp_path):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    wstore._last_hash.clear()
    monkeypatch.setattr(msgstore, "_to_memory", lambda items: None)
    bus.reset()
    classified: list[list[str]] = []

    async def fake_classify(msgs, name=None):
        classified.append([m["messageId"] for m in msgs])
        return [{**m, "importante": False, "dirigido_a_mi": False, "urgencia": "baja", "motivo": ""} for m in msgs]
    monkeypatch.setattr(triage_agent, "classify", fake_classify)
    o = owner_mod._Owner()
    o._msg_sub = bus.subscribe(ingest.TOPIC_MSG)
    yield o, classified
    bus.reset()


def _arrive(o, *ids):
    for mid in ids:
        ingest.publish_msg("email", {"messageId": mid, "chatId": "sender@example.com", "senderName": "A", "isGroup": False,
                                     "body": f"mail {mid}"})
    asyncio.run(o._triage_batch())


def test_an_item_already_taken_in_is_never_classified_again(owner):
    o, classified = owner
    _arrive(o, "101", "102")
    assert classified == [["101", "102"]]
    _arrive(o, "101", "102", "103")
    assert classified[-1] == ["103"], f"the model saw a mail it had already classified: {classified}"
    _arrive(o, "101")
    assert len(classified) == 2, "a batch of re-deliveries alone costs no model call"


# ── the router routes an arrival once ──────────────────────────────────────────────────────────────────────────
def test_a_re_delivered_message_resumes_a_waiting_row_once(monkeypatch):
    import time
    from nucleo import events
    from nucleo.circuit import ledger
    from nucleo.cli import worker_api_resume
    from nucleo.events import pump
    resumed = []
    monkeypatch.setattr(worker_api_resume, "resume_soon", lambda uid, ans, src="": resumed.append(uid))
    ts = ledger.store()
    ts.task_put({"id": "b9-1", "goal": "wait for the invoice", "state": "running", "created_at": int(time.time())})
    ledger.waiting("b9-1", events.waits_for(events.MAIL_IN, "email:sender@example.com"))
    msg = {"platform": "email", "senderId": "sender@example.com", "chatId": "sender@example.com", "body": "invoice", "messageId": "u7"}
    first = asyncio.run(pump.publish(events.of_message(msg)))
    again = asyncio.run(pump.publish(events.of_message(msg)))
    assert first["as"] == "resume" and again.get("again") is True and resumed == ["b9-1"]
    other = asyncio.run(pump.publish(events.of_message({**msg, "messageId": "u8"})))
    assert other["as"] == "resume" and resumed == ["b9-1", "b9-1"], "a NEW message still routes"
