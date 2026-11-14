"""T569 · identity + envelope: sign/verify, E2E, replay, skew, size."""
from __future__ import annotations

import pytest

from a2a.envelope import Envelope, EnvelopeError, canonical
from a2a.identity import BadCiphertext, BadSignature, Identity, did_of, mk_canonical, pubkey_of, verify, verify_mk_sig


def _pair():
    return Identity.generate(), Identity.generate()


def test_the_did_is_did_key_of_the_raw_pubkey_in_standard_base64():
    me = Identity.generate()
    assert me.did == "did:key:" + me.pub_b64 and len(me.pub_b64) == 44
    assert pubkey_of(me.did) == me.pub_raw and did_of(me.pub_raw) == me.did


def test_a_sealed_envelope_opens_only_for_its_recipient():
    a, b = _pair()
    wire = Envelope("msg.text", a.did, b.did, {"text": "hola"}).seal(a)
    assert "hola" not in str(wire)                              # the network sees only `kind`
    assert Envelope.open(b, wire, from_did=a.did).body == {"text": "hola"}
    c = Identity.generate()
    with pytest.raises(EnvelopeError):
        Envelope.open(c, dict(wire, to=c.did))


def test_one_flipped_byte_fails_verification():
    a, b = _pair()
    wire = Envelope("msg.text", a.did, b.did, {"text": "x"}).seal(a)
    ct = bytearray(wire["sealed"]["ct"].encode())
    ct[5] = ord("A") if ct[5] != ord("A") else ord("B")
    with pytest.raises(EnvelopeError) as e:
        Envelope.open(b, dict(wire, sealed=dict(wire["sealed"], ct=ct.decode())))
    assert e.value.reason == "bad_sig"


def test_the_transport_sender_must_be_the_envelope_sender():
    a, b = _pair()
    wire = Envelope("msg.text", a.did, b.did, {}).seal(a)
    with pytest.raises(EnvelopeError) as e:
        Envelope.open(b, wire, from_did=Identity.generate().did)
    assert e.value.reason == "bad_sig"


def test_future_ts_replay_expired_and_oversize_are_refused():
    a, b = _pair()
    now = 1_800_000_000
    fut = Envelope("msg.text", a.did, b.did, {}, ts=now + 600).seal(a)
    with pytest.raises(EnvelopeError):
        Envelope.open(b, fut, now=now)
    old = Envelope("msg.text", a.did, b.did, {}, ts=now - 31 * 86400).seal(a)
    with pytest.raises(EnvelopeError) as e:
        Envelope.open(b, old, now=now)
    assert e.value.reason == "expired"
    ok = Envelope("msg.text", a.did, b.did, {}, ts=now).seal(a)
    seen = {ok["id"]}
    with pytest.raises(EnvelopeError) as e:
        Envelope.open(b, ok, now=now, seen=seen)
    assert e.value.reason == "replay"
    with pytest.raises(EnvelopeError) as e:
        Envelope("msg.text", a.did, b.did, {"text": "x" * 17000}).seal(a)
    assert e.value.reason == "oversize"


def test_e2e_derives_the_same_key_on_both_sides_and_rejects_a_wrong_salt():
    a, b = _pair()
    sealed = a.seal(b.did, b"secret", salt="s1")
    assert b.open(a.did, sealed, salt="s1") == b"secret"
    with pytest.raises(BadCiphertext):
        b.open(a.did, sealed, salt="s2")


def test_meshkore_sig_matches_the_server_canonical_string():
    me = Identity.generate()
    h = me.mk_sig("POST", "/v1/mail/did%3Akey%3Aabc", '{"kind":"x"}', ts=100, nonce="n1")
    v, pub, ts, nonce, sig = h.split()
    assert (v, pub, ts, nonce) == ("v1", me.pub_b64, "100", "n1")
    verify(me.pub_raw, mk_canonical("POST", "/v1/mail/did%3Akey%3Aabc", '{"kind":"x"}', 100, "n1"), sig)
    assert verify_mk_sig(h, "POST", "/v1/mail/did%3Akey%3Aabc", '{"kind":"x"}', now=100) == me.pub_b64
    with pytest.raises(BadSignature):
        verify_mk_sig(h, "POST", "/v1/mail/did:key:abc", '{"kind":"x"}', now=100)   # the DECODED path is not it
    with pytest.raises(BadSignature):
        verify_mk_sig(h, "POST", "/v1/mail/did%3Akey%3Aabc", '{"kind":"x"}', now=1000)  # stale
    seen: set = set()
    verify_mk_sig(h, "POST", "/v1/mail/did%3Akey%3Aabc", '{"kind":"x"}', now=100, seen_nonces=seen)
    with pytest.raises(BadSignature):
        verify_mk_sig(h, "POST", "/v1/mail/did%3Akey%3Aabc", '{"kind":"x"}', now=100, seen_nonces=seen)


def test_canonical_json_is_key_order_independent():
    assert canonical({"b": 1, "a": 2}) == canonical({"a": 2, "b": 1}) == b'{"a":2,"b":1}'
