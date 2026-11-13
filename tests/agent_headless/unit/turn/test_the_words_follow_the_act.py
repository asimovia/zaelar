"""The words follow the act (CRIT-K2b corollary, V2-893 L2): ONE decision releases the model's call, its words and its
inline tags — never a second reading at another bar.

The class: in the escalate band (sure at the licence, not at the act floor) a call that LEAVES is held from the licence
(C9) while the words were released at the first word and the tags mid-stream, both read at the act floor — so «Sent!»
was said, and the turn's tags ran, for a send that was held. The same with the brief still in flight past the route
wait: the words went out «inline» while the send waited for the verdict. Now one state decides all three: while the
verdict is unknown or in the band, the words and the tags wait with the calls for `settle` (the stream's end), which
awaits the brief off the loop — up to Jev's own timeout when what waits LEAVES. Which tag leaves is read from what is
declared (the app's act, the grammar's own), never from a prefix. Disarm: `decided` reading unknown or the band as
«inline», `tags` not holding, `settle` not holding a leaving tag, `gate` running a call on a verdict in flight → red.
"""
from __future__ import annotations

import asyncio
import threading
import time

from nucleo.flash import follow_up_pass as FP
from nucleo.turn import brief as tb
from nucleo.turn import route_by_verdict as R

ORDER = "Contéstale a Raquel que sí"


def _brief(choice=None, conf=0.0, ready=True):
    ev = threading.Event()
    if ready:
        ev.set()
    res = {"_call_id": "t", tb.ESCALATE_KEY: {"choice": choice, "confidence": conf, "probs": {}}} if choice else {}
    return {"event": ev, "turn_id": "t", "result": res if ready else None}


def _land(brief, choice, conf, after_s):
    def _go():
        time.sleep(after_s)
        brief["result"] = {"_call_id": "t", tb.ESCALATE_KEY: {"choice": choice, "confidence": conf, "probs": {}}}
        brief["event"].set()
    threading.Thread(target=_go, daemon=True).start()


def _turn(brief, wait=0.0):
    """One turn's decision, wired as the pipeline wires it: the Hold, the gate and the tag emitter share it."""
    sent, ran, tags, req = [], [], [], {"v": None, "more": [], "surface": {}}
    d = R.Turn(brief, req, ORDER, lambda *a, **k: None, time.monotonic(), wait)
    hold = FP.Hold(brief, sent.append, route_wait_s=wait, decision=d)
    call = d.gate(lambda n, a: ran.append(n) or "ran")
    tag = d.tags(lambda *a, **k: tags.append(a[0]))
    return d, hold, call, tag, sent, ran, tags, req


def test_band_words_wait_for_the_stream_end():
    sent = []
    FP.Hold(_brief("escalate", 0.55), sent.append).say("Ya le he contestado a Raquel.")
    assert sent == [], "words in the band were said before the model's calls could hold the send"


def test_a_leaving_call_in_the_band_takes_its_words_and_tags_with_it():
    _d, hold, call, tag, sent, ran, tags, req = _turn(_brief("escalate", 0.55))
    hold.say("¡Enviado! ")
    tag("show", {"id": "mensajeria"})
    assert sent == [] and tags == [], "words or tags ran before the call that decides them"
    assert call("reply_message", {"text": "Sí"}) is None and ran == []
    asyncio.run(hold.release([], (), lambda *a, **k: None))
    assert sent == [] and tags == [] and hold.routed and req["routed"], "words or tags of a held send were released"


def test_the_band_without_a_leaving_call_says_its_words_and_runs_its_tags_at_the_end():
    _d, hold, call, tag, sent, ran, tags, req = _turn(_brief("escalate", 0.55))
    hold.say("Cuesta unos 30 euros.")
    tag("show", {"id": "busqueda"})
    call("web_search", {"query": "precio"})        # behind the held tag: what waits runs in the order it was written
    assert sent == [] and tags == [] and ran == [] and not req.get("routed")
    asyncio.run(hold.release([], (), lambda *a, **k: None))
    assert "".join(sent) == "Cuesta unos 30 euros." and tags == ["show"] and ran == ["web_search"] and not hold.routed


