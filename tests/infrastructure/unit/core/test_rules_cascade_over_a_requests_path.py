"""V2-806 F1 — every standing rule is a row of ONE scoped table, read by a cascade over the request's path.

The class: six stores each answered «does his rule cover this?» their own way — a consent class with a hand-rolled
`@channel` fallback, a style file, a flat list of sentences in the memory state, a widget's own `prefs`. Here the
same request is resolved five ways (defaults only, a user rule, an exception, a narrower rule, an expired `until`)
and the rails are shown to sit outside the table.

Generic by construction: the rows name declared classes and widgets (email, WhatsApp, Telegram, a booking, the
agenda), never a phrase.
"""
from __future__ import annotations

import json
import time

import pytest

import rules
from nucleo import consent


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    consent._reset_for_tests()
    yield
    consent._reset_for_tests()


def _send(channel: str, **kw) -> list:
    return rules.path(cls="messaging.send_new", channel=channel, widget="mensajeria", action="send_draft", **kw)


def _verdict(channel: str, **kw) -> str:
    return consent.decide(level="sensitive", policy_key=f"messaging.send_new@{channel}",
                          scope={"widget": "mensajeria", "action": "send_draft", **kw})["verdict"]


# ── the same request, five ways ──────────────────────────────────────────────────────────────────────────

def test_with_defaults_only_the_genesis_rows_decide():
    assert rules.gate(_send("email")) == "allow"
    assert rules.deciding_rule(_send("email"))["source"] == "default"
    assert rules.gate(rules.path(cls="messaging.autorespond", channel="whatsapp")) == "never"
    assert rules.gate(rules.path(cls="web.commit")) == "ask"
    assert _verdict("email") == consent.RUN


def test_a_user_rule_overrides_the_default_at_its_scope():
    rules.add("messaging/email/send_new", "gate", "consent", "ask", text="pregúntame antes de mandar correos")
    assert rules.gate(_send("email")) == "ask"
    assert rules.deciding_rule(_send("email"))["source"] == "user"
    assert _verdict("email") == consent.ASK_CONSENT


def test_an_exception_is_a_narrower_scope_the_row_does_not_cover():
    rules.add("messaging/*/send_new", "gate", "consent", "ask", except_=["messaging/telegram", "item:c7"],
              text="ask me before sending a message, except on Telegram and to c7")
    assert rules.gate(_send("email")) == "ask"
    assert rules.gate(_send("telegram")) == "allow", "excepted channel: the genesis default decides"
    assert rules.gate(_send("email", item="c7")) == "allow", "excepted item: the genesis default decides"
    assert _verdict("email") == consent.ASK_CONSENT and _verdict("telegram") == consent.RUN


def test_the_more_specific_row_runs_last_and_wins_whatever_its_age():
    rules.add("messaging/email/send_new", "gate", "consent", "allow")
    time.sleep(0.01)
    rules.add("messaging/*/send_new", "gate", "consent", "ask")         # newer, but broader
    assert rules.gate(_send("email")) == "allow"
    assert rules.gate(_send("whatsapp")) == "ask"
    rules.add("widget:mensajeria/send_draft", "gate", "consent", "never")
    assert rules.gate(_send("email")) == "never", "an action anchor (level 4) beats a channel one"
    rules.add("item:c3", "gate", "consent", "allow")
    assert rules.gate(_send("email", item="c3")) == "allow", "an item is the narrowest scope there is"
    time.sleep(0.01)
    rules.add("messaging/email", "gate", "consent", "never")             # newest of all, at the channel level
    assert rules.gate(_send("email", item="c3")) == "allow", "a newer BROADER row never beats a narrower one"
    assert rules.gate(rules.path(cls="messaging.reply", channel="email")) == "never"


def test_an_expired_until_is_read_as_absent_by_the_clock():
    rules.add("messaging/email/send_new", "gate", "consent", "ask", until=time.time() - 1, text="hoy pregúntame")
    assert rules.gate(_send("email")) == "allow", "past its until: the default is back, nothing swept it"
    rules.add("messaging/email/send_new", "gate", "consent", "never", until=time.time() + 3600)
    assert rules.gate(_send("email")) == "never"
    assert rules.gate(_send("email"), now=time.time() + 7200) == "allow"


