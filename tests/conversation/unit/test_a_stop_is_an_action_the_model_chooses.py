"""A stop is a system action the MODEL chooses (node 13.120, V2-941, plan v3.2 §3 — commit 1, the package).

No word of his is read to decide a stop. The catalog offers four orders with no parameters — `stop_voice`,
`stop_media`, `stop_run`, `stop_all` — and the model picks one when his last words ask to stop:

  · valid only as the model's FIRST order in the run and before any read it asked for (refused and counted after:
    what a page or a mail brought can stop nothing); the host's own memory read before the model does not count;
  · a valid stop is handed to the host in the act (`Stops`); `voice`, `run`, `all` cut our voice now;
  · `stop_voice` / `stop_media` let the run go on — a stop and a question are answered («Cállate. ¿Qué tiempo
    hace?»); with nothing more, or a no_reply, the batch closes `stopped` and nothing is said; `stop_run` / `stop_all`
    abandon the run: nothing of it is said;
  · a typed batch closed `stopped` gets the language's fixed minimal line, on the text channel;
  · a batch that cut our voice and then FAILS says its failure line on the screen only, never on the voice.

Disarms seen red: a stop after a read taken; a stop's run that says nothing closed silent instead of `stopped`; the
host not handed the stop; `stop_run` letting its reply out; the typed line missing; the failure line on the voice.
"""
from __future__ import annotations

from conversation.ear import signals as S
from conversation.mouth import SayEnded
from conversation.ports import Command, Done, Failed, ToolCall
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness
from tests.conversation.unit.test_a_wordless_barge_in_gives_the_line_back import _speaking


class _Stops:
    def __init__(self):
        self.calls = []

    def stop(self, scope, endpoint):
        self.calls.append((scope, endpoint))


class _Words:
    def line(self, key, near=""):
        return {"stopped": "w_stopped", "mute_lines": "w_lost"}.get(key, "")


def _h(store, rounds):
    h = Harness(store, grace=False)
    h.conv.stops, h.conv.words = _Stops(), _Words()
    it = iter(rounds)
    h.model.default = lambda ids: next(it)
    return h


def _ended(h):
    return [(p.get("outcome"), p.get("scope")) for k, lab, p in h.tel.events if k == "conv_run" and lab == "ended"]


def _closes(h):
    return [lab for k, lab, _p in h.tel.events if k == "conv_close"]


def _commands(h):
    return [p.get("command") for k, lab, p in h.tel.events if k == "conv_run" and lab == "command"]


def test_a_stop_alone_closes_stopped_and_says_nothing(store):
    h = _h(store, [[Command("stop_voice", {}), Done()]])
    h.utter([(["w1"], 0)])
    h.settle(3000)
    assert h.mouth.orders == [] and _ended(h) == [("stopped", "voice")] and _closes(h) == ["stopped"]
    assert h.conv.stops.calls == [("voice", "d1")] and ("stop", None, "stop") in h.mouth.calls


def test_a_stop_and_a_question_is_answered(store):
    h = _h(store, [[Command("stop_voice", {}), reply("w9"), Done()]])
    h.utter([(["w1", "w2"], 0)])
    h.settle(3000)
    assert [o.text for o in h.mouth.orders] == ["w9"] and h.conv.stops.calls == [("voice", "d1")]


def test_a_stop_then_no_reply_is_stopped_never_asked_again(store):
    h = _h(store, [[Command("stop_media", {}), Command("no_reply", {"reason": "w0"}), Done()]])
    h.utter([(["w1"], 0)])
    h.settle(3000)
    assert _ended(h) == [("stopped", "media")] and "no_reply_voice" not in _commands(h)
    assert ("stop", None, "stop") not in h.mouth.calls, "stopping what plays never cuts our voice"


def test_stop_run_abandons_the_run(store):
    h = _h(store, [[Command("stop_run", {}), reply("w9"), Done()]])
    h.utter([(["w1"], 0)])
    h.settle(3000)
    assert h.mouth.orders == [] and _ended(h) == [("stopped", "run")]


def test_a_stop_after_a_read_it_asked_for_is_refused(store):
    h = _h(store, [[ToolCall("x1", "w_read", {}), Done()], [Command("stop_all", {}), reply("w9"), Done()]])
    h.utter([(["w1"], 0)])
    h.settle(3000)
    assert h.conv.stops.calls == [] and "stop_refused" in _commands(h)
    assert [o.text for o in h.mouth.orders] == ["w9"]


def test_a_stop_that_is_not_the_first_order_is_refused(store):
    h = _h(store, [[Command("no_reply", {"reason": "w0"}), Done()], [Command("stop_voice", {}), reply("w9"), Done()]])
    h.utter([(["w1"], 0)])
    h.settle(3000)
    assert h.conv.stops.calls == [] and "stop_refused" in _commands(h)


def test_a_typed_batch_stopped_gets_the_fixed_line_on_the_text_channel(store):
    h = _h(store, [[Command("stop_all", {}), Done()]])
    h.typed("w1", 100)
    h.settle(3000)
    assert [(o.text, sorted(o.channels)) for o in h.mouth.orders] == [("w_stopped", ["text"])]
    assert _ended(h) == [("stopped", "all")]


def test_a_batch_that_cut_our_voice_and_fails_says_so_on_the_screen_only(store):
    h = Harness(store, grace=False)
    h.conv.words = _Words()
    sid = _speaking(h)
    start = next(row for _k, row in h.store.view(h.conv.account).recent("says", 2))["t_ms"]
    h.model.default = lambda ids: [Failed("timeout", "provider")]
    h.hear(S.VadEdge("d1", "rise", start + 50))
    h.conv.ack(SayEnded(sid, "cut", 4, start + 600, "d1", "agent_estimate"))
    h.utter([(["w1", "w2"], 0)], at=start + 40)
    h.settle(3000)
    lost = [o for o in h.mouth.orders if o.text == "w_lost"]
    assert lost and all(sorted(o.channels) == ["text"] for o in lost)
