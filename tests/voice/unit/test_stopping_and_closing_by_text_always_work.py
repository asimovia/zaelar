"""Stopping and closing by TEXT always work — the pieces that outlive the old turn (CRIT-V22).

Measured on his desktop, build 139: «para» typed over a story did not cut the voice. A typed line now enters the
conversation manager's inbox; in the voice's own process the body's `/voice/reply` with `cut` interrupts the speech in
course on the session loop and then queues the reply, in one request, even when the cut itself fails. What a stop
ends is what each app DECLARES running (`state.report.<field>.stop`), validated when the manifest loads.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


class _Speech:
    def __init__(self, *, done=False, interruptible=True, boom=False):
        self.interrupted, self.allow_interruptions, self._done, self._boom = False, interruptible, done, boom

    def done(self):
        return self._done

    def interrupt(self):
        if self._boom:
            raise RuntimeError("speech handle gone")
        self.interrupted = True


class _Session:
    """The live AgentSession's slice the typed door uses."""
    def __init__(self, log, speech=None):
        self.current_speech, self.log = speech if speech is not None else _Speech(), log

    def generate_reply(self, user_input="", **kw):
        self.log.append(("reply", user_input, bool(self.current_speech and self.current_speech.interrupted), kw))


@pytest.mark.parametrize("speech", [_Speech(), _Speech(boom=True)])
def test_the_voice_process_cuts_then_queues_in_one_request(monkeypatch, speech):
    """`/voice/reply` with `cut`: the speech in course is interrupted on the session loop, then the reply queued — even
    when the cut itself fails."""
    from voice.engine.pipeline import body_link, child
    log: list = []
    live = _Session(log, speech)
    monkeypatch.setenv(body_link.TOKEN_ENV, "tok")
    monkeypatch.setitem(child.LIVE, "session", live)

    async def _run():
        monkeypatch.setitem(child.LIVE, "loop", asyncio.get_running_loop())

        async def _json():
            return {"text": "para", "cut": True}
        await child.reply(SimpleNamespace(headers={body_link.HEADER: "tok"}, json=_json))
    asyncio.run(_run())
    assert log and log[-1][1] == "para" and live.current_speech.interrupted is not speech._boom


# ── every app that DECLARES a running state declares what a stop ends ──────────────────────────────────────────────
def _declared_stops():
    from widgets import runtime, state_decl
    return [(m["id"], f, st) for m in runtime.catalog()
            for f, spec in state_decl.report_fields(m.get("state") or {}).items() if (st := state_decl.stop_of(spec))]


def test_the_players_declare_what_a_stop_ends():
    assert {a for a, _f, _s in _declared_stops()} >= {"youtube", "musica"}


@pytest.mark.parametrize("stop", [{"act": "no_such_act", "when": True}, {"act": "pause", "when": "yes"}, {"when": True}])
def test_a_stop_that_names_no_act_of_the_app_or_a_value_of_another_type_is_refused(stop):
    from widgets import state_decl
    man = {"id": "x", "actions": {"pause": {}},
           "state": {"order": {"p": "p"}, "report": {"playing": {"type": "bool", "follows": "p", "stop": stop}}}}
    assert "stop is" in (state_decl.problem(man) or "")
    man["state"]["report"]["playing"]["stop"] = {"act": "pause", "when": True}
    assert state_decl.problem(man) is None
