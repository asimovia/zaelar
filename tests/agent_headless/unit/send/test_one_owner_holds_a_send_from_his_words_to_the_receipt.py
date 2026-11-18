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

        def resolve(name, channel="", relation=""):
            n = " ".join(str(name).lower().split())
            hit = [p for p in PEOPLE if p["name"].lower() == n]
            if hit:
                return {"one": {**hit[0], "platform": channel}}
            several = [p for p in PEOPLE if p["name"].split()[0].lower() in n.split()]
            return {"several": several, "unmatched": []} if several else {"none": True}
        monkeypatch.setattr(people, "resolve", resolve)
        monkeypatch.setattr(people, "_in_front", lambda name: {})
        monkeypatch.setattr(people, "named", lambda q: [p["name"] for p in PEOPLE if q.lower() in p["name"].lower()])
        from nucleo.send import deliver
        monkeypatch.setattr(deliver, "check", lambda d: {"ok": True, "platform": "whatsapp"})

        def run(d):
            self.sent.append(deliver.payload(d))
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
    assert taken and world.sent == [{"text": "I love you very much", "contact": "Odile Brandt", "contact_id": "c2",
                                     "channel": "whatsapp"}]
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


def test_the_send_goes_to_the_chosen_row_by_id_never_the_name_read_again(monkeypatch):
    """Two rows carry the same name: the chosen row's id decides, never a second reading of the name."""
    from widgets import directory
    from widgets.mensajeria.outbound import targets
    rows = [{"id": "a1", "name": "Odile Marsh", "kind": "person", "phone": "+34600000101",
             "channels": [{"platform": "whatsapp", "handle": "+34600000101", "chatId": "34600000101@s.whatsapp.net"}]},
            {"id": "b2", "name": "Odile Marsh", "kind": "person", "phone": "+34600000102",
             "channels": [{"platform": "whatsapp", "handle": "+34600000102", "chatId": "34600000102@s.whatsapp.net"}]}]
    monkeypatch.setattr(directory, "_contacts", lambda: rows)
    monkeypatch.setattr(targets, "connected_platforms", lambda db=None: None)
    got = targets.resolve_target({"contact": "Odile Marsh", "contact_id": "b2", "text": "hi", "channel": "whatsapp"})
    assert got.get("ok") and got["contactId"] == "b2" and got["chatId"].startswith("34600000102"), got
    gone = targets.resolve_target({"contact": "Odile Marsh", "contact_id": "zz", "text": "hi"})
    assert gone.get("ok") is False, "a chosen row that is gone is a refusal, never the name read again"


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


def test_a_yes_split_in_two_sentences_sends_once(world):
    """Audit P0: «Sí» / «mándaselo» arriving as two finals at once each read `send` — one message leaves."""
    world.reads = [_read(who="Odile Marsh", text="I'm late")]
    asyncio.run(owner.intake("Tell Odile Marsh I'm late", {}))
    line = _draft.current().confirm_line
    world.reads = [_read(send=True, bare=True), _read(send=True)]

    async def both():
        out = await asyncio.gather(owner.take("Yes", last_line=line), owner.take("send it", last_line=line))
        await asyncio.gather(*list(receipt.tasks))
        return out
    asyncio.run(both())
    assert len(world.sent) == 1


def test_his_order_never_sends_without_the_confirmation(world):
    """Audit P0: «send Odile Marsh that I'm late, now» read as `send` — he is still read the text first."""
    world.reads = [_read(who="Odile Marsh", text="I'm late", send=True)]
    line = asyncio.run(owner.intake("Send Odile Marsh that I'm late, now", {}))
    assert not world.sent and _draft.current().asked == _draft.CONFIRM and "I'm late" in line


def test_an_unread_order_is_never_lost_and_a_bare_order_asks_who(world):
    """Audit P0: the read failing must not drop the model's call; «I want to send a message» asks who."""
    world.reads = ["not json"]
    line = asyncio.run(owner.intake("Message Odile Marsh that I'm late", {"contact": "Odile Marsh", "text": "I'm late"}))
    assert _draft.current() is not None and _draft.current().asked == _draft.CONFIRM and line and not world.sent
    _draft.reset()
    world.reads = [_read()]
    asyncio.run(owner.intake("I want to send a message", {}))
    assert _draft.current() is not None and _draft.current().asked == _draft.WHO


