"""The guards and the stop stand in front of the ear (node 13.91, V2-941, v3.1 §1.7, B10).

  · at the end of one of his turns the guards judge its words: a closed microphone, our own line heard back within the
    echo window, a turn the attention mode says was not said to us — each is a `Discard` handed to the ear BEFORE the
    end, with its text and reason, so it never closes as his words;
  · his stop, typed or spoken, is his words: nothing on the manager's path reads it (the model chooses a stop order,
    plan v3.2 §3, node 13.120); a button's stop is a `user.control` from the producer of its door;
  · his phrase the browser's own ear caught enters as VOICE, an entry of its own (`LocalPhrase`), and is answered;
  · a batch on the body link keeps a share of its room for the other events, however long the ear's lane is;
  · switched off, the conversation this process opened is retired when its voice session closes — no restart.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from conversation.ear import signals as S
from nucleo.conversation_host import controls, ear_in, entry, guards


@pytest.fixture
def ear(monkeypatch):
    from voice import attention, mic_input
    state = {"mic": False, "directed": True}
    monkeypatch.setattr(mic_input, "blocks_turn", lambda text: state["mic"])
    monkeypatch.setattr(attention, "evaluate",
                        lambda text, now=None: SimpleNamespace(directed=state["directed"], reason="active_window"))
    monkeypatch.setattr(attention, "note_ambient", lambda text, now=None: None)
    monkeypatch.setattr(attention, "note_directed", lambda now=None: None)
    monkeypatch.setattr(attention, "is_shut_up", lambda text: "w_stop" in text)
    guards._lines.clear()
    ear_in._reset_for_tests()
    yield state
    ear_in._reset_for_tests()
    guards._lines.clear()


def test_each_guard_names_why(ear):
    assert guards.judge("w1 w2") is None
    ear["mic"] = True
    assert guards.judge("w1 w2") == "mic_blocked"
    ear["mic"] = False
    guards.said("w5 w6 w7 w8", at=1000.0)
    assert guards.judge("w5 w6 w7 w8", now=1005.0) == "echo"                  # while our line sounds
    guards.ended(at=1010.0)
    assert guards.judge("w5 w6 w7 w8", now=1100.0) is None                    # past the echo window: his
    ear["directed"] = False
    assert guards.judge("w1 w2", now=1100.0) == "not_addressed"


def _turn(stream="holder", words=("w1", "w2"), seq0=1):
    return [{"t": "words", "stream": stream, "turn": 0, "rev": 1, "final": True,
             "words": [[w, 100, 200, 0.9] for w in words], "window": [0, 300], "boot": "b", "seq": seq0},
            {"t": "eot", "stream": stream, "kind": "end", "prob": .9, "t_ms": 300, "terminal": True, "boot": "b",
             "seq": seq0 + 1}]


def test_the_ear_asks_the_guards_at_every_close(ear, store):
    """At the provider's end AND at the cap (no final word, too long, a stall): what the guards throw away is a discard
    with its text and reason (I4), never an entry (the audit of B7l–B10, minor 1)."""
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply
    from tests.conversation.unit.convkit import Harness
    h = Harness(store, grace=False)
    h.conv.ear.guard = guards.for_ear
    h.model.default = lambda ids: [reply("w9"), Done()]
    ear["mic"] = True
    h.utter([(["w1", "w2"], 0)])                                            # closed by the provider's end
    h.hear(S.VadEdge("d1", "rise", 5000), S.WordSpan("d1", 9, 1, False, (("w3", 5000, 5200, 0.9),), (5000, 5200)))
    h.settle(h.conv.cfg.close_cap_ms + h.conv.cfg.intervention_max_ms)     # no final word: closed by the cap
    found = [(p["reason"], p["text"]) for k, lab, p in h.tel.events if k == "conv_ear" and lab == "discarded"]
    assert ("mic_blocked", "w1 w2") in found and ("mic_blocked", "w3") in found and h.mouth.orders == []
    ear["mic"] = False
    h.utter([(["w5", "w6"], h.clock.mono + 1000)])
    assert [o.text for o in h.mouth.orders] == ["w9"]


def test_his_spoken_stop_is_his_words_never_read_on_the_managers_path(ear, monkeypatch):
    """Plan v3.2 §3: no word of his is read to stop — «stop» spoken reaches the conversation as his words, and the
    model chooses a stop order (13.120). No control, no discard is made of it here."""
    calls = []
    monkeypatch.setattr(controls, "control", lambda op="stop", dev="", by="chat": calls.append((op, dev, by)))
    got = []
    for f in _turn(words=("w_stop",)):
        ear_in.receive(f, got.append)
    assert calls == [] and [type(s).__name__ for s in got] == ["WordSpan", "EotHint"]
    assert guards.for_ear("holder", "w_stop") is None


class _Conv:
    account = "acct"

    def __init__(self):
        self.log = []

    def give(self, env):
        self.log.append(("give", env.kind.value, env.producer, env.channel.value, env.body.op.value))

    def hear(self, sig):
        self.log.append(("hear", type(sig).__name__))


@pytest.fixture
def handed(monkeypatch):
    conv = _Conv()
    monkeypatch.setattr(entry, "_hand", lambda fn: fn(conv))
    return conv


def test_his_typed_stop_is_his_line_whole(ear, handed):
    entry.typed("w_stop w1", "text:s1", checked=True)
    assert handed.log == [("hear", "TypedSubmit")]


@pytest.mark.parametrize("by, producer, channel", [("ear", "ear:holder", "voice"), ("chat", "chat:holder", "text")])
def test_a_control_comes_from_the_producer_of_its_door(handed, by, producer, channel):
    controls.control("stop", "", by)
    assert handed.log == [("give", "user.control", producer, channel, "stop")]


def test_the_browsers_phrase_enters_as_voice_and_is_answered(store, handed):
    controls.local_phrase("w1 w2", "")
    assert handed.log == [("hear", "LocalPhrase")]
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply
    from tests.conversation.unit.convkit import Harness
    h = Harness(store)
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.hear(S.LocalPhrase("d1", "l1", "w1 w2", 10))
    h.settle(8000)
    assert [o.text for o in h.mouth.orders] == ["w9"]
    accepted = [p for k, lab, p in h.tel.events if k == "conv_inbox" and lab == "accepted"]
    assert accepted and accepted[0]["refs"]["channel"] == "voice"


def test_a_batch_keeps_room_for_the_other_events(monkeypatch):
    from voice.engine.pipeline import body_link
    link = body_link.BodyLink(base="http://127.0.0.1:1", token="t", max_batch=40)
    batches = []

    async def deliver(batch):
        batches.append(batch)
        return True
    monkeypatch.setattr(link, "_deliver", deliver)

    async def go():
        for i in range(200):
            link.send_ear({"t": "mark", "stream": "holder", "through": i})
        for i in range(5):
            link.send({"k": "session", "what": "w", "i": i})
        link.start()                                                           # all queued, then one wake
        link._kick()
        await asyncio.sleep(0.2)
        await link.aclose()
    asyncio.run(go())
    first = batches[0]
    assert sum(1 for ev in first if ev.get("k") == "session") == 5 and len(first) <= 40


def test_switched_off_the_conversation_is_retired_without_a_restart(monkeypatch):
    from nucleo.conversation_host import sessions, switch
    closed = []
    monkeypatch.setattr(sessions, "close_all", lambda: closed.append(1))
    monkeypatch.setitem(entry._opener, "rt", object())
    monkeypatch.setattr(switch, "decide", lambda session=None: switch.Decision(True, "account"))
    assert controls.retire_if_off() is False and closed == []                     # still on: kept
    monkeypatch.setattr(switch, "decide", lambda session=None: switch.Decision(False, "default"))
    assert controls.retire_if_off() is True and closed == [1] and entry._opener["rt"] is None


#: a long line of ours, its start and its end (seconds)
LINE, START, END = ("w1 w2 w3 w4 w5 w6 w7 w8 w9 wa wb wc wd we wf wg wh wi wj wk wl wm wn wo wp wq wr ws wt wu wv wx "
                    "wy wz"), 1000.0, 1020.0


def test_a_few_of_our_words_heard_back_while_our_line_sounds_are_an_echo(ear):
    """The voice pass: our TTS fed at −10/−20 dB, six words of a 654-char line heard back — a prefix is not similar to
    the whole line, so the old guard let them in as his words. Timing and containment decide it."""
    guards.said(LINE, at=START)
    assert guards.judge("w1 w2 w3 w4 w5 w6", now=START + 3, rose=START + 0.2) == "echo"
    assert guards.judge("w9 wa wb wc", now=START + 8, rose=START + 6) == "echo"           # a stretch in the middle
    assert guards.judge("wq w1 wz w0", now=START + 8, rose=START + 6) is None              # his own words, over it
    guards.ended(at=END)
    assert guards.judge("wx wy wz", now=END + 1.5, rose=END + 1) == "echo"                 # its tail, just after
    assert guards.judge("wx wy wz", now=END + 9, rose=END + 8) is None                     # later: his, repeated


def test_after_our_line_ended_only_its_tail_is_an_echo_and_quoting_its_middle_is_his(ear):
    """His live session: our line had ENDED, and 1.3 s later he said three words from its MIDDLE — him quoting us,
    read as our echo, deleted and never answered. After the end, only the tail of what sounded can echo."""
    guards.said("w1 w2 w3 w4 w5 w6 w7 w8 w9 wa wb wc wd we wf", at=START)
    guards.ended(at=START + 10, heard="w1 w2 w3 w4 w5 w6 w7 w8 w9 wa wb wc wd we wf")
    assert guards.judge("w6 w7 w8 wz", now=START + 11.5, rose=START + 11.3) is None       # its middle: his
    assert guards.judge("wd we wf", now=START + 11.5, rose=START + 11.3) == "echo"        # its tail: our echo


def test_his_answer_that_repeats_our_question_is_never_an_echo(ear):
    guards.said("w1 w2 w3 w4?", at=START)
    guards.ended(at=START + 2)
    assert guards.judge("w3 w4", now=START + 3, rose=START + 2.5) is None                 # «¿A Rowan?» «A Rowan.»


def test_the_echo_window_keeps_our_last_lines(ear):
    for n, at in ((1, 100.0), (2, 110.0), (3, 120.0)):
        guards.said(f"wl{n} wm{n} wn{n}", at=at)
        guards.ended(at=at + 5)
    assert guards.judge("wl2 wm2", now=118.0, rose=113.0) == "echo"                      # not only the last one


def test_the_turns_first_word_times_the_echo(ear):
    guards.said("w1 w2 w3", at=0.0)                                                       # rose at 100 ms: during it
    for f in _turn(words=("w1", "w2", "w3")):
        ear_in.receive(f, lambda s: None)
    assert ear_in.rose_of("holder") == 100 and guards.for_ear("holder", "w1 w2 w3") == "echo"


def test_an_echo_never_cuts_our_line_and_his_own_words_do():
    from voice.engine.pipeline import ear_tap
    for heard, cut_expected in ((("w5", "w6", "w7"), False), (("wq", "wr", "w0"), True), ((), False)):
        tap = ear_tap.Tap("holder", lambda f: None)
        cuts = []
        tap.on_barge, tap.min_barge_ms, tap.line = (lambda: cuts.append(1)), 500, "w1 w2 w3 w4 w5 w6 w7 w8"
        tap.playback(True, now_ms=0)
        tap.heard = heard
        for t in range(1000, 1000 + ear_tap.WORDLESS_BARGE_MS + 300, 30):
            tap.edges.frame(True, t)
        assert bool(cuts) is cut_expected, heard



@pytest.fixture
def real_attention(monkeypatch):
    """The REAL attention module, in smart mode, its state restored after."""
    import copy
    from voice import attention, mic_input
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    monkeypatch.delenv("ZAELAR_ATTENTION_WINDOW", raising=False)
    monkeypatch.setattr(mic_input, "blocks_turn", lambda text: False)
    saved = copy.deepcopy(attention._state)
    attention._wipe_window()
    attention.set_assistant_name("Wzael")
    guards._lines.clear()
    ear_in._reset_for_tests()
    yield attention
    attention._state.clear()
    attention._state.update(saved)
    ear_in._reset_for_tests()
    guards._lines.clear()


def test_his_follow_up_after_our_reply_is_heard_with_the_real_attention(real_attention):
    """TK-1: in the body the attention window ran from one turn's end to the next — model latency and our whole reply
    inside it — so «¿y mañana?» 1 s after a 3 s reply was `not_addressed`. The body now hears what the voice process
    hears (his rises and falls, our playback), so the window measures his silence from the end of our reply."""
    import time
    base = time.time() - 7.0
    assert guards.judge("Wzael w1 w2", now=base + 1.0) is None                    # addressed by name: the window opens
    facts = [{"t": "playback", "stream": "holder", "speaking": True, "t_ms": int((base + 2.0) * 1000)},
             {"t": "playback", "stream": "holder", "speaking": False, "t_ms": int((base + 5.0) * 1000)},
             {"t": "vad", "stream": "holder", "edge": "rise", "t_ms": int((base + 6.0) * 1000), "echo_safe": True},
             {"t": "words", "stream": "holder", "turn": 0, "rev": 1, "final": True, "window": [0, 1],
              "words": [["w3", int((base + 6.0) * 1000), int((base + 6.3) * 1000), 0.9],
                        ["w4", int((base + 6.3) * 1000), int((base + 6.5) * 1000), 0.9]]},
             {"t": "vad", "stream": "holder", "edge": "fall", "t_ms": int((base + 6.5) * 1000), "echo_safe": True},
             {"t": "eot", "stream": "holder", "kind": "end", "prob": .9, "t_ms": int((base + 6.8) * 1000),
              "terminal": True}]
    for n, f in enumerate(facts, start=1):
        ear_in.receive({**f, "boot": "b", "seq": n}, lambda s: None)
    assert guards.for_ear("holder", "w3 w4") is None                               # his: never `not_addressed`


def test_the_agents_name_and_how_it_is_heard_bias_the_provider(monkeypatch):
    """The voice pass: Flux wrote «Johnny» as «Jenny» and the wake word never woke. The name and every spelling it is
    heard as go to the provider as key terms (Flux and nova-3), first run included: a name biases no language."""
    from voice import attention
    from voice.engine.speech.stt import deepgram
    monkeypatch.setattr(attention, "wakewords", lambda: ("wzael", "wzail"))
    stops = [t for spec in deepgram.langs.supported() for t in spec.stop_keyterms]
    assert stops and deepgram._keyterms("flux-general-multi", True) == ["wzael", "wzail"] + stops   # his stop too
    assert deepgram._keyterms("flux-general-en", False)[:2] == ["wzael", "wzail"]
    assert deepgram._keyterms("nova-2", False) == []                         # a model that refuses key terms


def test_a_rise_with_our_lines_start_cuts_only_on_his_own_words():
    """Minor 2: a cut by a rise within `ECHO_ONSET_MS` of our line's start could never be given back (that rise is not
    sent again as his). Wordless there, it never cuts; with words of his that are not ours, it does."""
    from voice.engine.pipeline import ear_tap
    for heard, cut_expected in (((), False), (("wq", "wr", "w0"), True), (("w1", "w2", "w3"), False)):
        tap = ear_tap.Tap("holder", lambda f: None)
        cuts = []
        tap.on_barge, tap.min_barge_ms, tap.line = (lambda: cuts.append(1)), 500, "w1 w2 w3 w4"
        tap.playback(True, now_ms=0)
        tap.heard = heard
        for t in range(100, 100 + ear_tap.WORDLESS_BARGE_MS + 600, 30):
            tap.edges.frame(True, t)
        assert bool(cuts) is cut_expected, heard



def test_what_was_set_aside_comes_back_with_the_wake_word(real_attention, store):
    """Minor 4: «para la música» judged not addressed, then «Johnny» — the order goes to the model whole, in front of
    the entry that called him; consumed once."""
    import time
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply
    from tests.conversation.unit.convkit import Harness
    real_attention._state["last_directed"] = 0.0
    assert guards.judge("w1 w2", now=time.time()) == "not_addressed"            # set aside, kept in the tail
    h = Harness(store, grace=False)
    h.conv.ear.guard = guards.for_ear
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.utter([(["Wzael"], 0)])
    assert "w1 w2 Wzael" in h.model.calls[0].prompt.input and real_attention._state["ambient_tail"] == []


def test_a_spoken_stop_is_never_told_to_the_model_as_a_voice_it_lost(store):
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply
    from tests.conversation.unit.convkit import Harness
    h = Harness(store, grace=False)
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.hear(S.VadEdge("d1", "rise", 10), S.WordSpan("d1", 1, 1, False, (("w_stop", 10, 200, 1.0),), (10, 200)))
    h.hear(S.Discard("d1", "w_stop", "stop", 300))
    h.typed("w1 w2", 1000)
    h.settle(3000)
    state = h.model.calls[-1].prompt.state
    assert "VOICE LOST" not in state and "iv_000001" not in state


@pytest.mark.parametrize("latency_s, reply_s", [(6, 3), (12, 3), (6, 10), (12, 10)])
def test_his_follow_up_after_a_slow_reply_is_heard(real_attention, monkeypatch, latency_s, reply_s):
    """TK-1b: a reply that READ (the read budget is 12 s) began after the 5 s window had closed, so `note_bot_speech`
    held nothing and his next sentence without the name was `not_addressed`. Our answer re-anchors the window as it
    starts; its end re-anchors it again."""
    import asyncio
    import threading
    import time
    from types import SimpleNamespace
    from nucleo.conversation_host import voice_mouth
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    class _Client:
        _loop = loop

        def env_diff(self):
            return {}

        async def say_stream(self, payload):
            yield {"id": "x"}
            yield {"done": True, "spoken_chars": 2}
    monkeypatch.setattr(voice_mouth, "_live", lambda: _Client())
    now = time.time()
    assert guards.judge("Wzael w1 w2", now=now - latency_s) is None              # his turn, addressed by name
    try:
        assert voice_mouth.speak(SimpleNamespace(text="w9", say_id="s1", endpoint="holder", notice_key=None),
                                 lambda sig: None)
    finally:
        loop.call_soon_threadsafe(loop.stop)
    for n, (speaking, at) in enumerate(((True, now), (False, now + reply_s)), start=1):
        ear_in.receive({"t": "playback", "stream": "holder", "speaking": speaking, "t_ms": int(at * 1000),
                        "boot": "b", "seq": n}, lambda s: None)
    assert guards.judge("w3 w4", now=now + reply_s + 1) is None                  # his follow-up, a second after


def test_a_question_back_on_our_statement_is_his_never_an_echo(ear):
    guards.said("w1 w2 w3 w4 w5.", at=START)
    guards.ended(at=START + 3)
    assert guards.judge("¿w4 w5?", now=START + 4.5, rose=START + 4) is None    # «¿A las cinco?»
    assert guards.judge("w4 w5", now=START + 4.5, rose=START + 4) == "echo"    # our own tail, heard back


def _cut_line(store):
    """Our line on d1, cut by his voice three characters in."""
    from conversation.mouth import SayEnded
    from tests.conversation.unit.convkit import Harness
    from tests.conversation.unit.test_a_wordless_barge_in_gives_the_line_back import LINE, _speaking
    h = Harness(store)
    sid = _speaking(h)
    h.conv.ack(SayEnded(sid, "cut", 3, 700, "d1", "agent_estimate"))
    return h, LINE


@pytest.mark.parametrize("reason, resumed", [("stop", False), ("not_addressed", True)])
def test_a_stop_discard_never_gives_the_cut_line_back(store, reason, resumed):
    """The voice gate, case 13: cut → «Cállate.» discarded `stop` → the line said again to the end. A stop wins over
    the wordless resume; another discard still gives the line back."""
    h, line = _cut_line(store)
    h.hear(S.VadEdge("d1", "rise", 800), S.Discard("d1", "w_stop", reason, 1200))
    h.at(4000).pump()
    assert (len([o for o in h.mouth.orders if o.text != line]) == 1) is resumed


def test_a_stop_control_before_a_wordless_end_never_gives_the_line_back(store):
    """The other order: his stop arrives as a control, then a voice with no word ends — the line stays cut."""
    from tests.conversation.unit.inboxkit import control
    from conversation.types import ControlOp
    h, line = _cut_line(store)
    h.conv.give(control(ControlOp.STOP, 900, "k9", endpoint="d1"))
    h.hear(S.VadEdge("d1", "rise", 1000), S.Discard("d1", "", "no_voice", 1300))
    h.at(4000).pump()
    assert [o.text for o in h.mouth.orders] == [line]


@pytest.mark.parametrize("set_aside_s, onset_s, reclaimed", [(1.0, None, True), (5.0, None, False), (2.0, 1.0, False)])
def test_only_what_he_said_right_before_the_name_comes_back(real_attention, store, set_aside_s, onset_s, reclaimed):
    """The wake-word run: a refused question about the stock market was put in front of «Johnny, ¿qué hora es en
    Tokio?». Only words set aside within `reclaim_tail_ms` (3 s) before the name, in the same breath, come back."""
    import time
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply
    from tests.conversation.unit.convkit import Harness
    now = time.time()
    real_attention._state["last_directed"] = 0.0
    assert guards.judge("w1 w2", now=now - set_aside_s) == "not_addressed"
    real_attention._state["speech_onset"] = now - onset_s if onset_s else 0.0
    h = Harness(store, grace=False)
    h.conv.ear.guard = guards.for_ear
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.utter([(["Wzael", "w3"], 0)])
    assert ("w1 w2 Wzael" in h.model.calls[0].prompt.input) is reclaimed



def _over_our_line(heard=(), aec=None, lines=("La bolsa de valores es un mercado donde se compran acciones.",),
                   monkeypatch=None):
    from voice import mic_input
    from voice.engine.pipeline import ear_tap
    if aec is None:
        monkeypatch.delenv(mic_input.AEC_ENV, raising=False)
    else:
        monkeypatch.setenv(mic_input.AEC_ENV, "1" if aec else "0")
    tap = ear_tap.Tap("holder", lambda f: None)
    cuts = []
    tap.on_barge, tap.min_barge_ms = (lambda: cuts.append(1)), 500
    for line in lines:
        tap.said(line)
    tap.playback(True, now_ms=0)
    tap.heard = heard
    for t in range(1000, 2200, 30):
        tap.edges.frame(True, t)
    return bool(cuts)


def test_our_echo_heard_mid_word_never_cuts(monkeypatch):
    """The voice gate on 4d4fc3163: the cut fired on «La bolsa e» — an interim cut mid-word, not found in our line."""
    from voice import echo_text
    assert echo_text.contained("La bolsa e", "La bolsa de valores es un mercado")
    assert not _over_our_line(("La", "bolsa", "e"), monkeypatch=monkeypatch)
    assert _over_our_line(("wq", "wr", "w0"), monkeypatch=monkeypatch)                     # his own words cut


def test_our_echo_of_an_earlier_line_never_cuts(monkeypatch):
    assert not _over_our_line(("w1", "w2", "w3"), lines=("w1 w2 w3 w4.", "w5 w6 w7."), monkeypatch=monkeypatch)


@pytest.mark.parametrize("aec, cuts", [(True, True), (False, False), (None, False)])
def test_a_wordless_rise_cuts_only_when_his_device_cancels_our_echo(monkeypatch, aec, cuts):
    """A short «Cállate» Flux never wrote: with echo cancellation declared ON a sustained wordless rise stops us (the
    old path did); off or unknown, our echo could be that rise — only his words cut, or the button."""
    assert _over_our_line((), aec=aec, monkeypatch=monkeypatch) is cuts


def test_the_holders_device_declares_its_echo_cancellation(monkeypatch):
    from server import livekit_api
    from voice import mic_input
    monkeypatch.setattr(mic_input, "set_muted", lambda *a, **k: None)
    monkeypatch.delenv(mic_input.AEC_ENV, raising=False)
    livekit_api._declare_mic("s1", "s1", False, "d1", "acquire", True)
    assert mic_input.device_aec()
    livekit_api._declare_mic("s1", "s1", False, "d1", "heartbeat", None)        # it stopped saying: unknown
    assert not mic_input.device_aec() and mic_input.AEC_ENV not in __import__("os").environ
    livekit_api._declare_mic("s1", "s1", False, "d1", "heartbeat", True)
    monkeypatch.setattr(mic_input, "apply_input", lambda: None)
    monkeypatch.setattr(mic_input, "_decl", dict(mic_input._decl))                  # the switch's state, given back
    mic_input.undeclare(reason="w")                                              # another surface: not its word
    assert not mic_input.device_aec()


def test_the_wake_phrase_of_words_the_paid_ear_brought_is_never_answered_twice(ear, monkeypatch):
    """The operator's live test (session c2cb9f47): «¿Cómo estás? ¿Me estás escuchando?» came through the paid ear and
    was answered; then the browser's own ear delivered the same words as a wake phrase, which CUT the reply and got a
    second one. The phrase of words the paid ear brought a few seconds ago (or is bringing) never enters."""
    import time
    events, heard = [], []
    conv = SimpleNamespace(em=SimpleNamespace(emit=lambda kind, label, **kw: events.append((kind, label, kw))),
                           hear=lambda sig: heard.append(sig))
    monkeypatch.setattr(entry, "_hand", lambda fn: fn(conv))
    for f in _turn(words=("¿Cómo", "estás?", "¿Me", "estás", "escuchando?")):
        ear_in.receive(f, lambda s: None)
    controls.local_phrase("buenas wzael cómo estás me estás escuchando", "")
    assert heard == [] and [(lab, kw["reason"]) for _k, lab, kw in events] == [("discarded", "heard_by_ear")]
    controls.local_phrase("wzael w7 w8 w9", "")                                  # words the paid ear never had
    assert [type(s).__name__ for s in heard] == ["LocalPhrase"]
    monkeypatch.setattr(time, "time", lambda real=time.time: real() + controls.HEARD_WITHIN_S + 1)
    controls.local_phrase("buenas wzael cómo estás me estás escuchando", "")    # long after: his again
    assert len(heard) == 2
