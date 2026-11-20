"""Our voice never starts while his voice is open (node 13.122, V2-941, plan v3.2 §4, R3 — commit 3).

The operator's long monologue (session c2cb9f47): the ear cut his speech, the run answered the piece, waited its 8 s
and spoke over him — twice. Now ONE predicate stands before any line by voice: an intervention of his open on that
device (the ear's, words or not). No time bound lets a line out over it.

  · a reply ready while his voice is open is parked, never dropped and never made again; its request is not swept as
    stalled; when his voice closes with nothing of his (a noise, a discard) it is said, once;
  · what he says meanwhile is another batch, run with the parked reply in view: a reply to it replaces the parked one
    and answers both requests; a no_reply leaves the parked one standing, said when his voice closes, and that chunk
    never runs again;
  · two ways out, neither over his voice: past `not_his_ms` with everything closed there since not his, it is said;
    past `monologue_max_ms` it goes to the wall as text, never the voice;
  · a line owed is not said over his open voice either: it keeps waiting.

Disarms seen red: the predicate ignored at publication; the parked reply dropped instead of kept; the sweep stalling
it; the replacement not answering the parked request; the wall exit by voice.
"""
from __future__ import annotations

import pytest

from conversation.config import Config
from conversation.ear import signals as S
from conversation.ports import Command, Done
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness


def _open(h, t, ep="d1"):
    h.hear(S.VadEdge(ep, "rise", t))


def _words(h, toks, t0, t, ep="d1", turn=77, rev=1):
    h.hear(S.WordSpan(ep, turn, rev, False, h.words(toks, t0), (t0, t)), h.beats(t, t + 240, ep))


def _close(h, toks, t0, ep="d1", turn=77):
    ws = h.words(toks, t0)
    end = ws[-1][2]
    h.hear(S.WordSpan(ep, turn, 9, True, ws, (t0, end)), S.VadEdge(ep, "fall", end + 10),
           h.beats(end, end + 300, ep), S.EotHint(ep, "flux", "end", .9, end + 300))
    return end + 300


def _said(h):
    return [(o.text, sorted(o.channels)) for o in h.mouth.orders]


def _ready_then_he_speaks(store, cfg=None):
    """A reply for «w1 w2» is ready and waits its grace when his voice opens again, with words, and stays open."""
    h = Harness(store, config=cfg)
    h.model.default = lambda ids: [reply("w9"), Done()]
    end = h.utter([(["w1", "w2"], 0)])
    h.settle(100)
    h.t0 = end + 150
    _open(h, h.t0)
    _words(h, ["w3"], h.t0, h.t0 + 300)
    return h