def test_a_held_tag_that_leaves_is_held_like_the_call_it_stands_for():
    _d, hold, _call, tag, sent, _ran, tags, req = _turn(_brief("escalate", 0.55))
    hold.say("Hecho.")
    tag("cluster.send", {"name": "amigos", "data": {"to": "*", "text": "Sí"}})
    asyncio.run(hold.release([], (), lambda *a, **k: None))
    assert tags == [] and sent == [] and req["routed"], "an inline send in the band left without the hold"
    assert req["held_calls"][0]["name"] == "cluster.send"


def test_a_tag_that_only_looks_at_the_inbox_is_no_send():
    """`[[msg.open:2]]` opens a chat: the messaging app declares it does not leave — the band lets it run."""
    _d, hold, _call, tag, sent, _ran, tags, req = _turn(_brief("escalate", 0.55))
    hold.say("Hecho.")
    tag("msg.open", {"n": 2})
    asyncio.run(hold.release([], (), lambda *a, **k: None))
    assert tags == ["msg.open"] and "".join(sent) == "Hecho." and not req.get("routed")


def test_outside_the_band_nothing_waits():
    for choice, conf, said, n_tags in (("handle_inline", 0.9, True, 1), ("escalate", 0.4, True, 1),
                                       ("escalate", 0.7, False, 0)):
        _d, hold, _call, tag, sent, _ran, tags, _req = _turn(_brief(choice, conf))
        hold.say("Vale.")
        tag("show", {"id": "x"})
        assert bool(sent) == said and len(tags) == n_tags, (choice, conf)


def test_a_leaving_call_waits_for_a_brief_in_flight_and_its_words_and_tags_wait_with_it():
    """Past the route wait, with the brief still in flight: «¡Enviado!» was said while the send waited (audit P1-1)."""
    brief = _brief(ready=False)
    _d, hold, call, tag, sent, ran, tags, req = _turn(brief, wait=0.0)
    hold.say("¡Enviado! ")
    tag("show", {"id": "mensajeria"})
    t = time.monotonic()
    assert call("reply_message", {"text": "Sí"}) is None and ran == [], "a send ran on a verdict still on its way"
    assert time.monotonic() - t < 0.2, "the call blocked the loop"
    assert sent == [] and tags == [], "words or tags went out on a verdict still on its way"
    _land(brief, "escalate", 0.55, 0.2)
    asyncio.run(hold.release([], (), lambda *a, **k: None))
    assert ran == [] and sent == [] and tags == [] and req["routed"] and hold.routed


def test_a_call_that_stays_never_waits_on_the_loop_and_follows_the_verdict():
    """Audit P2-2: a call met with the brief in flight is decided at `settle`, never awaited inside the stream."""
    for choice, conf, runs in (("escalate", 0.7, False), ("handle_inline", 0.9, True)):
        brief = _brief(ready=False)
        _d, hold, call, _tag, sent, ran, _tags, req = _turn(brief, wait=2.0)
        t = time.monotonic()
        assert call("web_search", {"query": "x"}) is None and time.monotonic() - t < 0.2, "the call blocked the loop"
        _land(brief, choice, conf, 0.1)
        asyncio.run(hold.release([], (), lambda *a, **k: None))
        assert (ran == ["web_search"]) == runs and bool(req.get("routed")) != runs, (choice, conf)


def test_a_verdict_that_lands_mid_stream_releases_the_words_at_once():
    brief = _brief(ready=False)
    _d, hold, _call, _tag, sent, _ran, _tags, _req = _turn(brief, wait=0.0)
    hold.say("Cuesta ")
    assert sent == []
    _land(brief, "handle_inline", 0.95, 0.0)
    time.sleep(0.05)
    hold.say("unos 30 euros.")
    assert "".join(sent) == "Cuesta unos 30 euros.", "inline words waited for the stream's end"


