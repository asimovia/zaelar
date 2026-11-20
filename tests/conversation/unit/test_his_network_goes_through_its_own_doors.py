"""His network goes through its own doors (node 13.131, INI-078 F2 step 7c, row 28): joining a cluster waits for his yes
on the Clusters tab's row through the one asker, never connects by itself; a message to a cluster leaves by the bridge's
one tag door (its outbound guard and his consent rule), and one it held is said as asked, never as sent; with several
clusters and none named it asks which; a friend's agent is reached by name among his accepted relationships; what the
network holds is the `network` topic of `read_state`, read when named."""
from __future__ import annotations

import asyncio

from nucleo.conversation_host import acts_network


def test_joining_a_cluster_asks_his_yes_on_its_row_and_connects_nothing(monkeypatch):
    from connectors import meshkore
    from nucleo.request import consent_ask
    asked, dispatched = [], []
    monkeypatch.setattr(consent_ask, "ask_consent", lambda w, k, p, q, **kw: asked.append((w, kw.get("kind"),
                        kw["op"]["action"], kw["op"]["payload"].get("vis"))) or ("row1", "a1"))
    monkeypatch.setattr(meshkore, "dispatch_tag", lambda *a: dispatched.append(a))
    got = asyncio.run(acts_network.run("connect", {"cluster_id": "c_0001", "name": "w_team"}))
    assert got.data["waits_for"] == "his yes" and dispatched == []
    assert asked == [("clusters", "cluster", "connect_cluster", "public")]       # an id with no token: an open cluster
    assert asyncio.run(acts_network.run("connect", {"name": "w_team"})).status == "failed" and len(asked) == 1


def test_a_cluster_message_leaves_by_the_tag_door_and_a_held_one_is_said_as_asked(monkeypatch):
    from connectors import meshkore
    sent = []

    async def door(action, extra):
        sent.append((action, extra))
        return extra["data"]["text"] if extra["name"] == "w_open" else None
    monkeypatch.setattr(meshkore, "dispatch_tag", door)
    monkeypatch.setattr(acts_network, "_clusters", lambda: [{"name": "w_open", "connected": True}])
    got = asyncio.run(acts_network.run("send", {"text": "w_hello", "to": "w_peer"}))
    assert got.status == "ok" and got.data["sent_to"] == "w_open"
    assert sent == [("cluster.send", {"name": "w_open", "data": {"text": "w_hello", "to": "w_peer"}})]
    monkeypatch.setattr(acts_network, "_asked_on_the_tab", lambda: True)
    held = asyncio.run(acts_network.run("send", {"text": "w_x", "cluster": "w_held"}))
    assert "sent_to" not in held.data and "asked" in held.data
    monkeypatch.setattr(acts_network, "_clusters", lambda: [{"name": "a", "connected": True}, {"name": "b",
                                                                                               "connected": True}])
    assert asyncio.run(acts_network.run("send", {"text": "w_x"})).data["reason"] == "which cluster" and len(sent) == 2


def test_a_friends_agent_is_reached_by_name_and_the_network_is_a_topic(monkeypatch):
    import a2a
    from nucleo import consent

    class Rel:
        def __init__(self, name):
            self.name, self.status, self.did, self.contact_id = name, "accepted", f"d_{name}", f"c_{name}"

    class Agent:
        rels = type("R", (), {"all": staticmethod(lambda: [Rel("W_Marta")])})
        out: list = []

        def send(self, did, text):
            self.out.append((did, text))
            return True

        def sharing(self, did):
            return []

        def inbox(self, did=None):
            return []
    agent = Agent()
    monkeypatch.setattr(a2a, "runtime", lambda: agent)
    monkeypatch.setattr(consent, "decide_act", lambda *a, **k: {"verdict": "act"})
    monkeypatch.setattr(consent, "asks", lambda v: False)
    assert asyncio.run(acts_network.run("a2a_send", {"to": "w_marta", "text": "w_hi"})).status == "ok"
    assert agent.out == [("d_W_Marta", "w_hi")]
    assert asyncio.run(acts_network.run("a2a_send", {"to": "w_nobody", "text": "w_x"})).data["error"] == "not_connected"
    from nucleo.conversation_host import memory_read
    monkeypatch.setattr(acts_network, "_clusters", lambda: [{"name": "w_team", "connected": True, "online": ["w_zalo"]}])
    facts = memory_read.topic("network")
    assert "cluster w_team: connected, online: w_zalo" in facts and "W_Marta" in facts
