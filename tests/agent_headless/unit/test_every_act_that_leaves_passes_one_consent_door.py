"""V2-805 — every act that reaches the real world passes the ONE consent door, and his rules override its defaults.

The class: five doors still decided on their own after V2-800 — an errand's reply under its mandate, a cluster
message (whose gate only covered connecting), a worker's click on a booking or payment (the browser's own gate),
the agenda's invitation (a follow-up, kept), and a spoken rule that could only move the GLOBAL knob, so «no me pidas
confirmación para mandar correos» changed what a booking did and could not target one channel.

Generic by construction: four channels (email, WhatsApp, a MeshKore cluster, a website), Spanish and English rules,
a rule that adds friction and one that removes it.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import consent
from widgets import store as wstore

BOOKING = {"name": "Continue", "role": "button", "isSubmit": True, "inForm": True,
           "pageUrl": "https://tables.example.com/booking/confirm", "targetUrl": "", "signals": ""}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path / "widgets"))
    monkeypatch.setattr(wstore, "_last_hash", {})
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Rowan Pike", "phone": "+34600111222"})
    cd.apply_action("set_channel", {"contactId": "c1", "platform": "whatsapp", "handle": "+34600111222"})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    from widgets import confirm as wc
    wc.reset()
    yield
    wc.reset()
    consent._reset_for_tests()


def _email():
    from nucleo.flash import frontend
    return frontend.action_verdict("mensajeria", "send_draft", {"contact": "hospitality@example.com"})


def _whatsapp():
    from nucleo.flash import frontend
    return frontend.action_verdict("mensajeria", "send_draft", {"contact": "Rowan Pike"})


def _cluster():
    from connectors.meshkore import send_gate
    return send_gate.verdict()


def _booking():
    from widgets.navegador import click_gate
    return click_gate.consent_verdict(BOOKING)


def _drafts():
    from widgets.mensajeria import data
    data.apply_action("draft", {"contact": "hospitality@example.com", "text": "Hola"})
    data.apply_action("draft", {"contact": "Rowan Pike", "text": "See you at 4"})


def _asks(v) -> bool:
    return consent.asks(v)


# ── one door, one decision ───────────────────────────────────────────────────────────────────────────────

def test_an_email_a_whatsapp_a_cluster_message_and_a_booking_submit_share_one_decision(monkeypatch):
    _drafts()
    keys = []
    real = consent.decide

    def _spy(**kw):
        keys.append(kw.get("policy_key"))
        return real(**kw)
    monkeypatch.setattr(consent, "decide", _spy)
    defaults = [_asks(_email()), _asks(_whatsapp()), _asks(_cluster()), _asks(_booking())]
    assert keys == ["messaging.send_new@email", "messaging.send_new@whatsapp", "messaging.send_new@meshkore",
                    "web.commit"], keys
    assert defaults == [False, False, False, True], "the defaults are the ones each door had before — none moved"
    consent.set_class("messaging.send_new", "ask")          # «pregúntame antes de mandar mensajes»
    assert [_asks(_email()), _asks(_whatsapp()), _asks(_cluster())] == [True, True, True]
    consent.set_class("web.commit", "allow")                # «no me pidas confirmación para reservar»
    assert not _asks(_booking())
    assert _asks(_cluster()), "a rule for bookings never reaches a message"


def test_a_payment_click_stays_its_own_class_and_an_unreadable_page_keeps_asking():
    from widgets.navegador import click_gate
    consent.set_class("web.commit", "allow")
    pay = dict(BOOKING, signals="cc-number cc-csc")
    assert _asks(click_gate.consent_verdict(pay)), "allowing bookings does not allow money to move"
    assert click_gate.consent_verdict(None) is None and click_gate.decide(None)[0], \
        "a page nobody can read has no class to look up: it asks whatever his rules say"


# ── a spoken rule names ONE channel ──────────────────────────────────────────────────────────────────────
# V2-806: the sentence is understood once by `rules.shape` (scripted here); the row it writes is scoped to the
# channel it names, and a removal names the row by id.

def _shaped(monkeypatch, plan: dict, sentence: str) -> dict:
    import json
    from rules import shape
    monkeypatch.setattr(shape, "_chat", lambda system, user: json.dumps(plan))
    return shape.write(sentence)


@pytest.mark.parametrize("rule,channel", [
    ("no me pidas confirmación para mandar correos", "email"),
    ("don't ask for confirmation for whatsapps", "whatsapp"),
    ("no me pidas permiso para escribir al cluster", "meshkore"),
])
def test_a_scoped_spoken_rule_removes_confirmation_for_that_channel_only(monkeypatch, rule, channel):
    _drafts()
    consent.set_class("messaging.send_new", "ask")
    before = consent.ask_at()
    res = _shaped(monkeypatch, {"op": "add", "say": "ok", "rows": [
        {"scope": f"messaging/{channel}/send_new", "kind": "gate", "key": "consent", "value": "allow"}]}, rule)
    assert [r["scope"] for r in res["stored"]] == [f"messaging/{channel}/send_new"]
    assert consent.ask_at() == before, "a rule about one channel never moves the global knob"
    verdicts = {"email": _email(), "whatsapp": _whatsapp(), "meshkore": _cluster()}
    assert not _asks(verdicts.pop(channel)), f"{channel} no longer asks"
    assert all(_asks(v) for v in verdicts.values()), "every other channel keeps his rule"
    assert _asks(_booking())
    _shaped(monkeypatch, {"op": "remove", "remove": [res["stored"][0]["id"]], "say": "ok"}, "olvida esa regla")
    assert consent.class_policy(f"messaging.send_new@{channel}") == "ask", "retired: the bare class rules again"


def test_a_scoped_rule_that_adds_friction_keeps_its_reach(monkeypatch):
    _drafts()
    _shaped(monkeypatch, {"op": "add", "say": "ok", "rows": [
        {"scope": "messaging/whatsapp/send_new", "kind": "gate", "key": "consent", "value": "ask"}]},
            "pregúntame siempre antes de mandar un whatsapp")
    assert _asks(_whatsapp()) and not _asks(_email())


def test_a_send_he_ordered_reads_his_rule_even_when_its_manifest_runs_it_fast():
    from nucleo.flash import frontend
    from widgets import actions as wa
    payload = {"contact": "hospitality@example.com", "text": "Hola"}
    assert frontend.action_mode_now("mensajeria", "send_to", payload) == wa.FAST
    consent.set_class("messaging.send_new@email", "ask")
    assert frontend.action_mode_now("mensajeria", "send_to", payload) == wa.CONFIRM
    assert frontend.action_mode_now("mensajeria", "send_to", {"contact": "Rowan Pike", "text": "hi"}) == wa.FAST


# ── an errand sends under its mandate, and only there ────────────────────────────────────────────────────

def _errand(may=("message", "schedule"), channels=("telegram",)):
    return {"id": "e1", "objective": "organise a call with Rowan",
            "mandate": {"parties": ["c1"], "channels": list(channels), "may": list(may)}}


def _deliver(errand):
    from nucleo.errands import mandate
    sent, told = [], []
    ok = mandate.deliver(errand, "telegram", "987", "Six works for me.", "Rowan Pike",
                         lambda *a: sent.append(a) or True, told.append)
    return ok, sent, told


def test_a_mandate_covered_errand_reply_leaves_without_asking():
    ok, sent, told = _deliver(_errand())
    assert ok and len(sent) == 1 and not told


@pytest.mark.parametrize("errand", [_errand(may=("schedule",)), _errand(channels=("email",)), {"id": "e1"}])
def test_a_reply_the_mandate_does_not_cover_is_held_as_a_row_he_can_send(errand):
    from widgets.mensajeria import data, held
    ok, sent, told = _deliver(errand)
    assert not ok and not sent and told, "outside the mandate nothing leaves, and he is told"
    rows = held.held(data.load_db())
    assert [(r["to"], r["platform"], r["text"]) for r in rows] == [("Rowan Pike", "telegram", "Six works for me.")]
    out = data.apply_action("send_draft", {"contact": "Rowan Pike"})       # his «send it», voice, chat or card
    assert out["ok"] and data.load_db()["pending_send"][0]["chatId"] == "987"


def test_inside_the_mandate_his_rule_for_that_channel_still_stops_it():
    consent.set_class("messaging.send_new@telegram", "ask")
    ok, sent, told = _deliver(_errand())
    assert not ok and not sent and told
    consent.set_class("messaging.send_new@telegram", "never")
    from widgets.mensajeria import data
    data.apply_action("send_draft", {"contact": "Rowan Pike"})              # clear the held one
    ok, sent, told = _deliver(_errand())
    assert not ok and not sent and "prohíbe" in told[0]
    assert not data.load_db().get("drafts"), "a forbidden send is not held either"


# ── a cluster message: the gate is WIRED, and a yes from any channel resolves the same row ──────────────

class _Mgr:
    def __init__(self):
        self.sent = []

    def has(self, name):
        return name == "arena"

    def names(self):
        return ["arena"]

    def get(self, name):
        return None

    async def send(self, name, to=None, text=None, media=None, payload=None):
        self.sent.append((name, to, text))


def _bridge():
    from connectors.meshkore.bridge import ClusterBridge
    m = _Mgr()
    return ClusterBridge(m, brain=None), m


def test_a_cluster_message_goes_through_the_door_and_his_ask_rule_holds_it():
    b, m = _bridge()
    asyncio.run(b.dispatch("cluster.send", {"name": "arena", "data": {"text": "hello team"}}))
    assert m.sent == [("arena", None, "hello team")], "the default sends, as before"
    consent.set_class("messaging.send_new@meshkore", "ask")
    asyncio.run(b.dispatch("cluster.send", {"name": "arena", "data": {"text": "second line"}}))
    assert len(m.sent) == 1, "his rule for the cluster holds the message"
    from widgets import confirm as wc
    p = wc.pending()[wc.NATIVE_CLUSTERS]
    assert p["op"]["action"] == "cluster_send" and p["op"]["payload"]["text"] == "second line"
    assert wc._leaves(wc.NATIVE_CLUSTERS, p), "a held cluster send LEAVES: a long «ok …» is not its yes"


@pytest.mark.parametrize("channel", ["voice_or_chat", "clusters_tab"])
def test_a_yes_resolves_the_same_cluster_row_whatever_channel_it_came_from(channel, monkeypatch):
    from connectors import meshkore
    from connectors.meshkore import send_gate
    b, m = _bridge()
    monkeypatch.setattr(meshkore, "dispatch_tag", lambda tag, extra: b.dispatch(tag, extra))
    consent.set_class("messaging.send_new@meshkore", "ask")
    assert send_gate.gate("arena", None, "held line") == "held"
    if channel == "voice_or_chat":
        from voice.engine.llm.providers import nucleo as prov, pending_confirm
        monkeypatch.setattr(prov, "_spawn", lambda coro, name: asyncio.run(coro))
        assert pending_confirm._resolve_pending_confirm(True)
    else:
        from connectors.meshkore import server_api
        asyncio.run(server_api.confirm({"ok": True}))
    assert m.sent == [("arena", None, "held line")], "his yes sends exactly the held row, past the door it passed"
    from widgets import confirm as wc
    assert not wc.pending()


def test_the_agenda_invitation_is_decided_once_at_the_door_and_published_after():
    """Kept as a FOLLOW-UP, not a second gate: `invite.run` executes what the door already decided through the
    agenda's `consent_scope` — it never asks consent itself (its own refusals are a missing fact or a doubt)."""
    import inspect

    from widgets.agenda import invite
    src = inspect.getsource(invite.run) + inspect.getsource(invite._mail_invitation)
    assert "consent" not in src and "confirm" not in src
    from nucleo.flash import frontend
    assert frontend._policy_key("agenda", "invite", {"consent_class": "calendar.invite_new_party"},
                                {"who": "stranger@example.com"}) == "calendar.invite_new_party"


def test_a_workers_booking_click_asks_by_default_and_his_rule_decides_it():
    """The gate is WIRED where the worker's mouse goes (`click_gate.may_act`): the class decides, his rule wins."""
    from widgets.navegador import click_gate

    class _Handle:
        async def evaluate(self, js):
            return dict(BOOKING)
    asked = []

    async def _confirm(q):
        asked.append(q)
        return False

    def _click():
        return asyncio.run(click_gate.may_act(None, _Handle(), confirm=_confirm, task_id="t1"))
    ok, _why = _click()
    assert not ok and len(asked) == 1, "a booking submit asks by default, as it always did"
    consent.set_class("web.commit", "allow")
    assert _click() == (True, "") and len(asked) == 1, "his «no confirmation for bookings» lets it through"
    consent.set_class("web.commit", "never")
    ok, why = _click()
    assert not ok and len(asked) == 1 and "regla" in why, "his «never» refuses without asking"
