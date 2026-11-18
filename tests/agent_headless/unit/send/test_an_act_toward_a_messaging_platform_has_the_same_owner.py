"""V2-938 — every act that leaves toward a messaging platform has the message's owner: a group left, a group created.

Measured in the sandbox replay of his session (2026-11-18): «there is a group called X and another Y — delete them»
went to a Brain Worker; its one question came ten seconds later, out of turn; on some runs the turn refused, on others
it promised and nothing ran. Now the turn hands the call to `nucleo/send` like a message: the card says what it would
refuse and what it FOUND, ONE question names what was found, his yes runs the card's own act, and the receipt is the
final line. A type declared to run on his order (a group created with the people he named) is not asked. Words that
change the act (other groups) are the conversation's: the model makes the call again.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from nucleo.send import draft as _draft, owner, read, receipt


def _read(**kw) -> str:
    return json.dumps({"mine": True, "who": "", "text": None, "channel": "", "send": False, "drop": False, "list": "",
                       **kw})


class World:
    def __init__(self, monkeypatch):
        self.reads, self.ran, self.said_out = [], [], []
        self.refusal, self.asks = None, True
        monkeypatch.setattr(read, "_ask", lambda system, user: self.reads.pop(0) if self.reads else "")
        from widgets import contract
        monkeypatch.setattr(contract, "would_refuse", lambda wid, act, p: self.refusal)
        from nucleo.workers import exit_risk
        monkeypatch.setattr(exit_risk, "asks_by_itself", lambda wid, act, p: self.asks)
        monkeypatch.setattr(exit_risk, "ready_question",
                            lambda wid, act, p: "¿Salgo de «Odile's club» y «Book club» y los quito de tus chats?")
        monkeypatch.setattr(exit_risk, "_card_values", lambda wid, act, p: {"groups": "«Odile's club», «Book club»"})
        from nucleo.send import act

        def run(d):
            self.ran.append((d.act, dict(d.extra)))
            return {"ok": True, "result": {"ref": f"g{len(self.ran)}"}}
        monkeypatch.setattr(act, "run", run)
        from nucleo.request import send_receipt
        monkeypatch.setattr(send_receipt, "receipt", lambda wid, ref, dw: ("sent", ""))

        async def say_out(line, key):
            self.said_out.append(line)
            return {"state": "spoken"}
        monkeypatch.setattr(receipt, "say_out", say_out)
        _draft.reset()


@pytest.fixture
def world(monkeypatch):
    w = World(monkeypatch)
    yield w
    _draft.reset()


LEAVE = {"groups": ["Odile's club", "Book club"], "platform": "whatsapp", "_act": "leave_group", "_widget": "mensajeria"}


def _take(text, last=""):
    async def go():
        out = await owner.take(text, last_line=last)
        await asyncio.gather(*list(receipt.tasks))
        return out
    return asyncio.run(go())


def test_leaving_two_groups_is_asked_once_naming_what_was_found_and_runs_on_his_yes(world):
    line = asyncio.run(owner.intake("delete the groups Odile's club and Book club", dict(LEAVE)))
    d = _draft.current()
    assert d.kind == "act" and d.asked == _draft.CONFIRM and "Odile's club" in line and "Book club" in line
    assert not world.ran
    world.reads = [_read(mine=False)]
    assert _take("why are you so slow?") == (False, ""), "his complaint is the conversation's, never swallowed"
    owner.heard(d.confirm_line)
    world.reads = [_read(send=True)]
    taken, _l = _take("yes, delete them")
    assert taken and world.ran == [("leave_group", {"groups": ["Odile's club", "Book club"], "platform": "whatsapp"})]
    assert world.said_out, "the final line is the act's receipt"


def test_what_the_card_would_refuse_is_said_before_any_question(world):
    world.refusal = {"ok": False, "error": "«Book club»: no está en tu lista de grupos"}
    line = asyncio.run(owner.intake("leave Book club", dict(LEAVE)))
    assert _draft.current() is None and not world.ran and line


def test_a_group_created_with_the_people_he_named_runs_on_his_order(world):
    world.asks = False
    asyncio.run(owner.intake("make a group Trip with Odile", {"name": "Trip", "members": ["Odile"], "platform":
                                                               "whatsapp", "_act": "create_group",
                                                               "_widget": "mensajeria"}))
    asyncio.run(asyncio.sleep(0))
    assert world.ran and world.ran[0][0] == "create_group"


def test_other_groups_in_his_words_change_the_act_and_it_is_asked_again(world):
    asyncio.run(owner.intake("delete the groups Odile's club and Book club", dict(LEAVE)))
    world.reads = [_read(names=["Book club"])]
    taken, line = _take("only Book club")
    d = _draft.current()
    assert taken and d.extra["groups"] == ["Book club"] and d.asked == _draft.CONFIRM and not world.ran


def test_his_words_name_more_groups_than_the_call_carried(world, monkeypatch):
    """Measured in the sandbox: he named two groups, the model's call carried one — his words win."""
    from widgets import field_types
    monkeypatch.setattr(field_types, "declared", lambda wid, act: {"groups": "list"})
    world.reads = [_read(names=["Prueba Zahelar", "excursión de mayo"])]
    asyncio.run(owner.intake("there's Prueba Zahelar and excursión de mayo, delete them",
                             {"name": "Prueba Zahelar", "_act": "leave_group", "_widget": "mensajeria"}))
    assert _draft.current().extra["groups"] == ["Prueba Zahelar", "excursión de mayo"]