def test_words_already_said_are_never_routed_after_them():
    """Audit P2-1: once his reply was said, a later routing (a held call) never drops what is already out."""
    d, hold, _call, _tag, sent, _ran, _tags, req = _turn(_brief("handle_inline", 0.9))
    hold.say("Vale.")
    req["routed"] = True
    asyncio.run(hold.release([], (), lambda *a, **k: None))
    assert "".join(sent) == "Vale." and hold.routed is False


def test_a_leaving_call_runs_once_its_verdict_lands_inline():
    brief = _brief(ready=False)
    _d, hold, call, _tag, _sent, ran, _tags, req = _turn(brief, wait=0.0)
    call("reply_message", {"text": "Sí"})
    _land(brief, "handle_inline", 0.9, 0.2)
    asyncio.run(hold.release([], (), lambda *a, **k: None))
    assert ran == ["reply_message"] and not req.get("routed")


def test_a_verdict_that_never_comes_is_no_verdict_and_the_call_runs_into_its_task(monkeypatch):
    monkeypatch.setenv("ZAELAR_JEV_TIMEOUT_MS", "200")
    _d, hold, call, _tag, _sent, ran, _tags, req = _turn(_brief(ready=False), wait=0.0)
    call("reply_message", {"text": "Sí"})
    t = time.monotonic()
    asyncio.run(hold.release([], (), lambda *a, **k: None))
    assert ran == ["reply_message"] and not req.get("routed")
    assert 0.1 < time.monotonic() - t < 1.0, "the wait is Jev's own timeout"


def test_what_waited_runs_in_the_order_the_model_wrote_it():
    """Audit L2b P2-A: what waited for the verdict ran AFTER what came once it landed («open chat 2 and mark it read»
    marked read on the wrong chat, then opened). One queue, emptied in order the moment the verdict lands."""
    brief = _brief(ready=False)
    order, req = [], {"v": None, "more": [], "surface": {}}
    d = R.Turn(brief, req, ORDER, lambda *a, **k: None, time.monotonic(), 0.0)
    hold = FP.Hold(brief, lambda _t: None, decision=d)
    call, tag = d.gate(lambda n, a: order.append(n)), d.tags(lambda *a, **k: order.append(a[0]))
    tag("msg.open", {"n": 2})
    call("web_search", {"query": "x"})
    _land(brief, "handle_inline", 0.95, 0.0)
    time.sleep(0.05)
    tag("msg.read", {"n": 1})
    call("show_widget", {"widget_id": "agenda"})
    asyncio.run(hold.release([], (), lambda *a, **k: None))
    assert order == ["msg.open", "web_search", "msg.read", "show_widget"], order


def test_a_call_leaked_as_text_crosses_the_same_gate():
    """Audit L2b P2-B: a call the model wrote as JSON text (`json_leak_dropped`) is a model call — in the band a leaked
    send is held like the called one, its «Sent.» unsaid. The executor's late seam is the gated call."""
    d, hold, call, tag, sent, ran, tags, req = _turn(_brief("escalate", 0.55))
    late = {"on_tool_call": call}                       # what `pipeline` binds: `_tx.late["on_tool_call"] = gate(...)`
    leaked = d.tags(lambda action, extra: late["on_tool_call"]("reply_message", {"text": "Sí"}))
    hold.say("Enviado.")
    leaked("json_leak_dropped", {"text": '{"name": "reply_message", "arguments": {"text": "Sí"}}'})
    asyncio.run(hold.release([], (), lambda *a, **k: None))
    assert ran == [] and sent == [] and req["routed"], "a leaked send left without the hold"
    src = open("nucleo/turn/pipeline.py", encoding="utf-8").read()
    assert '_tx.late["on_tool_call"] = _decision.gate(_tx.on_tool_call)' in src


