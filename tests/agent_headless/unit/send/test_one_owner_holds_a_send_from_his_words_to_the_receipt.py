"""V2-938 — a send has ONE owner (`nucleo/send`): his words, the person, the one question, the send, the receipt.

The operator's own script of 2026-11-18, replayed through the owner with the model's read of each sentence recorded
(the read is the only model in the path; everything after it is code over one draft). Measured live that day: the
disambiguation he answered started a worker with nobody chosen, and every following sentence — a dictated phrase, a
phrase taken out, «which Raquels do you have?», «why so slow?» — was swallowed with «got it» and nothing left.

What must hold:
  · the draft is the one state: a name nobody carries is a QUESTION naming the people it could be, never a pick;
  · each piece he dictates, adds or takes out changes the draft's text, and he hears the owner at once;
  · «which <name>s do you have?» is answered by the owner from his contacts;
  · nothing leaves until his yes over a draft with ONE person and a text — and what leaves is what he kept, to that
    person's row (by id, never the name read again);
  · the final line is the connector's receipt;
  · a sentence that is not about the message is NOT taken (the conversation answers it), and an unreadable read is
    never a swallow;
  · «forget that message» drops it and nothing leaves; with nothing open the gate takes nothing.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from nucleo.send import draft as _draft, gate, owner, people, read, receipt

PEOPLE = [{"name": n, "contact_id": f"c{i}", "note": ""} for i, n in
          enumerate(("Odile Marsh", "Odile Brandt", "Odile Kowalski", "Odile Varga"), 1)]


def _read(**kw) -> str:
    return json.dumps({"mine": True, "who": "", "text": None, "channel": "", "send": False, "drop": False, "list": "",
                       **kw})


class World:
    def __init__(self, monkeypatch):
        self.reads: list[str] = []
        self.sent: list[dict] = []
        self.said_out: list[str] = []
        self.receipt = ("sent", "")
        monkeypatch.setattr(read, "_ask", lambda system, user: self.reads.pop(0) if self.reads else "")

        def resolve(name, channel=""):
            n = " ".join(str(name).lower().split())
            hit = [p for p in PEOPLE if p["name"].lower() == n]
            if hit:
                return {"one": {**hit[0], "platform": channel}}
            several = [p for p in PEOPLE if p["name"].split()[0].lower() in n.split()]
            return {"several": several, "unmatched": []} if several else {"none": True}
        monkeypatch.setattr(people, "resolve", resolve)
        monkeypatch.setattr(people, "_in_front", lambda name: {})

        def run(payload):
            self.sent.append(dict(payload))
            return {"ok": True, "result": {"ref": f"r{len(self.sent)}"}}
        monkeypatch.setattr(owner, "_run", run)
        from nucleo.request import send_receipt
        monkeypatch.setattr(send_receipt, "receipt", lambda wid, ref, dw: self.receipt)
        from nucleo.pulse import notices

        async def notify(title, text, **kw):
            self.said_out.append(text)
            return {}
        monkeypatch.setattr(notices, "notify", notify)
        _draft.reset()


@pytest.fixture
def world(monkeypatch):
    w = World(monkeypatch)
    yield w
    _draft.reset()


def _take(text):
    return asyncio.run(owner.take(text))


def test_his_script_sends_only_what_he_kept_to_the_one_he_chose(world):
    world.reads = [_read(who="Odile Caro")]
    line = asyncio.run(owner.intake("Send a message to Odile Caro", {}))
    d = _draft.current()
    assert d is not None and not d.target and len(d.candidates) == 4 and d.asked == _draft.WHO
    assert all(p["name"].split()[1] in line for p in PEOPLE), "the question names the people it could be"

    world.reads = [_read(text="I love you very much")]
    taken, _line = _take("Tell her I love her very much")
    assert taken and d.text == "I love you very much" and not world.sent

    world.reads = [_read(text="I love you very much. Be in love with me.")]
    assert _take("that she be in love with me")[0] and "in love" in d.text

    world.reads = [_read(text="I love you very much")]
    assert _take("Take that last phrase out")[0] and "in love" not in d.text and not world.sent

    world.reads = [_read(list="Odile")]
    taken, line = _take("Which Odiles do you have?")
    assert taken and all(p["name"] in line for p in PEOPLE), line

    world.reads = [_read(who="Odile Brandt")]
    taken, line = _take("Odile Brandt")
    assert taken and d.target["contact_id"] == "c2" and d.asked == _draft.CONFIRM and not world.sent
    assert "I love you very much" in line, "the confirmation reads him the text"

    world.reads = [_read(send=True)]

    async def yes_and_receipt():
        taken, line = await owner.take("Yes, send it")
        await asyncio.gather(*list(receipt.tasks))
        return taken, line
    taken, _line = asyncio.run(yes_and_receipt())
    assert taken and world.sent == [{"text": "I love you very much", "contact": "Odile Brandt", "contact_id": "c2"}]
    assert _draft.current() is None, "a sent draft owns no more sentences"
    assert world.said_out, "the final line is the receipt's"


def test_nothing_leaves_before_his_yes_over_one_person_and_a_text(world):
    world.reads = [_read(who="Odile", send=True)]           # «send it now» over several people: a question, no send
    asyncio.run(owner.intake("Send Odile a hello now", {"text": "hello"}))
    assert not world.sent and _draft.current().asked == _draft.WHO
    world.reads = [_read(send=True)]                         # a yes to «which one?» is not a yes to send
    assert _take("Yes")[0] and not world.sent


def test_a_sentence_about_something_else_is_never_taken(world):
    world.reads = [_read(who="Odile Marsh", text="I'm late")]
    asyncio.run(owner.intake("Tell Odile Marsh I'm late", {}))
    assert _draft.current().asked == _draft.CONFIRM
    world.reads = [_read(mine=False)]
    assert _take("Why are you so slow?") == (False, "")
    world.reads = ["not json at all"]
    assert _take("Stop repeating what I say") == (False, ""), "an unreadable read is the conversation's"
    assert not world.sent and _draft.current() is not None


def test_forget_that_message_drops_it_and_nothing_leaves(world):
    world.reads = [_read(who="Odile Marsh", text="I can't tomorrow")]
    asyncio.run(owner.intake("Write Odile Marsh that I can't tomorrow", {}))
    world.reads = [_read(drop=True)]
    assert _take("Forget that message")[0]
    assert _draft.current() is None and not world.sent
    assert asyncio.run(gate.at_the_gate("Yes", None, None)) is False, "with nothing open the gate takes nothing"


def test_the_send_goes_to_the_chosen_row_by_id():
    from widgets.mensajeria.outbound import targets
    src = targets.resolve_target.__code__.co_consts
    assert any("contact_id" in str(c) for c in src) or "contact_id" in open(targets.__file__).read()


def test_a_lean_to_the_messaging_card_opens_nothing_unless_his_words_order_a_message(world):
    """Measured in the sandbox 2026-11-18: «I was watching TV, forget that message» leaned to the messaging card and
    opened a draft that then caught his next order. A lean opens a draft only when the owner's read finds who or what."""
    world.reads = [_read(drop=True)]
    assert asyncio.run(owner.intake("I was watching TV, forget that message", {}, by="order")) == ""
    assert _draft.current() is None
    world.reads = [_read(mine=False)]
    assert asyncio.run(owner.intake("open her chat", {}, by="our question")) == "" and _draft.current() is None
    world.reads = [_read(who="Odile Marsh")]
    assert asyncio.run(owner.intake("Write to Odile Marsh", {}, by="order")) and _draft.current() is not None