def test_at_the_same_level_his_row_beats_the_default_and_a_default_cannot_be_deleted(monkeypatch):
    rules.add("messaging/*/autorespond", "gate", "consent", "allow")
    assert rules.gate(rules.path(cls="messaging.autorespond")) == "allow"
    from rules import defaults
    shipped_later = [dict(r, created_at=time.time() + 3600) for r in defaults.rows()]
    monkeypatch.setattr(defaults, "rows", lambda: [dict(r) for r in shipped_later])
    assert rules.gate(rules.path(cls="messaging.autorespond")) == "allow", "a genesis newer than his row still loses"
    dflt = "default:consent@messaging/*/autorespond"
    assert rules.get(dflt)["source"] == "default"
    assert rules.remove(dflt) is None, "a factory row is overridden, never deleted"
    edited = rules.set_value(dflt, "ask")
    assert edited["source"] == "user" and rules.gate(rules.path(cls="messaging.autorespond")) == "ask"
    assert rules.get(dflt)["value"] == "never", "the factory row stays as shipped"


# ── one channel's rule stays in that channel ─────────────────────────────────────────────────────────────

def test_a_user_rule_for_email_does_not_touch_whatsapp_nor_an_unknown_channel():
    consent.set_class("messaging.send_new@email", "never")
    assert consent.class_policy("messaging.send_new@email") == "never"
    assert consent.class_policy("messaging.send_new@whatsapp") == "allow"
    assert consent.class_policy("messaging.send_new") == "allow", "a send whose channel nobody named"
    assert consent.decide_act("messaging.send_new", channel="whatsapp", level="standard")["verdict"] == consent.RUN


# ── the rails are not rules ──────────────────────────────────────────────────────────────────────────────

def test_no_row_disables_a_rail():
    for sc in ("global", "messaging", "messaging/*/send_new", "widget:mensajeria", "widget:mensajeria/send_draft"):
        rules.add(sc, "gate", "consent", "allow", text="never ask me anything")
    rules.add("global", "gate", "ask_at", "critical")
    kw = {"level": "standard", "policy_key": "messaging.send_new@email",
          "scope": {"widget": "mensajeria", "action": "send_draft"}}
    assert consent.decide(**kw)["verdict"] == consent.RUN
    assert consent.decide(**kw, missing=["operator.email"])["verdict"] == consent.ASK_FACT
    assert consent.decide(**kw, candidates=["Ana Ruiz", "Ana Gil"])["verdict"] == consent.ASK_WHICH
    assert consent.decide(**kw, bounded=False)["verdict"] == consent.ASK_CONSENT
    assert consent.decide(**kw, radius=40)["verdict"] == consent.ASK_CONSENT


# ── the legacy override file is imported once ────────────────────────────────────────────────────────────

def test_the_legacy_consent_file_is_migrated_once_and_idempotently(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "consent.json").write_text(json.dumps(
        {"ask_at": "sensitive", "classes": {"messaging.send_new@telegram": "ask", "web.commit": "allow"},
         "_set_at": 1_700_000_000}), encoding="utf-8")
    assert consent.class_policy("messaging.send_new@telegram") == "ask"
    assert consent.class_policy("web.commit") == "allow"
    assert consent.ask_at() == "sensitive"
    first = sorted(r["id"] for r in rules.all_rows(include_defaults=False))
    assert len(first) == 3 and all(r["origin"].startswith("consent.json:") for r in rules.all_rows(include_defaults=False))
    from rules import store
    store._conn().execute("DELETE FROM rules_meta")
    store._done.clear()
    consent.class_policy("web.commit")
    assert sorted(r["id"] for r in rules.all_rows(include_defaults=False)) == first, "a re-run inserts nothing"
    rules.remove("m_consent_web.commit")
    store._done.clear()
    assert consent.class_policy("web.commit") == "ask", "a row he deleted does not come back from the old file"