def _grammar_tags() -> set:
    """Every tag name the grammar emits: the literal names `strip_tags` hands its emitter, plus the alternations of the
    three patterns whose name is read from the match (`TAG_RE`, `cluster.` + `CX_CTRL_RE`, `msg.` + `MSG_RE`)."""
    import ast
    import re
    from voice import tag_protocol as tp
    src = open(tp.__file__, encoding="utf-8").read()
    names = {n.args[0].value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "emit_fn" and n.args and isinstance(n.args[0], ast.Constant)}
    for prefix, rx in (("", tp.TAG_RE), ("cluster.", tp.CX_CTRL_RE), ("msg.", tp.MSG_RE)):
        names |= {prefix + w for w in re.search(r"\(([a-z|]+)\)", rx.pattern).group(1).split("|")}
    return names


def test_every_tag_of_the_grammar_has_a_declared_answer_on_whether_it_leaves():
    """Audit L2b P2-C: which tag leaves is DECLARED — the grammar names each tag's owner, a connector's catalog the
    effects of its tags, a card's manifest the act a `msg.*` tag is — never a list in the router."""
    from nucleo.flash import tag_effects as TE
    from widgets import runtime
    assert _grammar_tags() == set(TE.owners()), "a tag the grammar emits has no declared owner (or a stale one)"
    for tag_name, owner in TE.owners().items():
        kind, _s, who = owner.partition(":")
        assert kind in ("canvas", "engine", "call", "app", "connector"), owner
        if kind == "connector":
            assert tag_name in TE.connector_tags(who), f"{who}'s catalog says nothing of {tag_name}"
        if kind == "app" and who:
            assert tag_name.split(".", 1)[1] in (runtime.get(who) or {}).get("actions", {}), f"{who} has no {tag_name}"
    leaving = {t for t in TE.owners() if TE.leaves(t, {})}
    assert {"cluster.send", "cluster.pact", "cluster.connect", "architect.ask", "architect.new"} <= leaving
    assert not leaving & {"msg.open", "msg.read", "cluster.done", "show", "close", "cron.create"}, leaving
    assert TE.leaves("widget.data", {"id": "mensajeria", "data": {"action": "reply"}})
    assert TE.leaves("widget.data", {"id": "mensajeria", "data": [1, 2]}) is False, "a non-dict body broke the read"


def test_a_brief_without_its_event_never_breaks_the_turn():
    """Audit L2b P3: an unawaitable brief reads as in flight (no verdict), never an exception that errors the turn."""
    class Unawaitable:
        def is_set(self):
            return False                                # in flight, and its `wait` is missing
    d = R.Turn({"event": Unawaitable(), "result": None}, {}, ORDER, None, time.monotonic(), 0.3)
    assert asyncio.run(d.settle()) is False


def test_the_pipeline_hands_one_decision_to_the_calls_the_words_and_the_tags():
    src = open("nucleo/turn/pipeline.py", encoding="utf-8").read()
    assert "_decision.gate(_tx.on_tool_call)" in src and "_decision.tags(_tx.tag_emit)" in src and "_decision=_decision" in src
    assert "decision=_decision" in open("nucleo/turn/pipeline_stream.py", encoding="utf-8").read()


def test_a_stream_that_is_cut_or_fails_drops_what_waited_and_says_so():
    """L2 P3-1: a barge-in or an error skips `settle` — what waited in the queue never runs, and the drop is said (the
    cut's own event carries the count; a failure says it here)."""
    brief = _brief(ready=False)
    d, hold, call, tag, _sent, ran, tags, _req = _turn(brief)
    call("reply_message", {"text": "Sí"})
    tag("show", {"id": "mensajeria"})
    events = []
    assert FP.drop_held(hold, lambda *a, **k: events.append(k.get("extra")), "error") == 2
    assert ran == [] and tags == [] and d.cut and d.queue == [] and events[0]["dropped"] == 2
    assert FP.drop_held(hold) == 0, "a queue is dropped once"
    _land(brief, "handle_inline", 0.95, 0.0)                    # the brief lands: a late call would now run at once
    time.sleep(0.05)
    call("show_widget", {"widget_id": "agenda"})                # the `finally` fires a late call after the cut
    tag("show", {"id": "agenda"})
    assert ran == [] and tags == [], "a call after the cut ran (audit L3 P2-2)"
