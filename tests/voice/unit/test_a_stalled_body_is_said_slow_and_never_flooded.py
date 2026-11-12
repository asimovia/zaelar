"""The voice process is honest about a stopped body and never floods it (E0, node 3.203).

Measured 2026-11-12: with the body's loop stopped by the host, the voice process opened a connection per failed
batch (106 lost batches; the body's TCP backlog filled in 31 s and the turn found it «unreachable»), dropped his
transcripts, and told him «say that again?» for words it had heard perfectly. Now:
  (a) a body that cannot be reached is tried ONCE more a second later, then he hears «it's running slow» — never
      «say that again» — and his line rides with the next turn as `prior`, which the body reads as his words;
  (b) while the body does not answer, the sender opens at most one connection per `RETRY_GAP_S`;
  (c) his transcripts and the items are asked once more at the front of the queue, like a session's start/close;
  (d) the ORDER is the request's own: a turn (and the kickoff) TAKES the facts still queued before it and carries
      them, and the body replays them before it runs the turn. Until 2026-11-12 the turn waited 0.2 s for a sender
      that, after one failure, paces itself a full second: the body read the turn before the final transcript that
      came before it. A batch already in the sender's hands is waited for its own POST, and said when overtaken.

Disarms (each seen red): `"brain_slow"` → `"say_again"` in `remote_llm_node` → (a); drop `await self._pace()` → (b);
`RETRIED = ("session",)` → (c); `ahead = []` in `remote_llm_node`, `_pace()` after the batch left the queue, no
`handle_batch` in `turn_lines` → (d).
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from voice.engine.pipeline import body_link, remote_brain


class _Down:
    def __init__(self, lines=None, fail_times: int = 99, queued=()):
        self.lines, self.fail_times, self.calls = lines or [], fail_times, 0
        self.queued, self.returned = list(queued), []

    async def ahead(self):
        out, self.queued = self.queued, []
        return out

    def back(self, events):
        self.returned.append(list(events))
        self.queued = list(events) + self.queued

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
    monkeypatch.setattr(remote_brain, "_line", {"say_again": "REPEAT?", "brain_slow": "SLOW"}.get)
    monkeypatch.setattr(remote_brain, "last_user_text", lambda ctx: ctx)
    return None


def _node(link, text):
    async def _run():
        return [x async for x in remote_brain.remote_llm_node(None, text, [], None)]
    return asyncio.run(_run())


def test_an_unreachable_body_is_tried_once_more_then_said_slow_and_his_line_kept(lines, monkeypatch):
    final = {"k": "transcript", "text": "hola", "final": True}
    link = _Down(queued=[final])
    monkeypatch.setattr(body_link, "get", lambda: link)
    assert _node(link, "hola") == ["SLOW"]
    assert link.calls == 2, "one retry, never a storm"
    assert link.payload["events"] == [final] and link.returned == [[final], [final]] and link.queued == [final], \
        "the facts a turn carried and the body never read go back to the front of the line, each time"
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


# ── (d) the order is the request's own ──────────────────────────────────────────────────────────────────────────

_STOPPED = {"k": "user_state", "state": "listening"}
_FINAL = {"k": "transcript", "text": "pon música", "final": True}


def _turn_through(link, monkeypatch, text="pon música"):
    """One turn over a REAL link whose turn stream is captured: what the body would have read, and how long it took."""
    seen = {}

    async def stream(_path, payload):
        seen.update(payload)
        yield {"t": "c", "text": "Voy."}
        yield {"t": "end"}
    monkeypatch.setattr(link, "stream", stream)
    monkeypatch.setattr(body_link, "get", lambda: link)
    monkeypatch.setattr(remote_brain, "last_user_text", lambda ctx: ctx)

    async def turn():
        t0 = time.monotonic()
        out = [x async for x in remote_brain.remote_llm_node(None, text, [], None)]
        return out, time.monotonic() - t0
    return seen, turn


@pytest.mark.parametrize("body_fails_first", [True, False])
def test_the_turn_carries_the_facts_queued_before_it_whatever_the_sender_waits_for(monkeypatch, body_fails_first):
    """(d) the measured inversion: one failed batch, the sender paces a whole gap, and the turn leaves inside it. The
    final transcript must reach the body BEFORE the turn — it rides with it. The variant with a healthy body: facts
    queued an instant before the turn (the sender has not run yet) ride the same way."""
    http = _FakeHttp()
    http.fail = body_fails_first
    link = _link(monkeypatch, http)
    link.max_batch = 256
    monkeypatch.setattr(body_link, "RETRY_GAP_S", 30.0)     # the sender's own wait: far longer than any turn would wait
    seen, turn = _turn_through(link, monkeypatch)

    async def run():
        link.start()
        link.send(_STOPPED)
        link.send(_FINAL)
        if body_fails_first:
            await asyncio.sleep(0.02)                       # that batch fails: his transcript is back at the front
            assert http.attempts == 1 and link._fail_streak == 1, "and from here the sender is pacing"
        out, took = await turn()
        await link.aclose()
        return out, took
    out, took = asyncio.run(run())
    assert out == ["Voy."] and took < 5.0, f"the turn waited on the sender's pace ({took:.1f} s)"
    carried = [(e["k"], e.get("text", e.get("state"))) for e in seen["events"]]
    assert carried[-1] == ("transcript", "pon música"), f"the body would read the turn before his final words: {seen}"
    assert body_fails_first or carried[0] == ("user_state", "listening"), "in the order they were queued"
    assert not link._q and not http.bodies and not link.stats["overtaken"], "carried once, never sent a second time"


def test_a_batch_in_the_senders_hands_is_waited_for_and_said_when_overtaken(monkeypatch):
    """(d) the wait that remains is the sender's own POST: a batch in flight comes back (its retried facts at the
    front) before the request takes the line; one that never comes back is overtaken — counted, and the rest rides."""
    gate = {"open": None, "attempts": 0}

    class _Hung:
        def post(self, url, data=None, headers=None, timeout=None):
            class _Resp:
                async def __aenter__(self):
                    gate["attempts"] += 1
                    await gate["open"].wait()
                    raise OSError("reset")

                async def __aexit__(self, *a):
                    return False
            return _Resp()
    monkeypatch.setattr(body_link, "RETRY_GAP_S", 30.0)

    def _hung_link():
        link = body_link.BodyLink(base="http://127.0.0.1:1", token="t", timeout_s=0.05)
        monkeypatch.setattr(link, "_http", lambda: _Hung())
        return link

    async def run(link, release: bool):
        gate["open"], gate["attempts"] = asyncio.Event(), 0
        link.start()
        link.send(_FINAL)
        await asyncio.sleep(0.01)
        assert gate["attempts"] == 1 and link._flying, "the batch is in the sender's hands"
        link.send(_STOPPED)
        waiting = asyncio.create_task(link.ahead())
        await asyncio.sleep(0.02)
        assert not waiting.done(), "the request waits for the batch in flight — inside the POST's own time"
        if release:
            gate["open"].set()                              # the POST fails: his transcript goes back to the front
        got = await waiting                                 # not released: 2 × timeout_s later it goes without it
        await link.aclose()
        return got
    back_first, hung = _hung_link(), _hung_link()
    came_back = asyncio.run(run(back_first, True))
    assert [e["k"] for e in came_back] == ["transcript", "user_state"] and came_back[0].get("_retried"), came_back
    assert back_first.stats["overtaken"] == 0
    overtook = asyncio.run(run(hung, False))
    assert [e["k"] for e in overtook] == ["user_state"] and hung.stats["overtaken"] == 1, (overtook, hung.stats)


def test_facts_a_request_could_not_deliver_return_to_the_front_in_order(monkeypatch):
    http = _FakeHttp()
    http.fail = False
    link = _link(monkeypatch, http)
    link.max_batch = 256

    async def run():
        link.start()
        link.send(_STOPPED)
        link.send(_FINAL)
        taken = await link.ahead()
        link.send({"k": "state", "state": "thinking"})
        link.back(taken)
        await asyncio.sleep(0.05)
        await link.aclose()
    asyncio.run(run())
    order = [e["k"] for b in http.bodies for e in __import__("json").loads(b)["events"]]
    assert order == ["user_state", "transcript", "state"], order


def test_the_body_replays_the_carried_facts_before_the_turn_and_before_the_kickoff(monkeypatch):
    """(d) the body's half: `events` on a turn (or on the kickoff question) go through the SAME replay, first."""
    from voice import remote_session
    from voice.engine.pipeline import first_air
    order = []
    monkeypatch.setattr(remote_session, "handle", lambda ev: order.append(ev["k"]))

    def _chat(*, chat_ctx, **k):
        order.append("turn")
        raise RuntimeError("stop here")
    monkeypatch.setattr(remote_session, "_brain", lambda: SimpleNamespace(_window=[], chat=_chat))
    monkeypatch.setitem(remote_session._M, "client", None)
    from voice.engine.speech import filler_audio as fa
    monkeypatch.setattr(fa, "llm_node_with_filler", lambda _a, model, ctx, tools, ms: model(None, ctx, tools, ms))

    async def _run():
        return [ln async for ln in remote_session.turn_lines({"text": "pon música", "events": [_STOPPED, _FINAL]})]
    asyncio.run(_run())
    assert order == ["user_state", "transcript", "turn"], order
    order.clear()
    monkeypatch.setattr(first_air, "decide_kickoff", lambda room, emit: order.append("kickoff") or "greet")
    assert remote_session.kickoff("r1", [{"k": "session", "what": "started"}])["greet"] == "greet"
    assert order == ["session", "kickoff"], order
    assert remote_session.kickoff("r1")["greet"] == "greet", "a question that carries nothing still decides"


def test_no_request_waits_on_a_clock_for_the_order():
    """The class: nothing in the voice process orders a request by waiting some seconds for the sender."""
    import inspect
    from voice.engine.pipeline import child_session
    assert not hasattr(body_link.BodyLink, "flush")
    for mod, call in ((remote_brain, "link.ahead()"), (child_session, "link.ahead()")):
        assert call in inspect.getsource(mod) and '"events": ahead' in inspect.getsource(mod), mod.__name__
