"""A barge-in with no word gives the cut line back — from the voice process's own edges (node 13.99, V2-941, B8f).

The voice smoke (3b) on B8e: a «mmm» over our line cut it (the local rule) and the line never came back. His voice
rose while ours sounded, so its rise went out as possible echo (`echo_safe` false) and the ear never opened it: no
intervention, no discard, no RESUME_LINE. Now the local rule, once it has proved the voice his (it rose after our line
began and lasted the threshold), sends that rise again as his, stamped at its real start. The whole sequence goes
through the tap's edges, the body's lane and the conversation: the line is cut, the voice ends with no word, and the
rest of the line is said once, by voice. A barge-in WITH words is answered instead, never resumed.
"""
from __future__ import annotations

from conversation.ear import signals as S
from conversation.mouth import SayEnded
from conversation.ports import Done
from conversation.testing.scripted_model import reply
from nucleo.conversation_host import ear_in
from tests.conversation.unit.convkit import Harness
from voice.engine.pipeline import ear_tap

LINE = "w1 w2. w3 w4. w5 w6."


def _speaking(h):
    h.mouth.ack = None
    h.model.default = lambda ids: [reply(LINE), Done()]
    h.typed("w0", 100, ep="d1")
    h.at(600).pump()
    return h.mouth.orders[-1].say_id


def _through_the_tap(h, frames, cut_heard: int, sid: str):
    """The voice process's edges for `frames` (time, speaking) while our line sounds, as the body hears them."""
    facts = []
    tap = ear_tap.Tap("d1", facts.append)
    tap.min_barge_ms = 500
    cut = []
    tap.on_barge = lambda: cut.append(1)
    tap.playback(True, now_ms=650)
    seq = 0
    for t, speaking in frames:
        tap.edges.frame(speaking, t)
        if cut and tap.speaking:                                             # the voice process cut our line
            tap.playback(False, now_ms=t)
            h.conv.ack(SayEnded(sid, "cut", cut_heard, t, "d1", "agent_estimate"))
        for f in facts:
            seq += 1
            for sig in ear_in.signals(f):
                h.hear(sig)
        facts.clear()
    return cut


def test_a_mmm_over_our_line_cuts_it_and_the_line_goes_on(store):
    ear_in._reset_for_tests()
    h = Harness(store)
    sid = _speaking(h)
    hum = [(t, True) for t in range(700, 1500, 30)] + [(t, False) for t in range(1500, 1800, 30)]
    cut = _through_the_tap(h, hum, cut_heard=9, sid=sid)
    assert cut == [1]
    h.hear(S.Tick(1800 + h.conv.cfg.close_cap_ms))
    h.at(4000).pump()
    assert [o.text for o in h.mouth.orders][-1] == "w3 w4. w5 w6." and "voice" in h.mouth.orders[-1].channels
    discarded = [p["reason"] for k, lab, p in h.tel.events if k == "conv_ear" and lab == "discarded"]
    assert discarded                                                        # his «mmm», heard and thrown away
    h.at(6000).pump()
    assert [o.text for o in h.mouth.orders].count("w3 w4. w5 w6.") == 1     # once


def test_the_rise_is_sent_again_as_his_at_its_real_start():
    facts = []
    tap = ear_tap.Tap("holder", facts.append)
    tap.on_barge, tap.min_barge_ms = (lambda: None), 500
    tap.playback(True, now_ms=0)
    for t in range(100, 700, 30):
        tap.edges.frame(True, t)
    rises = [(f["t_ms"], f["echo_safe"]) for f in facts if f["t"] == "vad" and f["edge"] == "rise"]
    assert rises == [(100, False), (100, True)]                              # possible echo, then proved his


def _commands(h):
    return [p.get("command") for k, lab, p in h.tel.events if k == "conv_run" and lab == "command"]


def test_a_no_reply_after_reads_for_his_words_is_asked_once_for_a_reply(store):
    """NVIDIA in the smoke: it searched and recalled, then «I need the closes of the last 30 Fridays… I can't count»
    as a no_reply — and he heard nothing. A no_reply in a run that read for his words gets one repair round."""
    from conversation.ports import Command, ToolCall, ToolResult
    from conversation.types import Evidence
    h = Harness(store, grace=False)
    h.tools.answers["market_data"] = ToolResult("ok", {}, (Evidence("ev1", "search", numbers=(1.0,)),))
    rounds = [[ToolCall("c1", "market_data", {}), Done()], [Command("no_reply", {"reason": "w_missing"}), Done()],
              [reply("w_what_i_found"), Done()]]
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - 1, len(rounds) - 1)]
    h.typed("w1 w2", 10)
    h.settle(2000)
    assert [o.text for o in h.mouth.orders] == ["w_what_i_found"] and "no_reply_after_reads" in _commands(h)
    asked = h.model.calls[2].prompt.steps[-1][1].data
    assert asked["read"] == ["market_data"] and "what is missing" in asked["reason"]


def test_a_second_no_reply_after_reads_closes_silent_and_is_counted(store):
    from conversation.ports import Command, ToolCall, ToolResult
    h = Harness(store, grace=False)
    h.tools.answers["market_data"] = ToolResult("ok", {}, ())
    rounds = [[ToolCall("c1", "market_data", {}), Done()], [Command("no_reply", {"reason": "w_missing"}), Done()]]
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - 1, len(rounds) - 1)]
    h.typed("w1 w2", 10)
    h.settle(2000)
    ended = [p for k, lab, p in h.tel.events if k == "conv_run" and lab == "ended"]
    assert ended[-1]["outcome"] == "no_reply" and ended[-1]["after_reads"] and len(h.model.calls) == 3


def test_a_no_reply_with_no_read_is_left_as_the_model_said(store):
    from conversation.ports import Command
    h = Harness(store, grace=False)
    h.model.default = lambda ids: [Command("no_reply", {"reason": "w_not_for_us"}), Done()]
    h.utter([(["w1"], 0)])                     # his VOICE, no read: it may not be for us (a typed line is: 13.103)
    h.settle(2000)
    assert len(h.model.calls) == 1 and "no_reply_after_reads" not in _commands(h)
