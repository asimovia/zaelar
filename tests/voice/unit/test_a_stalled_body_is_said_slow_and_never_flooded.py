"""The voice process is honest about a stopped body and never floods it (E0, node 3.203).

Measured 2026-11-12: with the body's loop stopped by the host, the voice process opened a connection per failed
batch (106 lost batches; the body's TCP backlog filled in 31 s and the turn found it «unreachable»), dropped his
transcripts, and told him «say that again?» for words it had heard perfectly. Now:
  (a) a body that cannot be reached is tried ONCE more a second later, then he hears «it's running slow» — never
      «say that again» — and his line rides with the next turn as `prior`, which the body reads as his words;
  (b) while the body does not answer, the sender opens at most one connection per `RETRY_GAP_S`;
  (c) his transcripts and the items are asked once more at the front of the queue, like a session's start/close.

Disarms (each seen red): `_slow_line` → `_say_again` in `remote_llm_node` → (a); drop `await self._pace()` → (b);
`RETRIED = ("session",)` → (c).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from voice.engine.pipeline import body_link, remote_brain


class _Down:
    def __init__(self, lines=None, fail_times: int = 99):
        self.lines, self.fail_times, self.calls, self.flushed = lines or [], fail_times, 0, 0

    async def flush(self, _max_s=0.2):
        self.flushed += 1
        return True

    async def stream(self, _p, payload):
        self.calls += 1
        self.payload = payload
        if self.calls <= self.fail_times:
            raise OSError("connection refused")
        for ln in self.lines:
            yield ln


@pytest.fixture
def lines(monkeypatch):
    monkeypatch.setattr(remote_brain, "RETRY_S", 0.01)
    monkeypatch.setitem(remote_brain._LOST, "text", "")
    monkeypatch.setattr(remote_brain, "_say_again", lambda: "REPEAT?")
    monkeypatch.setattr(remote_brain, "_slow_line", lambda: "SLOW")
    monkeypatch.setattr(remote_brain, "last_user_text", lambda ctx: ctx)
    return None


def _node(link, text):
    async def _run():
        return [x async for x in remote_brain.remote_llm_node(None, text, [], None)]
    return asyncio.run(_run())


def test_an_unreachable_body_is_tried_once_more_then_said_slow_and_his_line_kept(lines, monkeypatch):
    link = _Down()
    monkeypatch.setattr(body_link, "get", lambda: link)
    assert _node(link, "hola") == ["SLOW"]
    assert link.calls == 2, "one retry, never a storm"
    assert remote_brain._LOST["text"] == "hola"
    assert remote_brain.turn_payload("y qué tal")["prior"] == "hola", "his lost line rides with the next turn"
    assert "prior" not in remote_brain.turn_payload("hola"), "the same line is not said twice"


def test_a_body_back_on_the_second_try_answers_and_forgets_the_lost_line(lines, monkeypatch):
    link = _Down([{"t": "c", "text": "Cuatro."}, {"t": "end"}], fail_times=1)
    monkeypatch.setattr(body_link, "get", lambda: link)
    remote_brain._LOST["text"] = "hola"
    assert _node(link, "¿dos más dos?") == ["Cuatro."] and link.calls == 2
    assert remote_brain._LOST["text"] == ""


def test_a_turn_the_body_itself_failed_still_asks_him_again(lines, monkeypatch):
    link = _Down([{"t": "err", "msg": "boom"}], fail_times=0)
    monkeypatch.setattr(body_link, "get", lambda: link)
    assert _node(link, "hola") == ["REPEAT?"] and link.calls == 1


def test_the_body_reads_the_prior_line_as_his_words_before_the_turn(monkeypatch):
    from voice import remote_session

    class _Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def __aiter__(self):
            return self._gen()

        async def _gen(self):
            from livekit.agents.llm import ChatChunk, ChoiceDelta
            yield ChatChunk(id="x", delta=ChoiceDelta(role="assistant", content="Bien."))

    brain = SimpleNamespace(_window=[], chat=lambda *, chat_ctx, **k: _Stream())
    monkeypatch.setattr(remote_session, "_brain", lambda: brain)
    monkeypatch.setitem(remote_session._M, "client", None)
    from voice.engine.speech import filler_audio as fa
    monkeypatch.setattr(fa, "llm_node_with_filler", lambda _a, model, ctx, tools, ms: model(None, ctx, tools, ms))

    async def _run():
        return [ln async for ln in remote_session.turn_lines({"text": "y qué tal", "prior": "hola"})]
    out = asyncio.run(_run())
    assert "".join(ln["text"] for ln in out if ln["t"] == "c") == "Bien."
    assert brain._window and brain._window[-1]["role"] == "user" and brain._window[-1]["content"] == "hola"


class _FakeHttp:
    """An aiohttp session whose POST fails while `fail` is set: counts every connection attempt."""
    def __init__(self):
        self.fail, self.attempts, self.bodies = True, 0, []

    def post(self, url, data=None, headers=None, timeout=None):
        http = self

        class _Resp:
            status = 200

            async def __aenter__(self):
                http.attempts += 1
                if http.fail:
                    raise OSError("connection refused")
                http.bodies.append(data)
                return self

            async def __aexit__(self, *a):
                return False
        return _Resp()


def _link(monkeypatch, http):
    link = body_link.BodyLink(base="http://127.0.0.1:1", token="t", max_batch=1)
    monkeypatch.setattr(link, "_http", lambda: http)
    return link


def test_while_the_body_fails_the_sender_opens_one_connection_a_second(monkeypatch):
    """(b) three events queued against a body that does not answer: ONE attempt, then the gap — not three."""
    http = _FakeHttp()
    link = _link(monkeypatch, http)
    monkeypatch.setattr(body_link, "RETRY_GAP_S", 0.4)

    async def run():
        link.start()
        for ev in ({"k": "state", "state": "listening"}, {"k": "transcript", "text": "hola", "final": True},
                   {"k": "transcript", "text": "hola qué tal", "final": True}):
            link.send(ev)
        await asyncio.sleep(0.3)             # inside the gap: three batches queued, ONE connection opened
        during = http.attempts
        http.fail = False                    # the body answers again before the paced second try
        await asyncio.sleep(0.5)
        await link.aclose()
        return during
    during = asyncio.run(run())
    assert during == 1, f"one connection per gap while failing, not one per batch ({during})"
    assert link.stats["dropped"] == 1 and link.stats["sent"] == 2, link.stats
    assert all('"transcript"' in b for b in http.bodies), "his words reached the body once it answered"


def test_his_transcripts_and_the_items_are_asked_once_more_a_state_is_not(monkeypatch):
    """(c) the facts the body must not lose are retried at the front of the queue; a state is dropped and counted."""
    http = _FakeHttp()
    link = _link(monkeypatch, http)
    monkeypatch.setattr(body_link, "RETRY_GAP_S", 0.1)

    async def run():
        link.start()
        link.send({"k": "item", "role": "user", "text": "hola"})
        await asyncio.sleep(0.05)
        http.fail = False                   # the body answers again before the paced second try
        await asyncio.sleep(0.2)
        await link.aclose()
    asyncio.run(run())
    assert link.stats["sent"] == 1 and link.stats["dropped"] == 0 and http.attempts == 2
    assert '"_retried": true' in http.bodies[0]