def test_his_no_leaves_nothing(world):
    asyncio.run(owner.intake("delete the groups Odile's club and Book club", dict(LEAVE)))
    world.reads = [_read(drop=True)]
    taken, line = _take("no, leave them")
    assert taken and not world.ran and _draft.current() is None


def test_yes_delete_them_naming_the_same_groups_runs_it(world):
    """Measured in the sandbox: «yes, delete them» named the same groups again and was asked again. Naming again what
    the act is about is no change."""
    asyncio.run(owner.intake("delete the groups Odile's club and Book club", dict(LEAVE)))
    owner.heard(_draft.current().confirm_line)
    world.reads = [_read(send=True, names=["odile's club", "BOOK CLUB"])]
    taken, _l = _take("yes, delete them")
    assert taken and len(world.ran) == 1


def test_a_new_message_while_a_group_act_waits_is_taken_never_lost(world):
    """Measured in the sandbox: a group act waiting for his yes, then «now send a message to Odile Marsh»: he moved on
    — the group act is left undone (said) and the message is taken now; a queue behind a question he will not answer
    held it for good."""
    asyncio.run(owner.intake("delete the groups Odile's club and Book club", dict(LEAVE)))
    act = _draft.current()
    world.reads = [_read(who="Odile Marsh"), _read(who="Odile Marsh")]
    line = asyncio.run(owner.intake("now send a message to Odile Marsh", {}, by="order"))
    assert line and act.state == _draft.CANCELLED and _draft.current().kind == "message" and not world.ran


def test_an_order_with_no_call_and_no_act_read_opens_the_declared_act_his_words_order(world):
    """Measured in the sandbox: «there's a group X and another Y — delete them» — no call, no act in the reading, only
    an order on the messaging card. The owner reads which DECLARED act of the card his words order (never a message)
    and asks once, naming the groups."""
    world.reads = [_read(mine=False), json.dumps({"act": "leave_group", "names": ["Odile's club", "Book club"]})]
    line = asyncio.run(owner.intake("there's a group Odile's club and another Book club, delete them",
                                    {"_widget": "mensajeria"}, by="order"))
    d = _draft.current()
    assert d is not None and d.kind == "act" and d.act == "leave_group" and d.extra["groups"] == ["Odile's club",
                                                                                                    "Book club"]
    assert d.asked == _draft.CONFIRM and line and not world.ran


def test_a_choice_outside_what_the_card_declares_opens_nothing(world):
    world.reads = [_read(mine=False), json.dumps({"act": "delete_everything", "names": []})]
    assert asyncio.run(owner.intake("show me my groups", {"_widget": "mensajeria"}, by="order")) == ""
    assert _draft.current() is None
