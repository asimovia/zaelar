"""A request that ended takes its intervention with it, and nothing waits on the ear forever (node 13.27; review 2,
N1 and N2).

N1: once a request is final — answered, silent, stopped, recovered — its intervention is final for the ear: the voice
that follows is a NEW intervention with its own request and its own close, never a revision glued to the closed one;
and before that, a reopen counts only within `reopen_window_ms` of the close. N2: the sweep ticks the ear, so a reopen
that no signal ever ends (the phone dropped) still ends within the bound, and the sentence before it is answered.
"""
from __future__ import annotations

from conversation import envelopes as E
from conversation.config import Config
from conversation.ear import signals as S
from conversation.ports import Command, Done
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness
from tests.conversation.unit.earkit import feed
from tests.conversation.unit.inboxkit import control
from conversation.types import ControlOp

SILENT = [Command("no_reply", {"reason": "nothing_to_add"}), Done()]


def _requests(h: Harness) -> dict[str, str]:
    return {r["id"]: r["state"] for _k, r in h.conv.book.snapshot().scan("items") if r["kind"] == "request"}


def test_n1_voice_a_minute_after_a_silent_request_is_a_new_intervention(store):
    h = Harness(store)
    h.model.default = lambda ids: SILENT if ids == ["iv_000001"] else [reply("w9"), Done()]
    h.utter([(["w1", "w2"], 0)])
    assert _requests(h) == {"r_iv_000001": "silent"}
    h.at(h.clock.mono + 60_000)
    h.utter([(["w7", "w8"], 0)])
    second = h.model.calls[-1].prompt.input
    assert "«w7 w8»" in second and "w1 w2 w7" not in second and "iv_000001 · voice" not in second
    reqs = _requests(h)
    assert reqs["r_iv_000001"] == "silent" and len(reqs) == 2 and "answered" in reqs.values()
    assert [lab for lab, _ in h.closes()] == ["silent", "answered"]          # one close per request
    assert "conv_ear/reopened" not in h.tel.labels()


def test_n1_after_a_stop_the_next_sentence_does_not_carry_the_stopped_one(store):
    h = Harness(store)
    stop = control(ControlOp.STOP, 0, "k-stop", endpoint="d1")
    h.model.script["iv_000001"] = [[lambda: h.conv.give(stop), reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    assert [lab for lab, _ in h.closes()] == ["silent"]
    h.utter([(["w3"], 0)])                                    # right after: inside the window, but the request is final
    assert "w1" not in h.model.calls[-1].prompt.input.split("INPUT")[-1].split("]", 1)[-1].split("\n")[0]
    assert [lab for lab, _ in h.closes()] == ["silent", "answered"]
    assert "conv_ear/reopened" not in h.tel.labels()           # the ear knew: it never even tried the closed one


def test_n1_a_reopen_counts_only_within_the_window_of_the_close(clock, telemetry):
    from conversation.ear import Ear
    from conversation.telemetry import Emitter
    from conversation.types import Ids
    D, w = "d1", lambda tok, t: ((tok, t, t + 160, 1.0),)
    for gap, reopened in ((1000, True), (4000, False)):
        e = Ear("acct-test", Config(reopen_window_ms=2500), Emitter(telemetry, clock, "acct-test"), Ids())
        feed(e, S.VadEdge(D, "rise", 0), S.WordSpan(D, 1, 1, True, w("w1", 0), (0, 160)), S.VadEdge(D, "fall", 200),
             S.Watermark(D, 400), S.EotHint(D, "flux", "end", .9, 400))
        t = 400 + gap
        out = feed(e, S.VadEdge(D, "rise", t), S.WordSpan(D, 2, 1, False, w("w2", t), (t, t + 160)))
        states = [o.body for o in out if isinstance(o, E.Envelope) and o.kind is E.EnvelopeKind.INTERVENTION_STATE]
        assert any(E.is_reopen(o) for o in out if isinstance(o, E.Envelope)) is reopened, gap
        if not reopened:
            assert states[-1].intervention_id != "iv_000001" and e.open_intervention()[0] != "iv_000001"


def test_n2_a_reopen_no_signal_ends_is_ended_by_the_sweep_and_the_sentence_is_answered(store):
    h = Harness(store)

    def goes_on_then_drops():
        if len(h.model.calls) > 1:
            return
        t = h.clock.mono + 50
        h.hear(S.VadEdge("d1", "rise", t), S.WordSpan("d1", 77, 1, False, h.words(["w3"], t), (t, t + 180)))

    h.model.script["iv_000001"] = [[goes_on_then_drops, reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])                              # …and then nothing: no beat, no fall, no end
    for t in range(h.clock.mono + 500, h.clock.mono + 150_000, 500):
        h.at(t).pump()
    assert h.mouth.orders, "nobody answered"
    assert not h.conv.ear.open_ids()
    rows = [r for _k, r in h.store.snapshot("acct-test").scan("inbox")]
    assert not [r for r in rows if r["state"] in ("queued", "dequeued", "held")]
    assert all(s != "open" for s in _requests(h).values())


def test_n2_a_reopen_this_ear_still_hears_is_given_back_past_the_bound(store):
    """The person goes on with a word that never becomes final, the voice never falls, the provider never says end
    and keeps beating: past the bound the closed revision runs anyway, and what was heard since is a new intervention."""
    h = Harness(store)

    def goes_on():
        if len(h.model.calls) > 1:
            return
        t = h.clock.mono + 50
        h.hear(S.VadEdge("d1", "rise", t), S.WordSpan("d1", 77, 1, False, h.words(["w3"], t), (t, t + 180)))

    h.model.script["iv_000001"] = [[goes_on, reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    t0 = h.clock.mono
    for t in range(t0 + 240, t0 + 12_000, 240):
        h.hear(S.Watermark("d1", t))
    assert h.mouth.orders, "the closed revision never ran: the reopen held it past the bound"
    assert "«w1 w2»" in h.model.calls[-1].prompt.input


def test_n2_the_providers_end_with_a_word_never_final_ends_incomplete_at_the_cap(clock, telemetry):
    from conversation.ear import Ear
    from conversation.telemetry import Emitter
    from conversation.types import Ids
    e = Ear("acct-test", Config(), Emitter(telemetry, clock, "acct-test"), Ids())
    D = "d1"
    feed(e, S.VadEdge(D, "rise", 0), S.WordSpan(D, 1, 1, False, (("w1", 0, 160, 1.0),), (0, 160)),
         S.EotHint(D, "flux", "end", .8, 400))
    out = feed(e, *[S.Watermark(D, t) for t in range(400, 3400, 240)])
    assert [o.body.state for o in out if isinstance(o, E.Envelope)] == [E.IvState.INCOMPLETE]
