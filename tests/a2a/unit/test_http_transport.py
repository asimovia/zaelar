"""T576/T577 · the HTTP clients against the real contracts (HTTP mocked): encoded DID path signed as sent,
204 = empty, 5xx retried, 4xx raised, live samples by bearer token, no signature."""
from __future__ import annotations

import json

import httpx
import pytest

from a2a.discovery import HttpDirectory
from a2a.identity import Identity, verify_mk_sig
from a2a.transport.base import TransportError
from a2a.transport.http import SignedHttp
from a2a.transport.live import HttpLive
from a2a.transport.mailbox import HttpMailbox


def _http(me, handler, **kw):
    return SignedHttp(me, base="https://mesh.test", client=httpx.Client(transport=httpx.MockTransport(handler)),
                      sleep=lambda s: None, **kw)


def test_post_mail_signs_the_percent_encoded_path():
    me, peer = Identity.generate(), Identity.generate()
    got = {}

    def h(req):
        path = req.url.raw_path.decode()
        got["path"] = path
        verify_mk_sig(req.headers["meshkore-sig"], "POST", path, req.content.decode(), expected_pub_b64=me.pub_b64)
        return httpx.Response(201, json={"seq": 4})
    mb = HttpMailbox(_http(me, h))
    assert mb.post(peer.did, {"kind": "msg.text", "x": 1}) == 4
    assert got["path"].startswith("/v1/mail/did%3Akey%3A") and "/" not in got["path"][len("/v1/mail/"):]
    assert "+" not in got["path"][len("/v1/mail/"):] or "%2B" in got["path"]


def test_pull_204_is_empty_and_rows_are_parsed():
    me = Identity.generate()
    answers = iter([httpx.Response(204), httpx.Response(200, json=[{"seq": 3, "from_did": "did:key:x", "ts": 9,
                                                                     "body": {"kind": "msg.text"}}])])

    def h(req):
        assert req.url.path == "/v1/mail"
        verify_mk_sig(req.headers["meshkore-sig"], "GET", "/v1/mail", "", expected_pub_b64=me.pub_b64)
        return next(answers)
    mb = HttpMailbox(_http(me, h))
    assert mb.pull(after=2) == []
    m = mb.pull(after=2)[0]
    assert (m.seq, m.from_did, m.body["kind"]) == (3, "did:key:x", "msg.text")


def test_5xx_is_retried_4xx_is_raised_with_status():
    me = Identity.generate()
    calls = []

    def h(req):
        calls.append(req.headers["meshkore-sig"].split()[3])
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={"acked_upto": 5})
    assert HttpMailbox(_http(me, h)).ack(5) == 5
    assert len(calls) == 2 and calls[0] != calls[1]                 # a fresh nonce per attempt

    def forbid(req):
        return httpx.Response(403, json={"error": "no relationship: only connect.request or external.* may be sent"})
    with pytest.raises(TransportError) as e:
        HttpMailbox(_http(me, forbid)).post(me.did, {"kind": "msg.text"})
    assert e.value.status == 403


def test_a_dead_host_fails_with_status_zero():
    me = Identity.generate()

    def dead(req):
        raise httpx.ConnectError("down")
    with pytest.raises(TransportError) as e:
        HttpMailbox(_http(me, dead)).pull()
    assert e.value.status == 0


def test_people_publish_and_lookup_shapes():
    me = Identity.generate()

    def h(req):
        b = json.loads(req.content or b"{}")
        if req.url.path == "/v1/people/me":
            assert req.method == "PUT" and len(b["hashes"]) <= 16
            return httpx.Response(200, json={"hashes": len(b["hashes"])})
        assert req.url.path == "/v1/people/lookup"
        return httpx.Response(200, json=[{"hash": b["hashes"][0], "did": "did:key:p", "agent_id": "p1"}])
    d = HttpDirectory(_http(me, h))
    assert d.publish(["a" * 64] * 20) == 16
    assert d.lookup(["b" * 64])[0]["agent_id"] == "p1"


def test_live_open_is_signed_and_samples_go_by_bearer_only():
    me, peer = Identity.generate(), Identity.generate()

    def h(req):
        p = req.url.raw_path.decode().split("?")[0]
        if p.startswith("/v1/live/did"):
            verify_mk_sig(req.headers["meshkore-sig"], "POST", p, req.content.decode(), expected_pub_b64=me.pub_b64)
            assert json.loads(req.content) == {"ttl_s": 600, "ring": 100}
            return httpx.Response(201, json={"share_id": "s1", "push_token": "pt", "expires_at": 99, "ring": 100})
        assert "meshkore-sig" not in req.headers
        if req.method == "POST":
            assert req.headers["authorization"] == "Bearer pt"
            return httpx.Response(200, json={"seq": 1})
        if req.method == "GET":
            assert req.headers["authorization"] == "Bearer rt" and req.url.params["after"] == "0"
            return httpx.Response(200, json={"samples": [{"seq": 1, "ts": 5, "body": {"x": 1}}], "cursor": 1,
                                             "expires_at": 99, "closed": False})
        return httpx.Response(200, json={"ok": True})
    lv = HttpLive(_http(me, h))
    s = lv.open(peer.did, ttl_s=600, ring=100)
    assert (s.share_id, s.push_token) == ("s1", "pt")
    assert lv.push("s1", "pt", {"x": 1}) == 1
    assert lv.read("s1", "rt")["cursor"] == 1
    lv.close("s1", "pt")
