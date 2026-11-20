"""The publication waits for the person's resumed voice (node 13.29).

He pauses, the model starts, he goes on. If he speaks again on the device of the batch's last entry, within
`resume_window_ms` of it, and the run has not published yet, the run stops at its next checkpoint and its batch is not
eligible while that voice is open — the same check runs again right before sealing. The voice always ends (the ear's
cap, on the sweep's ticks): with words, the continuation travels with the batch and the model hears the whole sentence
in one prompt, nothing said before; a cough (no words) lets the batch run as it was. Another device, outside the
window, or a run that already published: no hold. The hold is bounded (`resume_hold_max_ms` from the close of the
batch's last entry, never reset by words), inside the request's liveness: no hold stalls a request.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conversation.config import Config
from conversation.ear import signals as S
from conversation.ports import Done, ToolCall
from conversation.replay import Replay, load
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sessions"


def _held_for_voice(h: Harness) -> bool:
    """A run held for his resumed voice — not a reply waiting for its grace."""
    return any(k == "conv_run" and lab == "held" and p.get("waits_for") != "grace" for k, lab, p in h.tel.events)


def _go_on(h: Harness, toks, *, ep="d1", close=True, once: list | None = None):
    def step():
        if once is not None:
            if once:
                return
            once.append(1)
        t = h.clock.mono + 50
        h.hear(S.VadEdge(ep, "rise", t))
        if toks:
            ws = h.words(toks, t)
            h.hear(S.WordSpan(ep, 77, 1, close, ws, (t, ws[-1][2])))
            if close:
                end = ws[-1][2]
                h.hear(S.VadEdge(ep, "fall", end + 10), h.beats(end, end + 300, ep),
                       S.EotHint(ep, "flux", "end", .9, end + 300))
    return step


def test_he_goes_on_the_run_waits_and_the_model_hears_the_whole_sentence_once(store):
    h = Harness(store)
    once: list = []
    h.model.script["iv_000001"] = [[_go_on(h, ["w3", "w4"], once=once), reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    h.settle()
    assert len(h.mouth.orders) == 1 and _held_for_voice(h)
    last = h.model.calls[-1].prompt.input
    assert "«w1 w2»" in last and "«w3 w4»" in last
    assert not any("«w1 w2»" in c.prompt.input for c in h.model.calls[:-1] if c is not h.model.calls[0])
    assert [lab for lab, _ in h.closes()] == ["answered", "answered"]


def test_a_cough_lets_the_batch_run_as_it_was(store):
    h = Harness(store)
    once: list = []
    h.model.script["iv_000001"] = [[_go_on(h, [], once=once), reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    assert not h.mouth.orders                                        # held: the cough is still an open voice
    t = h.clock.mono
    h.hear(S.VadEdge("d1", "fall", t + 100), S.Tick(t + 3000))       # no words: discarded at the cap
    assert len(h.mouth.orders) == 1 and "«w1 w2»" in h.model.calls[-1].prompt.input
    assert [lab for lab, _ in h.closes()] == ["answered"]


def test_a_voice_that_never_ends_is_ended_by_the_ear_and_releases_the_batch(store):
    h = Harness(store)
    once: list = []
    h.model.script["iv_000001"] = [[_go_on(h, [], once=once), reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])                                     # a rise, then nothing at all
    for t in range(h.clock.mono + 500, h.clock.mono + 6000, 500):
        h.at(t).pump()
    assert len(h.mouth.orders) == 1 and "conv_ear/discarded" in h.tel.labels()


@pytest.mark.parametrize("why", ["another_device", "outside_the_window"])
def test_another_device_or_outside_the_window_holds_nothing(store, why):
    cfg = Config(resume_window_ms=100) if why == "outside_the_window" else Config()
    h = Harness(store, config=cfg)
    ep = "d2" if why == "another_device" else "d1"

    def late():
        h.at(h.clock.mono + 500)
        _go_on(h, [], ep=ep)()

    h.model.script["iv_000001"] = [[late, reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    h.settle()
    assert len(h.mouth.orders) == 1 and not _held_for_voice(h)


def test_a_run_that_already_acted_is_not_held(store):
    """No run claims an effect in F1 (nothing but a read passes); the fact is set by hand, as F2's reservation will."""
    h = Harness(store)
    once: list = []
    h.model.script["iv_000001"] = [[lambda: setattr(h.conv.current, "claimed", True),
                                    ToolCall("c", "search", {"q": "w1"}), Done()],
                                   [_go_on(h, [], once=once), reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    h.settle()
    assert not _held_for_voice(h) and len(h.mouth.orders) == 1


def test_the_check_runs_again_right_before_sealing(store):
    """A voice the manager never got an onset for (it opened after the last checkpoint): sealing looks again — with no
    grace, so the seal is the next thing the run does."""
    h = Harness(store, grace=False)
    seen: list = []

    def opens_quietly():
        if seen:
            return
        seen.append(1)
        h.conv.ear.feed(S.VadEdge("d1", "rise", h.clock.mono + 10))  # straight into the ear: no onset reached it

    h.model.script["iv_000001"] = [[opens_quietly, reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    assert not h.mouth.orders and _held_for_voice(h)


def test_a_continuation_longer_than_the_bound_is_never_spoken_over(store):
    """He goes on and keeps talking past `resume_hold_max_ms`: his words do not reset the bound — the old batch runs at
    it — but its reply never starts while his voice is open (R3, plan v3.2 §4, node 13.122): it waits, parked, and no
    request is stalled by the wait."""
    h = Harness(store)
    once: list = []
    h.model.script["iv_000001"] = [[_go_on(h, ["w3"], close=False, once=once), reply("w9"), Done()],
                                   [reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    t0 = h.clock.mono
    for i, t in enumerate(range(t0 + 250, t0 + 12_000, 250)):      # words keep coming for 12 s
        h.hear(S.WordSpan("d1", 77, 2 + i, False, h.words(["w3"] + [f"w{j}" for j in range(4, 5 + i // 4)], t0),
                          (t0, t)), h.beats(t, t + 249))
    assert not any(k == "conv_mouth" and lab == "say" for k, lab, p in h.tel.events), "said over his open voice"
    assert "conv_close/stalled" not in h.tel.labels()


def test_no_hold_can_outlast_a_request(store):
    cfg = Config()
    assert cfg.liveness_ms > cfg.resume_hold_max_ms + cfg.model_first_ms


def test_the_window_is_never_shorter_than_the_models_first_deadline():
    cfg = Config()
    assert cfg.resume_window_ms >= cfg.model_first_ms


@pytest.mark.parametrize("think_ms", [800, 1500])
def test_s2_nothing_is_said_while_a_resumed_voice_is_open(think_ms):
    """The recorded session where the model, thinking 0.8–1.5 s, answered into the person's own pause: no line of ours
    goes out while a voice that resumed after the batch's last entry is open on that device — within the hold's bound
    from that entry's close (past it the batch runs as it is, by design; these recordings carry the old pipeline's VAD,
    whose falls come late or never, so their voices stay open long)."""
    rep = Replay(load((FIX / "s2.jsonl").read_text().splitlines()), think_ms=think_ms).run()
    W = []
    opened, ended, closes, starts = {}, {}, [], []
    for k, lab, p in rep.tel.events:
        r = p["refs"]
        if k == "conv_ear" and lab == "opened":
            opened[r["iv"]] = (p["t_ms"], r.get("endpoint"))
        elif k == "conv_ear" and lab in ("closed", "incomplete", "discarded"):
            ended.setdefault(r.get("iv"), p["t_ms"])
            if lab == "closed":
                closes.append((p["t_ms"], r.get("endpoint")))
        elif k == "conv_run" and lab == "started":
            starts.append((p["t_ms"], r["run"]))
        elif k == "conv_mouth" and lab == "say" and "voice" in p["channels"]:
            t = p["t_ms"]
            run_start = max((s for s, run in starts if run == r["run"]), default=t)
            last = max((c for c, _ep in closes if c <= run_start), default=0)
            for iv, (to, ep) in opened.items():
                if (ep == r.get("endpoint") and last <= to <= t and ended.get(iv, 10 ** 18) > t
                        and t - last < rep.config.resume_hold_max_ms):
                    W.append((iv, to, t))
    assert not W, f"said while he spoke again: {W}"
    assert any(lab == "held" and p.get("waits_for") != "grace" for k, lab, p in rep.tel.events if k == "conv_run")


def test_a_stop_while_the_run_is_held_cancels_it_and_nothing_is_said(store):
    """Review TA-2: the run gave its batch back to his resumed voice; he presses stop. A batch that waits is a run that
    has not started: the stop cancels it — its requests close silent, and when his voice ends nothing is said for it."""
    from conversation.types import ControlOp
    from tests.conversation.unit.inboxkit import control
    h = Harness(store)
    once: list = []
    h.model.script["iv_000001"] = [[_go_on(h, ["w3"], close=False, once=once), reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    assert _held_for_voice(h) and not h.mouth.orders
    h.conv.give(control(ControlOp.STOP, h.clock.mono, "k-stop", endpoint="d1"))
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("silent", "stopped")]
    t = h.clock.mono
    h.hear(S.WordSpan("d1", 77, 2, True, h.words(["w3", "w4"], t), (t, t + 400)),
           S.VadEdge("d1", "fall", t + 410), h.beats(t + 400, t + 800), S.EotHint("d1", "flux", "end", .9, t + 800))
    h.pump()
    prompts = [c.prompt.input for c in h.model.calls[1:]]
    assert all("«w1 w2»" not in p for p in prompts)            # the stopped sentence never runs again


def test_a_stop_inside_the_collect_window_cancels_what_waits(store):
    from conversation.types import ControlOp
    from tests.conversation.unit.inboxkit import control
    h = Harness(store, config=Config(collect_ms=350))                         # the window, when a genome sets one
    h.typed("w1", 100)
    h.conv.give(control(ControlOp.STOP, 150, "k-stop", endpoint="d2"))
    h.at(2000).pump()
    assert not h.model.calls and [(lab, p["reason"]) for lab, p in h.closes()] == [("silent", "stopped")]
