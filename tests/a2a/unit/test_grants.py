"""T571 · generic grants: items × audience × verbs × expiry, default deny."""
from __future__ import annotations

import pytest

from a2a.grants import Grants, JsonGrantStore
from a2a.items import Item, default_items


@pytest.fixture
def g(tmp_path, clock):
    items = default_items(busy=lambda a, b: [{"start": "10", "end": "11", "title": "dentist"}])
    items.declare(Item("shopping", "collection", "lists", "list.items/1", ("see", "append", "edit"),
                       {"default": lambda a: [{"text": "milk"}]}))
    items.declare(Item("rides", "widget-data", "activity", "activity.route/1", ("see", "copy")))
    return Grants(JsonGrantStore(tmp_path), items, clock=clock, groups=lambda cid: ["family"] if cid == "marta" else [])


def test_no_row_no_access(g):
    assert g.allowed("marta", "calendar", "see").reason == "no_row"


def test_a_grant_gives_only_its_verbs_and_dies_at_expiry(g, clock):
    g.grant("shopping", "contact:marta", ["see", "append"], expires_at=clock() + 60)
    assert g.allowed("marta", "shopping", "append").allowed
    assert g.allowed("marta", "shopping", "edit").reason == "verb"
    assert g.allowed("pablo", "shopping", "see").reason == "no_row"
    clock.advance(61)
    assert g.allowed("marta", "shopping", "see").reason == "expired"
    assert [x.item for x in g.sweep()] == ["shopping"]


def test_selector_group_and_network_audiences(g):
    g.grant("kind:widget-data,widget:activity", "group:family", ["see"])
    assert g.allowed("marta", "rides", "see").allowed
    assert not g.allowed("pablo", "rides", "see").allowed
    g.grant("profile", "network", ["see"])
    assert g.allowed("pablo", "profile", "see").allowed


def test_a_verb_the_item_does_not_support_cannot_be_granted(g):
    with pytest.raises(ValueError):
        g.grant("calendar", "contact:marta", ["edit"])
    with pytest.raises(ValueError):
        g.grant("calendar", "somebody", ["see"])


def test_revoke_removes_the_row(g):
    g.grant("calendar", "contact:marta", ["see"])
    assert len(g.revoke("calendar", "contact:marta")) == 1
    assert not g.allowed("marta", "calendar", "see").allowed


def test_the_policy_seam_can_only_narrow(g):
    g.grant("calendar", "contact:marta", ["see"])
    g.policy = lambda cid, item, verb: "never"
    assert g.allowed("marta", "calendar", "see").reason == "policy_never"
    g.policy = lambda cid, item, verb: None
    assert g.allowed("marta", "calendar", "see").allowed


def test_never_shareable_items_cannot_be_declared():
    for bad in ("memory", "vault", "credentials", "rules", "state", "diary"):
        with pytest.raises(ValueError):
            Item(bad, "collection", "x", "s/1", ("see",))


def test_freebusy_projection_carries_intervals_only(g):
    out = g.items.get("calendar").read("freebusy", {"from": "a", "to": "b"})
    assert out == [{"start": "10", "end": "11"}]
