"""A cover that sounded is never heard twice (V2-864, CRIT-V4c).

V2-863 decides the cover before the model is paid and tells the model, unconditionally, which phrase is already
sounding. Measured on the operator's own voice session the day after: 4 of 7 covered replies opened with the very
words of the cover («Look…» → «Look, you're right…»), the note notwithstanding. A model echoes its lead-in; a
sentence in its prompt does not stop it. `EchoCut` does, deterministically and with zero tokens: the head of the
reply is held until it can be compared word for word with the cover (case, accents and punctuation are the
voice's), an echo is cut before TTS and transcript, and anything else — a reply that merely CONTINUES the cover —
passes untouched. These tests drive the real node wrapper with fake inner generators, like its siblings.
"""
from __future__ import annotations

import asyncio

import pytest
from livekit.agents import llm
from livekit.agents.types import FlushSentinel

from voice.engine.speech import filler_audio as fa


class _Brain:
    def __init__(self):
        self._last_reply = ""
        self._last_filler = ""
        self._last_spoken = ""
        self._last_spoke_at = 0.0


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fa._reset_for_tests()
    monkeypatch.delenv("ZAELAR_FILLER_MS", raising=False)
    monkeypatch.setattr("voice.proactive.user_speaking", lambda: False)
    monkeypatch.setattr("nucleo.style_policy.filler_allowed", lambda k: True)
    yield
    fa._reset_for_tests()


def _cut(phrase: str, *chunks: str) -> tuple[str, bool]:
    e = fa.EchoCut(phrase)
    out = "".join(e.feed(c) for c in chunks) + e.flush()
    return out, e.cut


# ── 1. the cut itself: word for word, however punctuated, and only the head ─────────────────────────────────

@pytest.mark.parametrize("phrase, chunks, want", [
    ("Look…", ["Look, you're right that it should"], "You're right that it should"),
    ("Yeah…", ["Yeah… you told me"], "You told me"),
    ("Got it…", ["Got", " it — I", " can see"], "I can see"),
    ("Un segundo…", ["Un segundo, miro la agenda"], "Miro la agenda"),
    ("Vale…", ["Vale."], ""),
])
def test_a_reply_that_opens_with_the_cover_loses_it(phrase, chunks, want):
    out, cut = _cut(phrase, *chunks)
    assert (out, cut) == (want, True)


@pytest.mark.parametrize("phrase, chunks", [
    ("So…", ["then I got that wrong"]),          # it CONTINUES the cover
    ("Look…", ["Looking at it now"]),            # a longer word is not the cover's word
])
def test_a_reply_that_only_continues_the_cover_passes_intact(phrase, chunks):
    out, cut = _cut(phrase, *chunks)
    assert (out, cut) == ("".join(chunks), False)


def test_the_decision_is_taken_once_per_turn():
    e = fa.EchoCut("Look…")
    assert e.feed("Look, you're ") == "You're "
    assert e.feed("Look, again") == "Look, again", "after the decision every chunk passes straight through"


# ── 2. end to end through the node ────────────────────────────────────────────────────────────────────────

def _chunk(text):
    return llm.ChatChunk(id="c", delta=llm.ChoiceDelta(role="assistant", content=text))


def _inner(first_after: float, chunks):
    async def impl(agent, chat_ctx, tools, model_settings):
        await asyncio.sleep(first_after)
        for c in chunks:
            yield c
    return impl


def _run(impl):
    async def go():
        return [c async for c in fa.llm_node_with_filler(None, impl, None, None, None)]
    return asyncio.run(go())


def _shape(out):
    shaped = []
    for c in out:
        if isinstance(c, FlushSentinel):
            shaped.append("FLUSH")
        elif isinstance(c, llm.ChatChunk):
            shaped.append(c.delta.content if c.delta else None)
        else:
            shaped.append(c)
    return shaped


@pytest.fixture
def _look(monkeypatch):
    monkeypatch.setattr("voice.engine.core.langs.pick_filler", lambda last, kind=None: "Look…")
    events = []
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: events.append((a, k)))
    return events


def _brain_labels(events):
    return [a[1] for a, _k in events if a and a[0] == "brain" and len(a) > 1]


def test_the_echo_is_cut_from_the_reply_and_noted_once(_look):
    assert fa.arm(_Brain(), "is that right?") == "Look…"
    out = _run(_inner(0.2, [_chunk("Look, "), _chunk("you're right "), _chunk("that it should.")]))
    assert _shape(out) == ["Look… ", "FLUSH", "You're right ", "that it should."]
    cuts = [lbl for lbl in _brain_labels(_look) if "eco de la cobertura" in lbl]
    assert len(cuts) == 1, _brain_labels(_look)


def test_without_a_cover_that_sounded_a_reply_opening_with_its_words_is_intact(_look):
    """The model answered before anything armed: no cover sounded, so there is nothing to cut."""
    out = _run(_inner(0.0, [_chunk("Look, "), _chunk("you're right.")]))
    assert _shape(out) == ["Look, ", "you're right."]
    assert not [lbl for lbl in _brain_labels(_look) if "eco de la cobertura" in lbl]


def test_an_engine_answering_fast_sounds_no_cover_and_cuts_nothing(_look):
    for _ in range(fa._FAST_WINDOW):
        fa.note_latency(500)
    assert fa.arm(_Brain(), "is that right?") == ""
    out = _run(_inner(0.2, [_chunk("Look, "), _chunk("you're right.")]))
    assert _shape(out) == ["Look, ", "you're right."]


def test_a_chunk_with_no_text_passes_untouched(_look):
    """A usage report or a tool call carries no `delta.content`: it is not held, not cut, not broken."""
    fa.arm(_Brain(), "is that right?")
    empty = llm.ChatChunk(id="u", delta=llm.ChoiceDelta(role="assistant", content=None))
    tool = llm.ChatChunk(id="t", delta=llm.ChoiceDelta(role="assistant", tool_calls=[
        llm.FunctionToolCall(name="agenda", arguments="{}", call_id="k1")]))
    out = _run(_inner(0.2, [empty, tool, _chunk("Look, "), _chunk("done.")]))
    assert out[2] is empty and out[3] is tool
    assert _shape(out)[4:] == ["Done."]


# ── 3. the note names the cover's first word, as it sounds ─────────────────────────────────────────────────

def test_the_note_names_the_covers_first_word_with_its_capital(monkeypatch):
    monkeypatch.setattr("voice.engine.core.langs.pick_filler", lambda last, kind=None: "Un segundo…")
    messages = [{"role": "user", "content": "¿qué tengo hoy?"}]
    assert fa.arm(_Brain(), "¿qué tengo hoy?", messages=messages) == "Un segundo…"
    note = messages[-1]["content"]
    assert "nunca por «Un»" in note and "ya suena" in note


# ── 4. disarm: a cut that never cuts must turn the end-to-end test red ─────────────────────────────────────

def test_disarm_a_cut_that_never_cuts_is_caught(monkeypatch, _look):
    class _Never(fa.EchoCut):
        def feed(self, text):
            return text

        def flush(self):
            return ""

    original = fa.EchoCut
    try:
        monkeypatch.setattr(fa, "EchoCut", _Never)
        assert fa.EchoCut is _Never, "the disarm landed"
        with pytest.raises(AssertionError):
            test_the_echo_is_cut_from_the_reply_and_noted_once(_look)
    finally:
        monkeypatch.setattr(fa, "EchoCut", original)
