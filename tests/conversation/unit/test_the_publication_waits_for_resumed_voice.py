"""The publication waits for the person's resumed voice (node 13.29).

He pauses, the model starts, he goes on. If he speaks again on the device of the batch's last entry, within
`resume_window_ms` of it, and the run has not published yet, the run stops at its next checkpoint and its batch is not
eligible while that voice is open — the same check runs again right before sealing. The voice always ends (the ear's
cap, on the sweep's ticks): with words, the continuation travels with the batch and the model hears the whole sentence
in one prompt, nothing said before; a cough (no words) lets the batch run as it was. Another device, outside the
window, or a run that already published: no hold. While held, the person is speaking: no request is stalled.
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
    assert len(h.mouth.orders) == 1 and "conv_run/held" in h.tel.labels()
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
    assert len(h.mouth.orders) == 1 and "conv_run/held" not in h.tel.labels()


def test_a_run_that_already_acted_is_not_held(store):
    h = Harness(store)
    once: list = []
    h.model.script["iv_000001"] = [[ToolCall("c", "agenda_add", {"what": "w1"}), Done()],
                                   [_go_on(h, [], once=once), reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    assert "conv_run/held" not in h.tel.labels() and len(h.mouth.orders) == 1


def test_the_check_runs_again_right_before_sealing(store):
    """A voice the manager never got an onset for (it opened after the last checkpoint): sealing looks again."""
    h = Harness(store)
    seen: list = []

    def opens_quietly():
        if seen:
            return
        seen.append(1)
        h.conv.ear.feed(S.VadEdge("d1", "rise", h.clock.mono + 10))  # straight into the ear: no onset reached it

    h.model.script["iv_000001"] = [[opens_quietly, reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    assert not h.mouth.orders and "conv_run/held" in h.tel.labels()


def test_while_he_keeps_talking_no_request_is_stalled(store):
    h = Harness(store, config=Config(liveness_ms=5000))
    once: list = []
    h.model.script["iv_000001"] = [[_go_on(h, ["w3"], close=False, once=once), reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    t0 = h.clock.mono
    for i, t in enumerate(range(t0 + 1000, t0 + 12_000, 1000)):     # words keep coming for 11 s
        h.hear(S.WordSpan("d1", 77, 2 + i, False, h.words(["w3"] + [f"w{j}" for j in range(4, 5 + i)], t0), (t0, t)),
               h.beats(t, t + 999))
    assert "conv_close/stalled" not in h.tel.labels(), h.closes()
    assert not h.mouth.orders


def test_the_window_is_never_shorter_than_the_models_first_deadline():
    cfg = Config()
    assert cfg.resume_window_ms >= cfg.model_first_ms


@pytest.mark.parametrize("think_ms", [800, 1500])
def test_s2_nothing_is_said_while_a_resumed_voice_is_open(think_ms):
    """The recorded session where the model, thinking 0.8–1.5 s, answered into the person's own pause: no line of ours
    goes out while a voice that resumed after the batch's last entry is open on that device."""
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
                if ep == r.get("endpoint") and last <= to <= t and ended.get(iv, 10 ** 18) > t:
                    W.append((iv, to, t))
    assert not W, f"said while he spoke again: {W}"
    assert "conv_run/held" in rep.tel.labels("conv_run")