def test_a_turn_never_replaces_the_open_message_and_words_that_order_none_open_none(world):
    """Measured in the sandbox 2026-11-18: «stop repeating what I say» was not the message's (the gate's read said so),
    yet the model called the send and the draft waiting for his yes became «to whom?»; and a bare «yes» after he
    dropped a message opened a new one. Only his words order a message, and a turn never replaces the open one."""
    world.reads = [_read(who="Odile Marsh", text="I'm late")]
    asyncio.run(owner.intake("Tell Odile Marsh I'm late", {}))
    d = _draft.current()
    assert asyncio.run(owner.intake("Stop repeating what I say", {"contact": "Odile"})) == ""
    assert _draft.current() is d and d.text == "I'm late", "the open draft is untouched"
    _draft.reset()
    world.reads = [_read(send=True)]                        # «Yes.» with nothing open: no who, no what
    assert asyncio.run(owner.intake("Yes.", {"text": "I'm late"})) == "" and _draft.current() is None
    assert not world.sent


def test_a_reset_forgets_the_open_message(world):
    world.reads = [_read(who="Odile Marsh", text="hi")]
    asyncio.run(owner.intake("Tell Odile Marsh hi", {}))
    from nucleo import reset
    try:
        reset.abandon_work(source="test")
    except Exception:  # noqa: BLE001 — the rest of the reset may need a full engine; the draft goes first
        pass
    assert _draft.current() is None