def test_a_bare_yes_answers_only_the_confirmation_said_last(world):
    """Audit P0: a draft waits at the confirmation; he talks about something else; a bare «ok» to that is not a send."""
    world.reads = [_read(who="Odile Marsh", text="I'm late")]
    asyncio.run(owner.intake("Tell Odile Marsh I'm late", {}))
    world.reads = [_read(send=True, bare=True)]
    taken, line = _take_after("Ok", "Shall I put the radio on?")
    assert taken and not world.sent and "I'm late" in line, "he is read the message again"
    world.reads = [_read(send=True, bare=True)]
    taken, _l = _take_after("Ok", _draft.current().confirm_line)
    assert taken and len(world.sent) == 1


def _take_after(text, last):
    async def go():
        out = await owner.take(text, last_line=last)
        await asyncio.gather(*list(receipt.tasks))
        return out
    return asyncio.run(go())


def test_what_would_stop_it_is_asked_before_the_confirmation_and_a_refusal_keeps_his_text(world, monkeypatch):
    """Audit P1: a contact with several channels is asked which BEFORE the yes; a refusal after it keeps the draft."""
    from nucleo.send import deliver
    monkeypatch.setattr(deliver, "check", lambda d: {"ok": False, "channels": ["whatsapp", "email"]})
    world.reads = [_read(who="Odile Marsh", text="I'm late")]
    line = asyncio.run(owner.intake("Tell Odile Marsh I'm late", {}))
    assert _draft.current().asked == _draft.WHO and "WhatsApp" in line and not world.sent
    monkeypatch.setattr(deliver, "check", lambda d: {"ok": True, "platform": "email"})
    world.reads = [_read(channel="email")]
    assert _take("by email")[0] and _draft.current().asked == _draft.CONFIRM
    monkeypatch.setattr(owner, "_run", lambda d: {"ok": False, "error": "the link is down"})
    world.reads = [_read(send=True)]
    taken, line = _take("send it")
    assert taken and _draft.current() is not None and _draft.current().text == "I'm late"


def test_a_reply_is_read_once_to_its_conversation_and_sent_there_by_id(world, monkeypatch):
    """Audit 2 P0: a reply's `n` is a screen position — read ONCE at intake into its conversation's chat id; what
    leaves is a `send_to` to that chat, and naming somebody else repoints the message, never the reply's number."""
    from nucleo.send import deliver
    monkeypatch.setattr(deliver, "adopt", lambda act, h: {"extra": {}, "target": {
        "name": "Odile Marsh", "contact_id": "", "platform": "whatsapp", "chat_id": "c-77"}} if act == "reply" else
        {"extra": {}})
    world.reads = [_read(text="On my way")]
    asyncio.run(owner.intake("answer that one: on my way", {"n": 3, "text": "On my way", "_act": "reply"}))
    d = _draft.current()
    assert deliver.payload(d) == {"contact": "Odile Marsh", "chat_id": "c-77", "channel": "whatsapp",
                                  "text": "On my way"}
    world.reads = [_read(who="Odile Brandt")]
    _take("no, to Odile Brandt")
    assert deliver.payload(d)["contact_id"] == "c2" and "chat_id" not in deliver.payload(d)


def test_a_message_for_later_is_confirmed_with_its_time_and_held(world, monkeypatch):
    """Audit 2 P1: the time is read once, the confirmation says it, and what leaves is a held draft with its time."""
    from nucleo.send import deliver
    monkeypatch.setattr(deliver, "adopt", lambda act, h: {"extra": {"at_ts": 1_900_000_000.0}})
    world.reads = [_read(who="Odile Marsh", text="Happy birthday")]
    line = asyncio.run(owner.intake("tomorrow at nine tell Odile Marsh happy birthday", {"at": "x", "_act": "send_to"}))
    assert deliver.at(_draft.current()) and "Happy birthday" in line and _ask_when(1_900_000_000.0) in line
    assert "at_ts" not in deliver.payload(_draft.current())


def _ask_when(ts):
    from nucleo.send import ask
    return ask.when(ts)


