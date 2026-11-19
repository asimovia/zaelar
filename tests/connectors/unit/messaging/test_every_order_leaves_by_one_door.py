"""The exit door (`connectors/exit.py`): an order leaves with the lane that asked for it, is counted, and is held —
answered as «not sent», never published — when the lane is unknown or the switch says so."""
import bus
import pytest

from connectors import exit as door
from connectors.messaging import group_leave, ingest

OUT_TOPICS = {door.SEND: ingest.TOPIC_SEND, door.REPLY: ingest.TOPIC_REPLY, door.GROUP: ingest.TOPIC_GROUP,
              door.GROUP_LEAVE: group_leave.TOPIC_GROUP_LEAVE}


@pytest.fixture
def world(monkeypatch):
    """Every outbound topic and the failure topic, listened to; a clean count; the switch off."""
    monkeypatch.delenv(door.ENV, raising=False)
    door._reset_counters()
    subs = {t: bus.subscribe(t) for t in [*OUT_TOPICS.values(), ingest.TOPIC_SEND_FAILED]}

    def seen(topic):
        got = []
        while True:
            try:
                got.append(subs[topic].queue.get_nowait())
            except Exception:  # noqa: BLE001 — empty
                return got
    yield seen
    for s in subs.values():
        s.close()


def _order(lane="owner", **over):
    return {"ref": "r-1", "platform": "telegram", "to": "1000000017", "text": "hello", "lane": lane, **over}


@pytest.mark.parametrize("kind", door.KINDS)
def test_a_labelled_order_goes_out_on_its_own_topic_and_is_counted(world, kind):
    assert door.leave(kind, _order()) is True
    assert [o["ref"] for o in world(OUT_TOPICS[kind])] == ["r-1"]
    assert world(ingest.TOPIC_SEND_FAILED) == []
    assert door.counters() == {f"{kind}/owner/out": 1}


@pytest.mark.parametrize("lane", ["", "somebody", None])
def test_an_order_with_no_declared_lane_is_held_and_answered_as_not_sent(world, lane):
    assert door.leave(door.SEND, _order(lane=lane)) is False
    assert world(ingest.TOPIC_SEND) == []
    failed = world(ingest.TOPIC_SEND_FAILED)
    assert [f["ref"] for f in failed] == ["r-1"] and failed[0]["reason"] == "held:unlabelled"
    assert door.counters() == {"send/unlabelled/held": 1}


@pytest.mark.parametrize("value", ["all", "1", "TRUE", " on "])
def test_the_switch_holds_every_lane_and_every_kind(world, monkeypatch, value):
    monkeypatch.setenv(door.ENV, value)
    for lane in sorted(door.LANES):
        assert door.held(lane) == door.SWITCH
    for kind in door.KINDS:
        assert door.leave(kind, _order(lane="hand")) is False
        assert world(OUT_TOPICS[kind]) == []
    assert len(world(ingest.TOPIC_SEND_FAILED)) == len(door.KINDS)
    assert set(door.counters().values()) == {1} and all(k.endswith("/hand/held") for k in door.counters())


def test_a_list_holds_only_the_lanes_it_names(world, monkeypatch):
    monkeypatch.setenv(door.ENV, "errand, mandate")
    assert door.leave(door.SEND, _order(lane="errand")) is False
    assert door.leave(door.SEND, _order(lane="mandate", ref="r-2")) is False
    assert door.leave(door.SEND, _order(lane="owner", ref="r-3")) is True
    assert [o["ref"] for o in world(ingest.TOPIC_SEND)] == ["r-3"]
    assert [f["reason"] for f in world(ingest.TOPIC_SEND_FAILED)] == ["held:lane:errand", "held:lane:mandate"]
    assert door.counters() == {"send/errand/held": 1, "send/mandate/held": 1, "send/owner/out": 1}


def test_a_switch_that_names_something_that_is_not_a_lane_holds_everything(world, monkeypatch):
    monkeypatch.setenv(door.ENV, "erand")          # a typo is never «off»
    assert door.held("owner") == door.SWITCH
    assert door.leave(door.SEND, _order()) is False and world(ingest.TOPIC_SEND) == []


def test_the_switch_is_read_at_every_use(world, monkeypatch):
    assert door.leave(door.REPLY, _order()) is True
    monkeypatch.setenv(door.ENV, "all")
    assert door.leave(door.REPLY, _order(ref="r-2")) is False
    monkeypatch.delenv(door.ENV)
    assert door.leave(door.REPLY, _order(ref="r-3")) is True
    assert [o["ref"] for o in world(ingest.TOPIC_REPLY)] == ["r-1", "r-3"]


def test_the_early_question_answers_with_the_reason_and_counts_once(world, monkeypatch):
    assert door.check("invite", "invite") == ""
    assert door.counters() == {}                    # an act that may go on is counted when it LEAVES
    monkeypatch.setenv(door.ENV, "invite")
    why = door.check("invite", "invite")
    assert why == "held:lane:invite" and door.is_held(why)
    assert door.check("form", "nobody") == "held:unlabelled"
    assert door.counters() == {"invite/invite/held": 1, "form/unlabelled/held": 1}
    assert world(ingest.TOPIC_SEND_FAILED) == []    # nothing was queued: there is no order to answer


def test_the_record_never_carries_the_text_nor_who_it_is_for(world, monkeypatch):
    seen = []
    import voice.observer as observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: seen.append((kind, label, kw)))
    door.leave(door.SEND, _order(text="the secret plan", to="quinn@example.com", name="Quinn"))
    monkeypatch.setenv(door.ENV, "all")
    door.leave(door.SEND, _order(text="the secret plan", to="quinn@example.com", name="Quinn"))
    assert [k for k, _l, _kw in seen] == ["consequence", "consequence"]
    blob = repr(seen)
    assert "secret plan" not in blob and "quinn" not in blob.lower()
    assert seen[0][2]["extra"] == {"door": "exit", "exit": "send", "lane": "owner", "outcome": "out",
                                   "ref": "r-1", "platform": "telegram"}
    assert seen[1][2]["extra"]["outcome"] == "held" and seen[1][2]["extra"]["why"] == "switch"


def test_an_unknown_kind_is_a_programming_error_never_a_silent_send(world):
    with pytest.raises(ValueError):
        door.leave("carrier-pigeon", _order())