def _talks(h, ms, step=250):
    """He keeps talking for `ms`: his words grow, the intervention stays open."""
    for i, t in enumerate(range(h.clock.mono, h.clock.mono + ms, step)):
        _words(h, ["w3"] + [f"w{j}" for j in range(4, 5 + i // 8)], h.t0, t, rev=2 + i)
        h.at(t).pump()


def test_a_ready_reply_never_starts_over_his_open_voice(store):
    h = _ready_then_he_speaks(store, cfg=Config(intervention_max_ms=60_000))
    _talks(h, 35_000)                       # past the 8 s hold, the 20 s window and a request's 30 s liveness
    assert h.mouth.orders == [] and "conv_close/stalled" not in h.tel.labels()
    assert any(k == "conv_run" and lab == "held" and p.get("waits_for") == "voice_open" for k, lab, p in h.tel.events)
    assert len(h.model.calls) == 1, "the ready reply is never made again"


def test_a_reply_made_while_his_voice_is_already_open_waits_for_it(store):
    """His voice went on at the end of turn (the ear's successor): the batch runs at the hold's bound, its reply is
    ready with his voice still open, and it waits — it is never said over him."""
    h = Harness(store, grace=False, config=Config(intervention_max_ms=60_000))
    h.model.default = lambda ids: [reply("w9"), Done()]
    t = 10
    _open(h, t)
    ws = h.words(["w1", "w2"], t)
    end = ws[-1][2]
    h.hear(S.WordSpan("d1", 1, 1, True, ws, (t, end)), h.beats(end, end + 300),
           S.EotHint("d1", "flux", "end", .9, end + 300))           # the provider ends the turn, his voice still up
    h.t0 = end + 300
    _talks(h, 12_000)
    assert len(h.model.calls) == 1 and h.mouth.orders == []


def test_a_line_owed_waits_even_when_the_onset_was_lost(store):
    """The manager's own note of his voice (`speaking_on`) missed it; the ear's open intervention still holds."""
    from conversation.ports import OwedLine
    h = Harness(store, grace=False)

    class Owed:
        taken = 0

        def next(self, account):
            self.taken += 1
            return OwedLine("k1", "w5")

        def release(self, key):
            pass

        def settle(self, key):
            pass

        def owe(self, *a):
            pass
    h.conv.owed = Owed()
    _open(h, 100)
    _words(h, ["w3"], 100, 400)
    h.conv.speaking_on.clear()
    h.at(500).pump()
    assert h.conv.owed.taken == 0 and h.mouth.orders == []


def test_what_he_adds_runs_with_the_parked_reply_in_view_and_replaces_it(store):
    h = _ready_then_he_speaks(store)
    h.model.default = lambda ids: [reply("w8"), Done()]
    _talks(h, 1000)
    h.at(_close(h, ["w3", "w4"], h.t0)).pump()
    h.settle(6000)
    assert _said(h) == [("w8", ["text", "voice"])]
    last = h.model.calls[-1].prompt.input
    assert "«w9»" in last and "w3 w4" in last and "] «w1 w2»" not in last  # the first chunk is never an entry twice
    assert [lab for lab, _ in h.closes()] == ["answered", "answered"]


def test_a_chunk_that_is_not_his_leaves_the_parked_reply_standing(store):
    h = _ready_then_he_speaks(store)
    h.model.default = lambda ids: [Command("no_reply", {"reason": "w0"}), Done()]
    _talks(h, 1000)
    h.at(_close(h, ["w3", "w4"], h.t0)).pump()
    h.settle(6000)
    assert _said(h) == [("w9", ["text", "voice"])]
    calls = len(h.model.calls)
    h.settle(6000)
    assert len(h.model.calls) == calls, "a chunk judged not his never runs again"


def test_a_chunk_of_his_that_adds_nothing_never_lets_the_reply_out_over_him(store):
    """The R3 review's R3-A: a chunk of his the model closed «adds nothing» is his — he goes on talking for 25 s, and
    the reply that waits is never said over him."""
    h = _ready_then_he_speaks(store, cfg=Config(not_his_ms=3000, intervention_max_ms=60_000))
    h.model.default = lambda ids: [Command("no_reply", {"reason": "w0"}), Done()]
    h.at(_close(h, ["w3", "w4"], h.t0)).pump()
    h.settle(500)
    h.t0 = h.clock.mono + 50
    _open(h, h.t0)
    _talks(h, 25_000)
    assert h.mouth.orders == [], "said over him after a chunk of his that added nothing"


def test_past_not_his_with_nothing_of_his_it_is_said(store):
    """What closed there was judged NOT his (`no_reply` with `not_his`) and the voice goes on (the room, a TV): past
    `not_his_ms` the reply that waits is said."""
    h = _ready_then_he_speaks(store, cfg=Config(not_his_ms=3000, intervention_max_ms=60_000))
    h.model.default = lambda ids: [Command("no_reply", {"reason": "w0", "not_his": True}), Done()]
    h.at(_close(h, ["w3", "w4"], h.t0)).pump()
    h.settle(500)
    h.t0 = h.clock.mono + 50
    _open(h, h.t0)
    _talks(h, 3500)
    assert _said(h) == [("w9", ["text", "voice"])]


def test_a_chunk_of_his_after_one_not_his_starts_the_count_again(store):
    """R3-A: a chunk judged not his, then one of his that adds nothing: the last close there was his, so the reply
    that waits stays held while he goes on talking — what was not his before never lets it out over him."""
    h = _ready_then_he_speaks(store, cfg=Config(not_his_ms=3000, intervention_max_ms=60_000))
    h.model.default = lambda ids: [Command("no_reply", {"reason": "w0", "not_his": True}), Done()]
    h.at(_close(h, ["w3", "w4"], h.t0)).pump()
    h.settle(500)
    h.model.default = lambda ids: [Command("no_reply", {"reason": "w0"}), Done()]
    h.t0 = h.clock.mono + 50
    _open(h, h.t0)
    _words(h, ["w5"], h.t0, h.t0 + 300, turn=78)
    h.at(_close(h, ["w5", "w6"], h.t0, turn=78)).pump()
    h.settle(500)
    h.t0 = h.clock.mono + 50
    _open(h, h.t0)
    _talks(h, 25_000)
    assert h.mouth.orders == [], "said over him: a close of his did not start the count again"


@pytest.mark.parametrize("judged", [True, False])
def test_a_voice_the_host_judged_not_his_holds_nothing(store, judged):
    """E6: the host's reading of the open voice (`foreign_voice`, the enrolled voice's verdicts) says it is another
    person's — a TV, someone across the room: the reply that waits is said while that voice goes on. The reader is asked
    with the device and the voice's onset; with no such judgement the voice holds, as ever."""
    h = _ready_then_he_speaks(store, cfg=Config(intervention_max_ms=60_000))
    asked = []
    h.conv.foreign_voice = lambda ep, onset: asked.append((ep, onset)) or (judged and ep == "d1" and onset == h.t0)
    _talks(h, 4000)
    assert (_said(h) == [("w9", ["text", "voice"])]) is judged and ("d1", h.t0) in asked


@pytest.mark.parametrize("order, dropped", [("stop_voice", True), ("stop_all", True), ("stop_media", False)])
def test_a_stop_drops_the_reply_that_waits_but_stopping_what_plays_leaves_it(store, order, dropped):
    """R3-B: his «para» while a reply waits for his voice: it is never said after — but stopping what plays is no stop
    of our answer."""
    h = _ready_then_he_speaks(store)
    h.model.default = lambda ids: [Command(order, {}), Done()]
    h.at(_close(h, ["w_para"], h.t0)).pump()
    h.settle(6000)
    assert (_said(h) == []) is dropped
    if dropped:
        assert "stopped" in [lab for lab, _ in h.closes()] and h.conv.waiting is None


def test_the_buttons_stop_drops_the_reply_that_waits(store):
    from conversation.types import ControlOp
    from tests.conversation.unit.inboxkit import control
    h = _ready_then_he_speaks(store)
    h.conv.give(control(ControlOp.STOP, h.clock.mono, "k1", endpoint="d1"))
    assert h.conv.waiting is None
    h.model.default = lambda ids: [reply("w10"), Done()]     # what he says after is answered on its own
    h.hear(S.VadEdge("d1", "fall", h.clock.mono + 10))
    h.settle(6000)
    assert "w9" not in [t for t, _ in _said(h)] and "stopped" in [lab for lab, _ in h.closes()]


def test_past_the_monologue_ceiling_it_goes_to_the_wall_as_text(store):
    h = _ready_then_he_speaks(store, cfg=Config(monologue_max_ms=5000, intervention_max_ms=60_000))
    _talks(h, 6000)
    assert _said(h) == [("w9", ["text"])]


def test_a_line_owed_waits_for_his_voice_to_close(store):
    from conversation.ports import OwedLine
    h = Harness(store, grace=False)

    class Owed:
        def __init__(self):
            self.taken = 0

        def next(self, account):
            self.taken += 1
            return OwedLine("k1", "w5")

        def release(self, key):
            pass

        def settle(self, key):
            pass

        def owe(self, *a):
            pass
    h.conv.owed = Owed()
    _open(h, 100)
    h.settle(2000)
    assert h.conv.owed.taken == 0 and h.mouth.orders == []
