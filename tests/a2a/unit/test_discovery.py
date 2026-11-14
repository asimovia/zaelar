"""T573/T577 · discovery: normalised hashes, the mutual rule, a match proposes and only a yes sends (D10)."""
from __future__ import annotations

from a2a.discovery import hash_value, hashes_for, norm_email, norm_phone


def test_normalisation_and_hash_scheme():
    assert norm_email("  Marta@Example.COM ") == "marta@example.com"
    assert norm_email("nope") is None
    assert norm_phone("+34 600 11 22 33") == "+34600112233"
    assert norm_phone("0034600112233") == "+34600112233"
    assert norm_phone("600112233") is None and norm_phone("600112233", "34") == "+34600112233"
    import hashlib, hmac
    assert hash_value("marta@example.com") == hmac.new(b"meshkore-people-v1", b"marta@example.com",
                                                       hashlib.sha256).hexdigest()
    assert set(hashes_for(["A@b.co"], ["+34600112233"]).values()) == {"email", "phone"}


def _contacts(email):
    return [{"cid": "marta", "name": "Marta", "emails": [email]}]


def test_a_one_sided_lookup_finds_nothing(pair):
    a, b = pair()
    a.publish_hashes(emails=["ana@example.com"])
    b.publish_hashes(emails=["marta@example.com"])
    assert a.discover(_contacts("marta@example.com")) == []          # B never looked A up


def test_mutual_match_proposes_once_and_sends_nothing_without_yes(pair, net, clock, rows):
    a, b = pair()
    a.publish_hashes(emails=["ana@example.com"])
    b.publish_hashes(emails=["marta@example.com"])
    a.discover(_contacts("marta@example.com"))
    b.discover([{"cid": "ana", "name": "Ana", "emails": ["ana@example.com"]}])   # B: first side gets the match
    found = a.discover(_contacts("marta@example.com"))
    assert [f["cid"] for f in found] == ["marta"] and found[0]["matched_by"] == "email"
    assert net.boxes[b.me.did] == [] and net.boxes[a.me.did] == []             # proposals only
    assert a.discover(_contacts("marta@example.com")) == []                       # once per 30 days
    clock.advance(31 * 86400)
    b.discover([{"cid": "ana", "name": "Ana", "emails": ["ana@example.com"]}])   # the mutual window is 30 days
    a.asker = lambda card: "ask"
    a.discover(_contacts("marta@example.com"))
    assert [m.body["kind"] for m in net.boxes[b.me.did]] == ["connect.request"]
    assert not any("example.com" in str(r) or len(str(r.get("hashes", ""))) > 4 for r in rows)


def test_never_is_remembered(pair, clock):
    a, b = pair()
    a.publish_hashes(emails=["ana@example.com"]); b.publish_hashes(emails=["marta@example.com"])
    b.discover([{"cid": "ana", "emails": ["ana@example.com"]}])
    a.asker = lambda card: "never"
    a.discover(_contacts("marta@example.com"))
    clock.advance(40 * 86400)
    b.discover([{"cid": "ana", "emails": ["ana@example.com"]}])
    assert a.discover(_contacts("marta@example.com")) == []