def test_several_messages_in_one_sentence_are_asked_one_after_the_other(world):
    """Audit P1: the second message of «tell Odile Marsh X and Odile Brandt Y» is not dropped."""
    world.reads = [_read(who="Odile Marsh", text="X")]
    asyncio.run(owner.intake("tell Odile Marsh X and Odile Brandt Y", {}))
    _draft.queue("tell Odile Marsh X and Odile Brandt Y", {"contact": "Odile Brandt", "text": "Y"}, "queued")
    world.reads = [_read(drop=True), _read(who="Odile Marsh", text="X")]     # a re-read would repeat the first one

    async def drop_then_next():
        out = await owner.take("forget the first one")
        await asyncio.sleep(0.05)
        return out
    assert asyncio.run(drop_then_next())[0]
    nxt = _draft.current()
    assert nxt is not None and nxt.target["name"] == "Odile Brandt" and nxt.text == "Y"


def test_the_turn_says_the_confirmation_even_after_its_own_question(world, monkeypatch):
    """Audit P0: a confirmation he never heard is never the one his yes answers — the owner's line is said."""
    from nucleo.send import turn
    world.reads = [_read(who="Odile Marsh", text="I'm late")]
    said = []
    esc = {"send_owner": {"said": "tell Odile Marsh I'm late", "hint": {}, "quiet": True, "by": "our question"}}
    out = asyncio.run(turn.speak(esc, "Anything else?", said.append, type("S", (), {"sanitize": staticmethod(
        lambda t, drop_metadata=False: t)})))
    assert said and "I'm late" in said[-1] and "I'm late" in out


def test_another_order_while_one_is_open_waits_its_turn_and_he_is_told(world):
    """Audit 2 P1: «and send another one to Odile Brandt: hi» while Odile Marsh's waits — never dropped, never merged."""
    world.reads = [_read(who="Odile Marsh", text="I'm late")]
    asyncio.run(owner.intake("tell Odile Marsh I'm late", {}))
    d = _draft.current()
    line = asyncio.run(owner.intake("and another to Odile Brandt: hi", {"contact": "Odile Brandt", "text": "hi"}))
    assert _draft.current() is d and d.text == "I'm late" and line and len(_draft._queue) == 1


def test_a_sentence_that_overlaps_a_send_is_the_conversations(world):
    """Audit 2 P1: while «yes, send it» holds the draft, «what time is it?» is not swallowed with no answer."""
    world.reads = [_read(who="Odile Marsh", text="I'm late")]
    asyncio.run(owner.intake("tell Odile Marsh I'm late", {}))
    line = _draft.current().confirm_line
    world.reads = [_read(send=True)]

    async def both():
        a = asyncio.ensure_future(owner.take("yes, send it", last_line=line))
        await asyncio.sleep(0)
        b = await owner.take("what time is it?", last_line=line)
        await a
        await asyncio.gather(*list(receipt.tasks))
        return b
    assert asyncio.run(both()) == (False, "") and len(world.sent) == 1


def test_a_send_cut_by_his_barge_in_still_leaves_once_and_is_told(world, monkeypatch):
    """Audit 2 P1: a turn cancelled while the act runs — the act finishes, the draft closes, the line is said later."""
    import time as _t
    world.reads = [_read(who="Odile Marsh", text="I'm late")]
    asyncio.run(owner.intake("tell Odile Marsh I'm late", {}))
    d = _draft.current()
    slow = owner._run

    def run_slowly(dd):
        _t.sleep(0.1)
        return slow(dd)
    monkeypatch.setattr(owner, "_run", run_slowly)

    async def cut():
        t = asyncio.ensure_future(owner._send(d))
        await asyncio.sleep(0.02)
        t.cancel()
        await asyncio.sleep(0.3)
        await asyncio.gather(*list(receipt.tasks))
    asyncio.run(cut())
    assert len(world.sent) == 1 and d.state == _draft.SENT and world.said_out


def test_the_confirmation_must_carry_her_whole_name():
    from nucleo.send import ask
    assert ask.carries("Para Raquel Ortega: «Te quiero». ¿Lo mando?", "Te quiero", "Raquel Ortega")
    assert not ask.carries("Para Raquel: «Te quiero». ¿Lo mando?", "Te quiero", "Raquel Ortega")
    assert not ask.carries("Para Raquel Ortega: «Te quiero mucho»", "Te quiero mucho, de verdad", "Raquel Ortega")
