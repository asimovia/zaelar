"""A phrase the action map knows VERBATIM runs before the model (node 13.134, V2-942 A2, INI-078 F2 step 7b): the
package offers the batch's words to the host's `Shortcut` first — an exact hit runs its act, its line is said, the run
ends with `actionmap` as its origin and neither the open doors (`Route`) nor the model are asked; no hit, or a shortcut
that fails, and the words go on to the doors and the model as if it did not exist. The host's shortcut is the action
map's own exact lookup and act (its switches its own), and what it says is the act's receipt or a short ack his style
allows."""
from __future__ import annotations

import asyncio

import pytest

from conversation.ports import Done
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness


class _Door:
    def __init__(self, line):
        self.line, self.seen = line, []

    async def take(self, account, text):
        self.seen.append(text)
        if isinstance(self.line, Exception):
            raise self.line
        return self.line


def _with(store, shortcut, route):
    h = Harness(store, grace=False)
    h.conv.shortcut, h.conv.route = shortcut, route
    h.model.default = lambda ids: [reply("w9"), Done()]
    return h


def test_an_exact_hit_runs_before_the_doors_and_the_model(store):
    shortcut, route = _Door("w_done"), _Door("w_heard")
    h = _with(store, shortcut, route)
    h.utter([(["w_close", "w_music"], 0)])
    h.settle(3000)
    assert shortcut.seen == ["w_close w_music"] and route.seen == [] and not h.model.calls
    assert [o.text for o in h.mouth.orders] == ["w_done"]
    commands = [p.get("command") for k, lab, p in h.tel.events if k == "conv_run" and lab == "command"]
    assert commands == ["actionmap"]


@pytest.mark.parametrize("line", [None, OSError("w_down")], ids=["no_hit", "failing"])
def test_no_hit_goes_on_to_the_doors_and_the_model(store, line):
    shortcut, route = _Door(line), _Door(None)
    h = _with(store, shortcut, route)
    h.typed("w1", 0)
    h.settle(3000)
    assert shortcut.seen == ["w1"] and route.seen == ["w1"] and len(h.model.calls) == 1


def test_the_hosts_shortcut_is_the_maps_exact_lookup_and_act(monkeypatch):
    from i18n import langs
    from nucleo import actionmap, style_policy
    from nucleo.conversation_host import shortcut
    from nucleo.flash import bulk_close
    ran = []
    monkeypatch.setattr(actionmap, "enabled", lambda: True)
    monkeypatch.setattr(actionmap, "match_spoken", lambda t: {"id": 4, "action": {"do": "close", "widget": "w_music"}}
                        if t == "w_close the music" else None)
    monkeypatch.setattr(actionmap, "execute", lambda hit, emit, phrase="": ran.append((hit["id"], phrase)) or True)
    monkeypatch.setattr(bulk_close, "take_receipt", lambda **k: "")
    monkeypatch.setattr(style_policy, "confirm_short_actions", lambda: True)
    monkeypatch.setattr(langs, "pick_ack", lambda last="", code=None: "w_ok")
    take = shortcut.HostShortcut().take
    assert asyncio.run(take("a", "w_close the music")) == "w_ok" and ran == [(4, "w_close the music")]
    assert asyncio.run(take("a", "w_close the music please")) is None and len(ran) == 1      # verbatim, or nothing
    monkeypatch.setattr(style_policy, "confirm_short_actions", lambda: False)
    assert asyncio.run(take("a", "w_close the music")) == ""                                # ran, said nothing
    monkeypatch.setattr(actionmap, "enabled", lambda: False)
    assert asyncio.run(take("a", "w_close the music")) is None and len(ran) == 2


def _run(listen, said, effects, outcome="answered", reads=0, run="r1"):
    refs = {"refs": {"run": run}}
    listen("conv_run", "input", {**refs, "text": [said]})
    for _ in range(reads):
        listen("conv_effect", "read", {**refs, "tool": "read_widget"})
    for tool, state in effects:
        listen("conv_effect", "submitted", {**refs, "tool": tool})
        listen("conv_effect", "receipt", {**refs, "state": state})
    listen("conv_run", "ended", {**refs, "outcome": outcome})


def test_the_map_learns_from_a_run_whose_only_effect_was_one_declared_canvas_act(monkeypatch):
    """V2-942 T8: a run that answered him with ONE declared canvas act, accepted, and nothing read is the map's candidate,
    origin `conversation`; two acts, a read, a refused act, an act of another door or a failed run are not."""
    from nucleo.actionmap import watch
    from nucleo.conversation_host import shortcut
    seen = []
    monkeypatch.setattr(watch, "candidate", lambda user, action, origin: seen.append((user, action, origin)))
    _run(shortcut.listen, "w_open the agenda", [("show_widget", "provider_accepted")])
    assert seen == [("w_open the agenda", "canvas:show", "conversation")]
    _run(shortcut.listen, "w_x", [("show_widget", "provider_accepted"), ("close_widget", "provider_accepted")])
    _run(shortcut.listen, "w_x", [("show_widget", "provider_accepted")], reads=1)
    _run(shortcut.listen, "w_x", [("show_widget", "rejected")])
    _run(shortcut.listen, "w_x", [("start_task", "provider_accepted")])
    _run(shortcut.listen, "w_x", [("close_widget", "provider_accepted")], outcome="failed")
    assert len(seen) == 1 and shortcut._runs == {}


def test_a_candidate_is_logged_with_its_origin_and_whether_an_entry_already_knew_it(monkeypatch):
    from nucleo import actionmap
    from nucleo.actionmap import watch
    from voice import observer
    logged = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **k: logged.append((kind, k["extra"])))
    monkeypatch.setattr(actionmap, "enabled", lambda: True)
    monkeypatch.setattr(actionmap, "match", lambda t: {"id": 1} if t == "w_known" else None)
    assert watch.candidate("w_open the agenda", "canvas:show", "conversation")
    assert watch.candidate("w_known", "canvas:close", "conversation")
    assert [(k, e["origin"], e["action"], e["known_entry"]) for k, e in logged] == [
        ("actionmap", "conversation", "canvas:show", False), ("actionmap", "conversation", "canvas:close", True)]
    monkeypatch.setattr(actionmap, "enabled", lambda: False)
    assert not watch.candidate("w_x", "canvas:show", "conversation") and len(logged) == 2
