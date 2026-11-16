"""The Brain Worker's optional Claude-subscription rung (`brain_worker.lead` in the model table, V2-913).

Claude itself, on a subscription's long-lived OAuth token, goes AHEAD of the titular — but only where its credential
resolves. Pinned here:

  · ORDER: subscription → titular → stand-in, even when the deployment configured the titular as its head;
  · THE GATE: no credential → the rung does not exist and the chain is exactly the old one; a `CLAUDE_CODE_OAUTH_TOKEN`
    left in someone's shell does not create it either (the rung reads its own variable);
  · THE ROUTE: direct, the CLI gets the token as its login (no base URL); behind mediated egress the process never
    holds it and presents its own credential to egress's family;
  · THE LIMITS: a 5-hour or weekly window, in the CLI's own wording, parks the rung until the reset it states and
    the chain relays to the titular;
  · THE ATTRIBUTION: every worker event names the tier that served it, by name, with the real model.

Disarm: drop `lead_name=` in `providers._known_from_table` → order cases red; drop the `tiers.sort` → the configured
head wins, red; drop the `hit your` branch of `_WINDOW_RE` → the limit is not a quota, no relay, red; drop `provider=`
from the `usage` event in `claude_map` → the attribution case red.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from nucleo.workers import providers as prov
from nucleo.workers.base import WorkerEvent
from nucleo.workers.providers.claude import ClaudeCodeSession   # the facade first: it binds claude_map
from nucleo.workers import session as S

SUB = prov.SUBSCRIPTION_TIER


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fresh = prov.CooldownStore(prov._KV)
    fresh._loaded = True
    monkeypatch.setattr(fresh, "_save", lambda: None)
    monkeypatch.setattr(prov, "_store", fresh)
    monkeypatch.setattr(prov, "_is_container", lambda: False)
    for var in {e for t in prov.KNOWN for e in t.get("env", ())} | {"CLAUDE_CODE_OAUTH_TOKEN"}:
        monkeypatch.delenv(var, raising=False)
    yield


def _cfg(monkeypatch, **over):
    import config.v2 as v2
    base = {"base_url": "https://api.z.ai/api/anthropic", "model": "glm-5.3"}
    base.update(over)
    monkeypatch.setattr(v2, "get", lambda k: base if k == "code_agent" else {})


def _keys(monkeypatch, sub=True):
    monkeypatch.setenv("Z_AI_API_KEY", "k-zai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k-ds")
    if sub:
        monkeypatch.setenv("CLAUDE_SUBSCRIPTION_OAUTH_TOKEN", "sk-ant-oat01-test")


# ── order and gate ────────────────────────────────────────────────────────────────────────────────────────────
def test_the_table_declares_the_rung_with_real_claude_models():
    lead = next(t for t in prov.KNOWN if t["name"] == SUB)
    assert lead["model"].startswith("claude-") and lead["fast_model"].startswith("claude-")
    assert lead["vision"] is True and lead["auth"] == "oauth"
    assert lead["env"] == ["CLAUDE_SUBSCRIPTION_OAUTH_TOKEN"]


def test_the_subscription_goes_first_even_ahead_of_the_configured_head(monkeypatch):
    _cfg(monkeypatch)
    _keys(monkeypatch)
    tiers = prov.chain()
    assert [t["name"] for t in tiers] == [SUB, "z.ai", "deepseek", "licencia-claude"]
    assert [t["model"] for t in tiers[:3]] == ["claude-sonnet-5-5", "glm-5.3", "deepseek-v4-pro"]
    assert prov.pick()["name"] == SUB and prov.relayed()


def test_without_its_credential_the_chain_is_exactly_the_old_one(monkeypatch):
    _cfg(monkeypatch)
    _keys(monkeypatch, sub=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "someone-elses-shell-login")
    assert [t["name"] for t in prov.chain()] == ["z.ai", "deepseek", "licencia-claude"]
    assert prov.pick()["name"] == "z.ai" and not prov.relayed()


# ── route ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_direct_the_token_is_the_clis_login_and_no_endpoint_is_redirected(monkeypatch):
    _cfg(monkeypatch)
    _keys(monkeypatch)
    env = prov.env_for_worker()
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-test"
    assert "ANTHROPIC_BASE_URL" not in env and "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "claude-sonnet-5-5"
    assert env["ANTHROPIC_SMALL_FAST_MODEL"] == "claude-sonnet-5-5", "the fast slot never falls to a default"
    assert "ZAELAR_NAV_VISION" not in env, "Claude reads images: the browser keeps its screenshots"


def _mediated(monkeypatch):
    from nucleo.energy import egress
    monkeypatch.setattr(egress, "mediated", lambda: True)
    monkeypatch.setenv("ZAELAR_GATEWAY_URL", "https://egress.test")
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "account-cred")


def test_behind_egress_the_process_presents_its_own_credential_never_a_token(monkeypatch):
    _mediated(monkeypatch)
    rung = {"name": SUB, "base_url": "https://egress.test/p/claude_subscription", "env": ["CONTROL_PLANE_SERVICE_TOKEN"],
            "model": "claude-sonnet-5-5", "fast_model": "claude-sonnet-5-5", "vision": True}
    _cfg(monkeypatch, providers=[rung, {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic",
                                        "env": ["Z_AI_API_KEY"], "model": "glm-5.3"}])
    monkeypatch.setenv("Z_AI_API_KEY", "account-cred")             # the stand-in, as egress leaves it
    env = prov.env_for_worker()
    assert env["ANTHROPIC_BASE_URL"] == "https://egress.test/p/claude_subscription"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "account-cred"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env


def test_behind_egress_the_providers_own_base_routes_to_the_subscription_family(monkeypatch):
    from nucleo.energy import egress
    _mediated(monkeypatch)
    assert egress.route_url("https://api.anthropic.com/v1/messages", "x") == (
        "https://egress.test/p/claude_subscription/v1/messages", "account-cred")
    assert egress.provider_of("https://api.anthropic.com") == "anthropic"


# ── limits ────────────────────────────────────────────────────────────────────────────────────────────────────
NOW = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc).timestamp()


@pytest.mark.parametrize("text,expected", [
    ("You've hit your limit · resets 3pm (UTC)", datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)),
    ("5-hour limit reached ∙ resets 9:30am (UTC)", datetime(2026, 11, 17, 9, 30, tzinfo=timezone.utc)),
    ("You've hit your weekly limit · resets Nov 20, 3pm (UTC)", datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)),
    ("Claude AI usage limit reached|1794790200", datetime.fromtimestamp(1794790200, tz=timezone.utc)),
])
def test_the_reset_is_read_in_the_clis_own_wording(text, expected):
    from nucleo.workers.providers import health
    assert prov.classify_failure(text) == "exhausted", text
    assert health._claude_reset_epoch(text, now=NOW) == expected.timestamp()


def test_a_spent_window_parks_the_rung_until_its_reset_and_relays_to_the_titular(monkeypatch):
    _cfg(monkeypatch)
    _keys(monkeypatch)
    sub = prov.pick()
    assert sub["name"] == SUB
    reset = time.strftime("%b %-d, %-I%p", time.localtime(time.time() + 3 * 86400)).replace("AM", "am").replace(
        "PM", "pm")
    cause = prov.note_failure(f"You've hit your weekly limit · resets {reset}", sub)
    assert cause["kind"] == "exhausted" and cause["provider"] == SUB and cause["next"] == "z.ai"
    assert prov.pick()["name"] == "z.ai"
    assert prov._store.until(SUB) > time.time() + 2 * 86400, "parked until the stated reset, not 30 min"


# ── attribution ───────────────────────────────────────────────────────────────────────────────────────────────
def test_every_worker_event_names_the_tier_and_the_real_model(monkeypatch):
    rows = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None: rows.append(
        (kind, dict(extra or {}))))
    cc = object.__new__(ClaudeCodeSession)
    cc._model, cc._task_id = "claude-sonnet-5-5", "7"
    cc._tier = {"name": SUB, "base_url": "https://egress.test/p/claude_subscription"}
    cc._steps_by_id, cc._last_step, cc._ctx_tokens = {}, {}, 0
    msg = {"type": "assistant", "message": {"id": "m1", "model": "claude-sonnet-5-5", "stop_reason": "end_turn",
                                            "usage": {"input_tokens": 9, "output_tokens": 3},
                                            "content": [{"type": "text", "text": "done"}]}}
    evs = list(cc._map(msg)) + list(cc._map({"type": "result", "subtype": "success", "result": "ok", "usage": {}}))
    by = {e.type: e.data for e in evs}
    assert by["usage"]["provider"] == SUB and by["usage"]["real_model"] == "claude-sonnet-5-5"
    assert by["result"]["provider"] == SUB
    assert by["model_call"]["turn"]["provider"] == SUB

    s = S.WorkerSession.__new__(S.WorkerSession)
    s._rec = S.SessionRecord(task_id="7", goal="g", kind="web")
    s._usage_partial, s._model, s._base_url, s._provider, s._ctx_warned = {}, "", "", "", True
    s._first_output_at, s._started_at = 1.0, 0.0
    s._spin, s._spin_dead, s._perm_hits = {}, False, 0
    s._emit_chip = s._touch = s._bus = (lambda *a, **k: None)
    for e in evs:
        if e.type in ("usage", "model_call", "result"):
            s._on_event(WorkerEvent(task_id="7", type=e.type, data=e.data))
    assert s._provider == SUB
    call = next(x for k, x in rows if k == "model_call")
    assert call["provider"] == SUB and call["model"] == "claude-sonnet-5-5"


# ── a hand-configured tier on the same URL is NOT the subscription rung ───────────────────────────────────────
def test_a_hand_made_tier_on_the_same_url_keeps_its_key_and_its_endpoint(monkeypatch):
    """`code_agent.providers` naming api.anthropic.com with an API key: no oauth, no inherited fast slot."""
    _cfg(monkeypatch, providers=[{"name": "mine", "base_url": "https://api.anthropic.com", "env": ["MY_ANTHROPIC_KEY"],
                                  "model": "claude-opus-5-5"}])
    monkeypatch.setenv("MY_ANTHROPIC_KEY", "sk-ant-api-test")
    env = prov.env_for_worker()
    assert env["ANTHROPIC_BASE_URL"] == "https://api.anthropic.com" and env["ANTHROPIC_AUTH_TOKEN"] == "sk-ant-api-test"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env and "ANTHROPIC_SMALL_FAST_MODEL" not in env


def test_a_head_configured_on_that_url_stays_in_the_chain_without_the_subscription_token(monkeypatch):
    _cfg(monkeypatch, base_url="https://api.anthropic.com", model="claude-opus-5-5")
    _keys(monkeypatch, sub=False)
    assert [t["name"] for t in prov.chain()] == ["api.anthropic.com", "z.ai", "deepseek", "licencia-claude"]
    assert "auth" not in prov.chain()[0]
